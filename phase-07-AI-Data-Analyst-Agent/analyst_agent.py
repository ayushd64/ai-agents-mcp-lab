# analyst_agent.py — Step 3: a LangGraph agent that answers data questions via the SQL server

import os, sys, asyncio
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver

# --- 1. Config: reads whichever model your .env points to (local OR cloud) ---
load_dotenv(override=True)
model = ChatOpenAI(
    model=os.environ["MODEL"],
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)

# --- 2. The system prompt turns a tool-caller into a disciplined analyst ---
SYSTEM_PROMPT = (
    "You are a data analyst. You answer questions about the user's data by querying it with SQL.\n"
    "RULES:\n"
    "1. ALWAYS call get_schema first to learn the exact column names and types before writing SQL.\n"
    "2. Then call run_query with a single read-only SELECT statement (DuckDB SQL syntax).\n"
    "3. Never guess column names — use only the ones get_schema returned.\n"
    "4. After you get results, answer the user in one or two clear sentences, stating the numbers.\n"
    "5. If a query errors, read the error, fix your SQL, and try again."
)

# --- 3. Point the agent at your SQL MCP server ---
mcp_client = MultiServerMCPClient({
    "sql": {
        "command": sys.executable,                   # this venv's Python
        "args": [os.path.abspath("sql_server.py")],  # the server from Step 2
        "transport": "stdio",
    },
})


async def main():
    tools = await mcp_client.get_tools()
    print("Connected. Tools:", [t.name for t in tools])

    agent = create_react_agent(model, tools, prompt=SYSTEM_PROMPT, checkpointer=InMemorySaver())

    config = {"configurable": {"thread_id": "analyst-session"}}
    print(f"\nData analyst ready (model: {os.environ['MODEL']}). Ask about your data. Type 'exit' to quit.\n")

    while True:
        q = input("You: ").strip()
        if q.lower() in {"exit", "quit"}:
            break
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": q}]},
            config=config,
        )
        print("Analyst:", result["messages"][-1].content, "\n")


if __name__ == "__main__":
    asyncio.run(main())

