# mcp_agent.py — Phase 4 (leveled up): multi-server MCP client + durable memory

import os
import sys
import json
import sqlite3
import asyncio
from contextlib import AsyncExitStack

from openai import AsyncOpenAI
from dotenv import load_dotenv

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# --- 1. Config ---
load_dotenv(override=True)   # .env wins over any system env var (the Phase 4 401 fix)
llm = AsyncOpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
MODEL = os.environ["MODEL"]
SYSTEM_PROMPT = "You are a helpful assistant. Use the available tools when they help answer the user."

# --- 2. The MCP servers we connect to: ours + one we did NOT write ---
SERVERS = {
    "notes": StdioServerParameters(
        command=sys.executable,              # our venv Python runs notes_server.py
        args=["notes_server.py"],
    ),
    "filesystem": StdioServerParameters(
        command="npx.cmd",                   # Windows: npx.cmd  (mac/Linux: use "npx")
        args=["-y", "@modelcontextprotocol/server-filesystem",
              os.path.abspath("sandbox")],   # the ONLY folder it may access
    ),
}

# --- 3. Durable conversation memory (Phase 2's pattern, now in the client) ---
CLIENT_DB = "client_memory.db"

def init_client_db():
    conn = sqlite3.connect(CLIENT_DB)
    conn.execute("CREATE TABLE IF NOT EXISTS messages "
                 "(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)")
    conn.commit(); conn.close()

def load_conversation():
    conn = sqlite3.connect(CLIENT_DB)
    rows = conn.execute("SELECT role, content FROM messages ORDER BY id").fetchall()
    conn.close()
    return [{"role": r, "content": c} for r, c in rows]

def save_message(role, content):
    conn = sqlite3.connect(CLIENT_DB)
    conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit(); conn.close()

# --- 4. Translate MCP tool descriptions into the LLM's expected format ---
def mcp_to_openai_tools(mcp_tools):
    return [
        {"type": "function",
         "function": {"name": t.name, "description": t.description, "parameters": t.inputSchema}}
        for t in mcp_tools
    ]

# --- 5. The agent loop — now routes each call to the server that owns the tool ---
async def run_agent(tool_to_session, conversation, tools):
    working = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation
    while True:
        response = await llm.chat.completions.create(
            model=MODEL, messages=working, tools=tools, tool_choice="auto"
        )
        reply = response.choices[0].message
        working.append(reply)

        if not reply.tool_calls:
            return reply.content

        for tool_call in reply.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)
            print(f"  [calling MCP tool] {name}({args})")

            session = tool_to_session[name]               # which server has this tool?
            result = await session.call_tool(name, args)  # call it on THAT server
            output = "\n".join(c.text for c in result.content if hasattr(c, "text"))

            working.append({"role": "tool", "tool_call_id": tool_call.id, "content": output})

# --- 6. Connect ALL servers, merge their tools, then chat ---
async def main():
    init_client_db()

    async with AsyncExitStack() as stack:
        tool_to_session = {}   # tool name -> the session that provides it
        all_tools = []         # merged tool list handed to the LLM

        for label, params in SERVERS.items():
            read, write = await stack.enter_async_context(stdio_client(params))
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            result = await session.list_tools()
            for t in result.tools:
                tool_to_session[t.name] = session      # remember who owns each tool
            all_tools.extend(mcp_to_openai_tools(result.tools))
            print(f"[{label}] connected — tools: {[t.name for t in result.tools]}")

        print("\nChat with your multi-server agent. Type 'exit' to quit.\n")

        conversation = load_conversation()
        if conversation:
            print(f"(Loaded {len(conversation)} past messages.)\n")

        while True:
            user_input = input("You: ").strip()
            if user_input.lower() in {"exit", "quit"}:
                break
            conversation.append({"role": "user", "content": user_input})
            save_message("user", user_input)

            answer = await run_agent(tool_to_session, conversation, all_tools)

            conversation.append({"role": "assistant", "content": answer})
            save_message("assistant", answer)
            print(f"Assistant: {answer}\n")

if __name__ == "__main__":
    asyncio.run(main())

