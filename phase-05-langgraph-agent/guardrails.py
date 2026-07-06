# guardrails.py — a lightweight safety layer for the agent

import re

# --- INPUT GUARD: run BEFORE the agent, to block bad requests cheaply ---
BLOCKED_PATTERNS = [
    r"ignore (all |your |previous )?instructions",   # classic prompt-injection
    r"reveal.*(system prompt|instructions)",          # trying to extract the prompt
    r"\b(bomb|explosive|weapon)\b.*\b(make|build|create)\b",
]

def check_input(text: str):
    """Return (ok, message). ok=False means: don't call the agent, show `message`."""
    if len(text) > 2000:
        return False, "That message is too long — please shorten it."
    lowered = text.lower()
    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, lowered):
            return False, "I'm sorry, I can't help with that request."
    return True, ""

# --- OUTPUT GUARD: run AFTER the agent, to sanitize what the user sees ---
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
LONG_DIGITS_RE = re.compile(r"\b\d{12,19}\b")   # crude credit-card-like sequences

def check_output(text: str):
    """Return sanitized text, redacting anything that shouldn't leak."""
    if not text or not text.strip():
        return "Sorry, I couldn't produce a response. Please try rephrasing."
    text = EMAIL_RE.sub("[email redacted]", text)
    text = LONG_DIGITS_RE.sub("[number redacted]", text)
    return text

