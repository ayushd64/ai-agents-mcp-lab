# langgraph_agent.py - Phase 5: the same MCP agent, now built by LangGraph

import os
import sys
import asyncio
from dotenv import load_dotenv

from langfuse import get_client
from langfuse.langchain import CallbackHandler

from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import InMemorySaver       # Older versions: Memory Saver


# --- 1. The Model: our working NVIDIA setup, wrapped for langchain ---
load_dotenv(override=True)
model = ChatOpenAI(
    model=os.environ["MODEL"],
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)


# --- 2. Point LangGraph at our MCP server (this replaces our entire Phase 4 client) ---
mcp_client = MultiServerMCPClient({
    "notes": {
        "command": sys.executable,                      # our venv python
        "args": [os.path.abspath("notes_server.py")],   # our server
        "transport": "stdio",
    },
    "filesystem": {
        "command": "npx.cmd",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", os.path.abspath("sandbox")],
        "transport": "stdio",
    },
})


async def main():
    # Load the server's tools, already wrapped as LangChain tools - no translation code
    tools = await mcp_client.get_tools()
    print("Loaded MCP tools:", [t.name for t in tools])

    # --- 3. Build the agent. THIS ONE line replaces our whole run_agent loop ---
    memory = InMemorySaver()
    agent = create_react_agent(model, tools, checkpointer=memory)

    langfuse = get_client()
    if langfuse.auth_check():
        print("Langfuse connected - traces will appear inn our dashboard.")
    langfuse_handler = CallbackHandler()        # reads our LANGFUSE_* env vars automatically

    # See our agent AS a graph (copy this into https://mermaid.live to view it)
    print("\n----- our agent's graph -----")
    print(agent.get_graph().draw_mermaid())
    print("-------------------------------\n")


    # --- 4. Chat. The thread_id ties every message into one remembered conversation ---
    config = {"configurable": {"thread_id": "my_chat"},
              "callbacks": [langfuse_handler],      # <-- every step now gets recorded
              "metadata": {
                  "langfuse_session_id": "test_session",
                  "langfuse_tags": ["phase-6", "notes-agent"],
              }
            }
    print("Chat with our LangGraph agent. Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        langfuse.flush()        # ensure all traces are uploaded befoore the program quits
        # Pass ONLY the new message - LangGraph remembers the rest of you
        try:
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
            )
            print("Assistant:", result["messages"][-1].content, "\n")
        except Exception as e:
            print(f"[error] {type(e).__name__}: {e}\n")     # catch it, keep the loop alive



if __name__ == "__main__":
    asyncio.run(main())