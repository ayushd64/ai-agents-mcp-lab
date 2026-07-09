# backend.py - FastAPI web service: upload a CSV, stream the agent's answer

import os, sys, json, shutil
from contextlib import asynccontextmanager

import duckdb
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse

from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver
from fastapi.responses import FileResponse

from guardrails import check_input

load_dotenv(override=True)

DATA_PATH = os.path.abspath("current_data.csv")     # the active dataset the servers read
if not os.path.exists(DATA_PATH):                   # seed with the sample on first run
    shutil.copy("sample_data.csv", DATA_PATH)

SYSTEM_PROMPT = (
    "You are a data analyst. Answer questions about the user's data by querying it with SQL.\n"
    "1. ONLY answer questions about the user's uploaded data. If a question is off-topic "
    "(weather, general knowledge, chit-chat, anything not answerable from the data), do NOT call "
    "any tools — reply exactly: 'I can only answer questions about your data.'\n"
    "2. Call get_schema once to learn the exact column names. Then write ONE read-only SELECT "
    "(DuckDB syntax) and call run_query. Do NOT rewrite a query that already succeeded — only "
    "rewrite if it returned an error. Never guess column names.\n"
    "3. If a question uses a business term (e.g. 'Q1', 'growth'), call search_glossary first.\n"
    "4. If the user asks for a chart/plot/graph, call make_chart with a SELECT, a chart_type "
    "(bar/line/scatter/area), and x/y column names matching the query output. Don't paste the spec.\n"
    "5. After a chart, ALWAYS also write a one-sentence summary of what it shows, with the key numbers.\n"
    "6. Report money in plain dollars (e.g. $68,000). Never divide by 1,000,000 or label small "
    "values as millions.\n"
    "7. Keep answers to one or two clear sentences with the actual numbers."
)



# The servers spawn per tool call and read DATA_FILE each time - so overwriting
# current_data.csv on upload is enough; no rebuild required.
def server_config():
    env = {**os.environ, "DATA_FILE": DATA_PATH}
    return {
        "sql":       {"command": sys.executable, "args": [os.path.abspath("sql_server.py")], "transport": "stdio", "env": env},
        "knowledge": {"command": sys.executable, "args": [os.path.abspath("knowledge_server.py")], "transport": "stdio", "env": env},
        "chart":     {"command": sys.executable, "args": [os.path.abspath("chart_server.py")], "transport": "stdio", "env": env},
    }

state = {"agent": None}

async def build_agent():
    client = MultiServerMCPClient(server_config())
    tools = await client.get_tools()
    # model = ChatOllama(model=os.environ["MODEL"],
    #                    temperature=0,
    #                 )
    model = ChatOpenAI(
        model=os.environ["MODEL"],
        base_url=os.environ["OPENAI_BASE_URL"],
        api_key=os.environ["OPENAI_API_KEY"],
        temperature=0,
    )
    state["agent"] = create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=InMemorySaver())

@asynccontextmanager
async def lifespan(app):
    await build_agent()         # build once when the server starts
    yield

app = FastAPI(lifespan=lifespan)




# ------------- helpers -------------
def sse(event: str, data) -> str:
    """Format one Server-Sent Event. JSON-encode the payload so newlines are safe."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

def tool_text(output) -> str:
    """Pull plain text out of a tool's output (string, ToolMessage, or content blocks.)"""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    content = getattr(output, "content", output)
    if isinstance(content, list):
        return "".join(
            (b.get("text", "") if isinstance(b, dict) else getattr(b, "text", "")) or "" for b in content
        )
    return str(content)



# ------------- endpoints -------------
@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    """Save the uploaded CSV as UTF-8 (converting from common encodings) and profile it."""
    raw = await file.read()
    # decode with a tolerant fallback, then write clean UTF-8
    for enc in ("utf-8-sig", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("utf-8", errors="ignore")
    with open(DATA_PATH, "w", encoding="utf-8", newline="") as f:
        f.write(text)

    con = duckdb.connect(":memory:")
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv('{DATA_PATH}', ignore_errors=true, auto_detect=true)")
    rows = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    cols = [{"name": c[0], "type": c[1]} for c in con.execute("DESCRIBE t").fetchall()]
    con.close()
    return {"status": "ok", "rows": rows, "columns": cols}





async def event_stream(q: str, thread_id: str):
    ok, msg = check_input(q)
    if not ok:
        yield sse("token", msg); yield sse("done", ""); return

    agent = state["agent"]
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 15}
    produced = False
    seen_sql = set()                                  # NEW: track shown queries

    async for ev in agent.astream_events(
        {"messages": [{"role": "user", "content": q}]}, config=config, version="v2"
    ):
        kind = ev["event"]
        if kind == "on_tool_start":
            sql = (ev["data"].get("input") or {}).get("sql", "")
            if ev["name"] in ("run_query", "make_chart") and sql:
                if sql in seen_sql:                   # skip duplicates
                    continue
                seen_sql.add(sql)
                yield sse("step", "Writing and running a query")
                yield sse("sql", sql)
            else:
                labels = {
                    "list_tables": "Looking at available data",
                    "get_schema": "Examining the columns",
                    "search_glossary": "Checking business definitions",
                }
                yield sse("step", labels.get(ev["name"], f"Working ({ev['name']})"))
        elif kind == "on_tool_end" and ev["name"] == "make_chart":
            spec = tool_text(ev["data"].get("output"))
            if spec.strip().startswith("{"):
                produced = True
                yield sse("chart", spec)
        elif kind == "on_chat_model_stream":
            token = ev["data"]["chunk"].content
            if token:
                produced = True
                yield sse("token", token)

    if not produced:
        yield sse("token", "Sorry, I couldn't produce an answer. Please rephrase.")
    yield sse("done", "")



@app.get("/stream")
async def stream(q: str, thread_id: str = "web-seesion"):
    import uuid
    return StreamingResponse(event_stream(q, f"{thread_id}-{uuid.uuid4()}"), media_type="text/event-stream")

@app.get("/")
async def home():
    return FileResponse("index.html")

