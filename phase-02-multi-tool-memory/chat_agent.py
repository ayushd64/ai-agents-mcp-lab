# chat_agent.py - Phase 2: a multi-tool agent with memory that survives restarts

import os
import json
import sqlite3
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv


# --- 1. Config (identical pattern to Phase 1) ---
load_dotenv()
client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],
    api_key=os.environ["OPENAI_API_KEY"],
)
MODEL = os.environ["MODEL"]

# A system prompt sets the agent's persona and rules. It is not stored in memory.
SYSTEM_PROMPT = (
    "You are a friendly, concise personal assistant. "
    "Use your tools when a question needs live info or math. "
    "Remember what the user told you earlier in the conversation."
)



# --- 2. Tools (Phase 1's two, plus a calculator) ---
def get_weather(city: str) -> str:
    """Pretend to look up the weather. In real life this would call a weaher API."""
    fake_data = { 
        "tokyo": "22°C, sunny", 
        "london": "14°C, rainy", 
        "jaipur": "38°C, hot and clear", 
    }
    return fake_data.get(city.lower(), "Weather data not available for the city.")


def get_current_time() -> str:
    """Return the current local date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def calculator(expression: str) -> str:
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))  # toy; fine for a demo
    except Exception as e:
        return f"Error: {e}"
    

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a given city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "City name, e.g. 'Tokyo'"
                    }
                },
                "required": ["city"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date and time.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a math expression, e.g. '240 * 0.15'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "A math expression." 
                    }
                },
                "required": ["expression"]
            }
        }
    },
]
available_tools = {
    "get_weather": get_weather,
    "get_current_time": get_current_time,
    "calculator": calculator,
}


# --- 3. Durable memory: a tiny SQLite database ---
DB_PATH = "memory.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS messages "
        "(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, content TEXT)"
    )
    conn.commit()
    conn.close()


def reset_memory():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM messages")
    conn.commit()
    conn.close()


def load_conversation():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT role, content FROM messages ORDER BY id").fetchall()
    conn.close()
    return [{"role": role, "content": content} for role, content in rows]


def save_messages(role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT INTO messages (role, content) VALUES (?, ?)", (role, content))
    conn.commit()
    conn.close()



# --- 4. The agent loop (Phase 1's loop, unchanges in spirit) ---
def run_agent(working_messages):
    while True:     # <<< THIS LOOP IS THE AGENT
        # Ask the model what to do next, handing it the tool it's allowed to use.
        response = client.chat.completions.create(
            model=MODEL,
            messages=working_messages,
            tools=tools,
            tool_choice='auto',     # let the model decide whether to call a tool 
        )

        reply = response.choices[0].message
        working_messages.append(reply)      # working memory (scratchpad)

        # If the model did NOT ask for a tool, it's giving its final answer -> we are done.
        if not reply.tool_calls:
            return reply.content            # final answer -> done
        
        # Otherwise the model wants to use a tool. Run each requested tool call.
        for tool_call in reply.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)     # arguments arrive as a JSON string

            print(f"[agent is calling tool] {name}({args})")

            result = available_tools[name](**args)      # actually run the Python function

            # Feed the tool's result back to the model so it an keep reasoning.
            working_messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
        # loop repeats -> the model now sees the tool result and decides what's next



# --- 5. The Chat loop: durable memory lives BETWEEN turns ---
def chat():
    init_db()
    conversation = load_conversation()      # everything from past runs
    if conversation:
        print(f"(Loaded {len(conversation)} past messages - the assistant remembers you.)")
    print("Chat with your agent. Type 'exit' to quit.\n")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Goodbye!")
            break
        
        if user_input.lower() == "/reset":
            reset_memory()      # wipe the database table
            conversation.clear()        # wipe the in-memory list
            print("Memory cleared. Starting fresh.\n")
            continue        # skip the rest of this turn, go back to the prompt

        conversation.append({"role": "user", "content": user_input})
        save_messages("user", user_input)

        # Build this turn's working memory: sytem prompt + durable conversation.
        # The tool scratchpad gets appended to THIS list insde run_agent - not to 'conversation'.
        working_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation
        answer = run_agent(working_messages)

        conversation.append({"role": "assistant", "content": answer})
        save_messages("assistant", answer)
        print(f"Assistant: {answer}\n")


if __name__ == "__main__":
    chat()