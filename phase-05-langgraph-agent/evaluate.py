# evaluate.py — Phase 6b (complete): dataset + tool-use check + judge + version-robust Langfuse scoring

import os
import sys
import json
import asyncio
from contextlib import nullcontext
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI            # reads whatever .env points to (NVIDIA or Ollama)
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent

from langfuse import get_client
from langfuse.langchain import CallbackHandler
from langchain.agents import create_agent

# ----------------------------------------------------------------------------
# 1. Config — the agent's model, and a temperature=0 judge for consistent scoring
# ----------------------------------------------------------------------------
load_dotenv(override=True)

model = ChatOpenAI(
    model=os.environ["MODEL"],
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)

SYSTEM_PROMPT = (
    "You are a helpful assistant. For questions about company policies, products, or "
    "internal facts, ALWAYS call search_docs first and answer ONLY from what it returns. "
    "Each retrieved chunk is prefixed with its source, like [from handbook.md]. "
    "Cite that source in your answer, e.g. 'According to handbook.md, ...'. "
    "If the answer isn't in the retrieved text, say you don't know."
)




judge = ChatOpenAI(
    model=os.environ["MODEL"],
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
    temperature=0,
)

mcp_client = MultiServerMCPClient({
    "notes": {
        "command": sys.executable,
        "args": [os.path.abspath("notes_server.py")],
        "transport": "stdio",
    },
})

# ----------------------------------------------------------------------------
# 2. The evaluation dataset. `expected_tool` checks the PATH; `must_contain`
#    checks hard facts. For "save" actions must_contain is empty on purpose —
#    the reliable signal there is the tool call, not the wording.
# ----------------------------------------------------------------------------
test_cases = [
    {"q": "What's the weather in London?", "must_contain": ["14"],
     "expected_tool": "get_weather", "criteria": "States London's weather ~14°C and rainy."},
    {"q": "What's the weather in Tokyo?", "must_contain": ["22"],
     "expected_tool": "get_weather", "criteria": "States Tokyo's weather ~22°C and sunny/clear."},
    {"q": "What's the weather in Jaipur?", "must_contain": ["38"],
     "expected_tool": "get_weather", "criteria": "States Jaipur's weather ~38°C and hot/clear."},
    {"q": "What's the weather in Paris?", "must_contain": ["available"],
     "expected_tool": "get_weather", "criteria": "Says weather data is NOT available for Paris."},
    {"q": "Save a note that I need to call the dentist.", "must_contain": [],
     "expected_tool": "add_note", "criteria": "Confirms a note about calling the dentist was saved."},
    {"q": "Save a reminder to buy groceries.", "must_contain": [],
     "expected_tool": "add_note", "criteria": "Confirms a reminder to buy groceries was saved."},
    {"q": "What is 15 times 4?", "must_contain": ["60"],
     "expected_tool": None, "criteria": "Answers 60."},
    {"q": "What is 100 divided by 4?", "must_contain": ["25"],
     "expected_tool": None, "criteria": "Answers 25."},
    {"q": "Remember that.", "must_contain": [],
     "expected_tool": None, "criteria": "Handles the vague request gracefully, e.g. asks what to remember."},
]

# ----------------------------------------------------------------------------
# 3. LLM-as-judge — a second model grades each answer 1–5 against the criteria
# ----------------------------------------------------------------------------
JUDGE_SYSTEM = (
    "You are a strict evaluator of an AI assistant. Given a question, the assistant's answer, and "
    "success criteria, score how well the answer meets the criteria. "
    'Reply with ONLY JSON: {"score": <integer 1-5>, "reason": "<short reason>"}. No other text.'
)

def extract_json(text: str) -> dict:
    """Pull the {...} out of the judge's reply, even if wrapped in markdown fences."""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])

async def judge_answer(q, answer, criteria):
    resp = await judge.ainvoke([
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": f"Question: {q}\nAnswer: {answer}\nCriteria: {criteria}"},
    ])
    try:
        d = extract_json(resp.content)
        return int(d["score"]), str(d.get("reason", ""))
    except Exception:
        return 0, f"(unparseable judge output: {resp.content[:60]})"

# ----------------------------------------------------------------------------
# 4. Helpers to inspect the PROCESS, not just the final text
# ----------------------------------------------------------------------------
def tools_used(messages):
    """Names of every tool the agent actually called during this run."""
    names = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            names.append(tc.get("name"))
    return names

def last_text(messages):
    """Last non-empty assistant message (local models sometimes end with a blank one)."""
    for m in reversed(messages):
        t = getattr(m, "content", "") or ""
        if isinstance(t, str) and t.strip():
            return t
    return ""

# ----------------------------------------------------------------------------
# 5. Run the suite
# ----------------------------------------------------------------------------
async def main():
    tools = await mcp_client.get_tools()
    agent = create_agent(model, tools)

    langfuse = get_client()
    handler = CallbackHandler()

    # Adapters so the code works across Langfuse SDK versions (method names differ)
    def open_span(name):
        if hasattr(langfuse, "start_as_current_span"):
            return langfuse.start_as_current_span(name=name)
        if hasattr(langfuse, "start_as_current_observation"):
            return langfuse.start_as_current_observation(as_type="span", name=name)
        return nullcontext()

    def add_score(name, value):
        for method in ("score_current_span", "score_current_trace"):
            fn = getattr(langfuse, method, None)
            if fn:
                try:
                    fn(name=name, value=value)
                except Exception as e:
                    print(f"  (score {name} skipped: {e})")
                return

    rows = []
    for case in test_cases:
        q = case["q"]
        with open_span(f"eval: {q[:40]}"):
            out = await agent.ainvoke(
                {"messages": [{"role": "user", "content": q}]},
                config={"callbacks": [handler]},
            )
            answer = last_text(out["messages"])
            used = tools_used(out["messages"])

            exact = all(s.lower() in answer.lower() for s in case["must_contain"])       # Check 1
            tool_ok = case["expected_tool"] is None or case["expected_tool"] in used      # Check 2
            score, reason = await judge_answer(q, answer, case["criteria"])              # Check 3

            add_score("exact_match", float(exact))
            add_score("correct_tool", float(tool_ok))
            add_score("judge_score", score)

        rows.append({"exact": exact, "tool": tool_ok, "score": score})
        p = lambda b: "PASS" if b else "FAIL"
        print(f"[exact {p(exact)} | tool {p(tool_ok)} | judge {score}/5] {q}")
        print(f"        tools used: {used or 'none'}  |  {reason}")
        print(f"        answer: {answer[:90]}\n")

    langfuse.flush()   # push all traces + scores before exit

    n = len(rows)
    print("=" * 58)
    print(f"Exact-match pass:  {sum(r['exact'] for r in rows)}/{n}")
    print(f"Correct-tool pass: {sum(r['tool'] for r in rows)}/{n}")
    print(f"Average judge:     {sum(r['score'] for r in rows) / n:.2f}/5")

if __name__ == "__main__":
    asyncio.run(main())

