# notes_server.py — SQLite-backed notes server
import sqlite3
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Notes & Weather")
DB_PATH = "notes.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS notes (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)")
    conn.commit(); conn.close()
init_db()

@mcp.tool()
def add_note(text: str) -> str:
    """Save a note. Use this whenever the user wants to remember something."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("INSERT INTO notes (text) VALUES (?)", (text,))
    conn.commit(); note_id = cur.lastrowid; conn.close()
    return f"Saved note #{note_id}: {text}"

@mcp.tool()
def get_weather(city: str) -> str:
    """Get the current weather for a given city."""
    fake = {"tokyo": "22°C, sunny", "london": "14°C, rainy", "jaipur": "38°C, hot and clear"}
    return fake.get(city.lower(), "Weather data not available for that city.")

@mcp.tool()
def list_notes() -> str:
    """Read back all saved notes. Use this when the user asks what's in their notes."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, text FROM notes ORDER BY id").fetchall()
    conn.close()
    return "No notes yet." if not rows else "\n".join(f"{i}. {t}" for i, t in rows)


@mcp.resource("notes://all")
def all_notes() -> str:
    """Return every saved note as plain text."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT id, text FROM notes ORDER BY id").fetchall()
    conn.close()
    return "No notes yet." if not rows else "\n".join(f"{i}. {t}" for i, t in rows)

if __name__ == "__main__":
    mcp.run()

