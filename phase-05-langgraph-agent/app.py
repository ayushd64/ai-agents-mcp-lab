# app.py — a chat UI over your guarded LangGraph + MCP agent

import os, sys, asyncio
import streamlit as st
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

from guardrails import check_input, check_output

load_dotenv(override=True)

SYSTEM_PROMPT = (
    "You are a helpful assistant. For questions about company policies, products, or internal "
    "facts, ALWAYS call search_docs first and answer ONLY from what it returns, citing the source. "
    "If the answer isn't in the retrieved text, say you don't know."
)

@st.cache_resource   # build ONCE and reuse — Streamlit reruns this script on every click
def build_agent():
    loop = asyncio.new_event_loop()   # one persistent event loop for our async agent
    model = ChatOpenAI(model=os.environ["MODEL"],
                       base_url=os.environ["OPENAI_BASE_URL"],
                       api_key=os.environ["OPENAI_API_KEY"])
    mcp_client = MultiServerMCPClient({
        "notes":     {"command": sys.executable, "args": [os.path.abspath("notes_server.py")], "transport": "stdio"},
        "knowledge": {"command": sys.executable, "args": [os.path.abspath("rag_server.py")],   "transport": "stdio"},
    })
    tools = loop.run_until_complete(mcp_client.get_tools())
    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=InMemorySaver())
    return agent, loop

agent, loop = build_agent()

def guarded_reply(text: str) -> str:
    ok, message = check_input(text)          # GATE 1: input guard
    if not ok:
        return message
    result = loop.run_until_complete(agent.ainvoke(
        {"messages": [{"role": "user", "content": text}]},
        config={"configurable": {"thread_id": "streamlit-session"}},
    ))
    return check_output(result["messages"][-1].content)   # GATE 2: output guard

# ---------------- UI ----------------
st.title("🤖 My Agent")
st.caption("LangGraph + MCP + local Ollama, with guardrails")

if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:      # redraw past turns on every rerun
    with st.chat_message(role):
        st.markdown(content)

if prompt := st.chat_input("Ask me something..."):
    st.session_state.history.append(("user", prompt))
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            reply = guarded_reply(prompt)
        st.markdown(reply)
    st.session_state.history.append(("assistant", reply))

