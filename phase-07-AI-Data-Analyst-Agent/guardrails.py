# guardrails.py — the app's shared safety layer (imported by servers AND the agent)

import re

# ============ SQL SAFETY (used by sql_server.py and chart_server.py) ============

# Defense-in-depth backup: block data-modifying keywords as whole words.
# (Whole-word match so it won't trip on columns like "created_at" or "updated".)
_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|attach|detach|copy|"
    r"install|pragma|vacuum|export|reindex)\b",
    re.IGNORECASE,
)

def validate_sql(sql: str):
    """Return (ok, result). If ok -> result is the cleaned SQL. If not -> result is an error string.
    Allows only a single, read-only SELECT/WITH statement."""
    clean = sql.strip().rstrip(";").strip()
    if not clean:
        return False, "Error: empty query."
    low = clean.lower()
    if not (low.startswith("select") or low.startswith("with")):   # primary guard
        return False, "Error: only read-only SELECT queries are allowed."
    if ";" in clean:                                                # no chained statements
        return False, "Error: only one statement is allowed."
    if _WRITE_KEYWORDS.search(clean):                              # backup guard
        return False, "Error: query contains a disallowed keyword; only read-only SELECT is permitted."
    return True, clean

MAX_ROWS = 100   # cap results so a huge query can't flood the app or the model's context


# ============ INPUT GUARD (before the agent) ============

_BLOCKED = [
    r"ignore (all |your |previous )?(instructions|prompt)",
    r"reveal.*(system prompt|instructions)",
    r"you are now ",          # role-override injection
]

def check_input(text: str):
    """Return (ok, message). ok=False -> skip the agent and show `message`."""
    if not text or not text.strip():
        return False, "Please enter a question."
    if len(text) > 2000:
        return False, "That message is too long — please shorten it."
    low = text.lower()
    for pat in _BLOCKED:
        if re.search(pat, low):
            return False, "I can only help with questions about your data."
    return True, ""


# ============ OUTPUT GUARD (after the agent) ============

def check_output(text: str):
    """Sanitize the final answer before showing it."""
    if not text or not text.strip():
        return "Sorry, I couldn't produce an answer. Please try rephrasing your question."
    return text

