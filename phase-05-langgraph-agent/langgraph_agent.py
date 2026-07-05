# langgraph_agent.py - Phase 5: the same MCP agent, now built by LangGraph

import os
import sys
import asyncio
from dotenv import load_dotenv

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

    # See our agent AS a graph (copy this into https://mermaid.live to view it)
    print("\n----- our agent's graph -----")
    print(agent.get_graph().draw_mermaid())
    print("-------------------------------\n")


    # --- 4. Chat. The thread_id ties every message into one remembered conversation ---
    config = {"configurable": {"thread_id": "my_chat"}}
    print("Chat with our LangGraph agent. Type 'exit' to quit.\n")
    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        # Pass ONLY the new message - LangGraph remembers the rest of you
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": user_input}]},
            config=config,
        )
        print("Assistant:", result["messages"][-1].content, "\n")



if __name__ == "__main__":
    asyncio.run(main())