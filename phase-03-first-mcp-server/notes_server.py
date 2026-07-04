# notes_server.py - Phase 3: my first MCP server (tools + resource + prompt)

from mcp.server.fastmcp import FastMCP

# Create the MCP server. This name is what shows up in hosts like Claude Desktop.
mcp = FastMCP("Notes & Weather")

# Simple in-memory storage for this demo (resets when the server restarts)
notes: list[str] = []



# --- TOOL 1: an ACTION with a side effect (think POST) ---
@mcp.tool()
def add_note(text: str) -> str:
    """Save a note. Use this whenever the user wants to remember something."""
    notes.append(text)
    return f"Saved not #{len(notes)}: {text}"



# --- Tool 2: a familiar one - but notice, ZERO hand-written schema this time ---
@mcp.tool()
def get_weather(city: str) -> str:
    """Get the current weather for a given city."""
    fake = { 
        "tokyo": "22°C, sunny", 
        "london": "14°C, rainy", 
        "jaipur": "38°C, hot and clear", 
    }
    return fake.get(city.lower(), "Weather data not available for that city.")



# --- RESOURCE: read-only DATA the host can load into context (think GET) ---
@mcp.resource("notes://all")
def all_notes() -> str:
    """Return every saved note as plain text."""
    if not notes:
        return "No notes yet."
    return "\n".join(f"{i}. {note}" for i, note in enumerate(notes, start=1))



# ---PROMPT: a reusable, named template the user can invoke ---
@mcp.prompt()
def summarize_notes() -> str:
    """A ready-made prompt that asks the model to summarize all notes."""
    return "Please read my notes and summarize them into 3 short bullet points."



# --- Run over stdio, the standard transport for local servers ---
if __name__ == "__main__":
    mcp.run()