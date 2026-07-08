# backend.py - FastAPI web service: upload a CSV, stream the agent's answer

import os, sys, json, shutil
from contextlib import asynccontextmanager

import duckdb
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse

# from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

from guardrails import check_input

load_dotenv(override=True)

DATA_PATH = os.path.abspath("current_data.csv")     # the active dataset the servers read
if not os.path.exists(DATA_PATH):                   # seed with the sample on first run
    shutil.copy("sample_data.csv", DATA_PATH)

SYSTEM_PROMPT = ( 
    "You are a data analyst. Answer questions about the user's data by querying it with SQL.\n" 
    "1. Call get_schema exactly once. Call run_query exactly once unless the query fails. After receiving the SQL result, immediately answer the user. Do not call the same tool repeatedly.\n"
    "2. Then call run_query with a single read-only SELECT (DuckDB syntax). Never guess column names.\n" 
    "3. If a question uses a business term (e.g. 'Q1', 'growth'), call search_glossary first.\n" 
    "4. If the user asks for a chart/plot/graph, call make_chart with a SELECT, a chart_type " "(bar/line/scatter/area), and x/y column names matching the query output. Don't paste the spec.\n" 
    "5. Answer in one or two clear sentences with the actual numbers.\n" "SQL TIPS (DuckDB): single line; use QUARTER(date) for quarters; prefer SUM(CASE WHEN ...)." 
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
    model = ChatOllama(model=os.environ["MODEL"],
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
    """Save the uploaded CSV as the active dataset and return a quick schema summary."""
    with open(DATA_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    con = duckdb.connect(":memory:")            # profile the new file
    con.execute(f"CREATE TABLE t AS SELECT * FROM read_csv_auto('{DATA_PATH}')")
    rows = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
    cols = [{"name": c[0], "type": c[1]} for c in con.execute("DESCRIBE t").fetchall()]
    con.close()
    return {"status": "ok", "rows": rows, "columns": cols }



async def event_stream(q: str, thread_id: str):
    ok, msg = check_input(q)                    # GATE 1: input guard
    if not ok:
        yield sse("token", msg); yield sse("done", ""); return
    
    agent = state["agent"]
    config = {"configurable": {"thread_id": thread_id}, "recursion_limit": 50}
    got_text = False



    async for ev in agent.astream_events(
        {"messages": [{"role": "user", "content": q}]}, config=config, version="v2"        
    ):
        # print(ev["event"])
        kind = ev["event"]
        if kind == "on_tool_start":
            yield sse("step", f"Calling {ev['name']}...")
        elif kind == "on_tool_end" and ev["name"] == 'make_chart':
            spec = tool_text(ev["data"].get("output"))
            if spec.strip().startswith("{"):
                yield sse("chart", spec)
        elif kind == "on_chat_model_stream":
            chunk = ev["data"]["chunk"]
            token = chunk.content
            # token = getattr(ev["data"]["chunk"], "contnet", "") or ""
            if token:
                got_text = True
                yield sse("token", token)
    if not got_text:
        yield sse("token", "Sorry, I couldn't produce an answer. Please rephrase.")
    yield sse("done", "")


@app.get("/stream")
async def stream(q: str, thread_id: str = "web-seesion"):
    return StreamingResponse(event_stream(q, thread_id), media_type="text/event-stream")

