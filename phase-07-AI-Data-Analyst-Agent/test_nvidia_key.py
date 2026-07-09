# test_nvidia_key.py — verify the NVIDIA cloud model + key from .env actually work

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(override=True)

base_url = os.environ.get("OPENAI_BASE_URL")
api_key  = os.environ.get("OPENAI_API_KEY")
model    = os.environ.get("MODEL")

# Show what we loaded (key masked) so you can spot a wrong/missing value
print("BASE_URL:", base_url)
print("MODEL:   ", model)
print("KEY:     ", (api_key[:8] + "…" + api_key[-4:]) if api_key else "MISSING")
print("-" * 40)

try:
    client = OpenAI(base_url=base_url, api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: OK"}],
        max_tokens=10,
    )
    print("✅ SUCCESS — the model replied:")
    print("   ", resp.choices[0].message.content)
except Exception as e:
    print("❌ FAILED:", type(e).__name__)
    print("   ", e)

