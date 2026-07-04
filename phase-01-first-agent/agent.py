# agent.py - phase 1: our first AI agent (LLM +  one tool + a loop)

import os
import json
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv



# --- 1. Load configuration from  the .env file ---
load_dotenv()       # reads the variables from .env into the environment

client = OpenAI(
    base_url=os.environ["OPENAI_BASE_URL"],     # point the sdk at local Ollama
    api_key=os.environ["OPENAI_API_KEY"],          # ollama ignores this, but the sdk requires a value
)
MODEL = os.environ["MODEL"]                     # e.g. "qwen2.5:1.5b" 



# --- 2. Define a tool: it's just a normal python function ---
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



# --- 3. Describe the tool to the model in the format it understands (JSON schema) ---
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
                        "description": "The name of the city, e.g. 'Tokyo'.",
                    }
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current local date and time.",
            "parameters": {
                "type": "object",
                "properties": {},   # no inputs -> empty
                "required": [],     # nothing is required
            },
        }, 
    },
]


# A lookup table so we can find the real Python function from the name the model gives us.
available_tools = {
    "get_weather": get_weather,
    "get_current_time": get_current_time,
}



# --- 4. The agent: an LLM running inside a loop ---
def run_agent(user_message: str) -> str:
    # The conversation history. We keep appending to this list as the agent works.
    messages = [{"role": "user", "content": user_message}]

    while True:     # <<< THIS LOOP IS THE AGENT
        # Ask the model what to do next, handing it the tool it's allowed to use.
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=tools,
            tool_choice='auto',     # let the model decide whether to call a tool 
        )

        reply = response.choices[0].message
        messages.append(reply)      # remember what the model just said/decided

        # If the model did NOT ask for a tool, it's giving its final answer -> we are done.
        if not reply.tool_calls:
            return reply.content
        
        # Otherwise the model wants to use a tool. Run each requested tool call.
        for tool_call in reply.tool_calls:
            name = tool_call.function.name
            args = json.loads(tool_call.function.arguments)     # arguments arrive as a JSON string

            print(f"[agent is calling tool] {name}({args})")

            result = available_tools[name](**args)      # actually run the Python function

            # Feed the tool's result back to the model so it an keep reasoning.
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": result,
            })
        # loop repeats -> the model now sees the tool result and decides what's next


# --- 5. Try it out ---
if __name__ == "__main__":
    answer = run_agent("What's the weather like in London and what time is it right now?")
    print(f"\nFinal answer:", answer)
