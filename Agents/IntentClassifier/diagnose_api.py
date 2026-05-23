"""Confirm gemma-4-31b-it with 2048 output tokens completes full JSON."""
import time
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY
from core.intent_processor import IntentProcessor

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=180_000),
)

proc = IntentProcessor()
sr1 = (
    "Show me why invoice INV-7821 for order ORD-4589 is higher than expected, "
    "compare the invoice and payment records with the contract discount terms, "
    "and create a correction request if the discount was missed."
)
prompt = proc._build_prompt(sr1)

print(f"[TEST] gemma-4-31b-it | max_output_tokens=2048")
t0 = time.time()
try:
    r = client.models.generate_content(
        model="gemma-4-31b-it",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.05, max_output_tokens=2048),
    )
    elapsed = round(time.time() - t0, 1)
    text = r.text if r.text else ""
    finish = r.candidates[0].finish_reason if r.candidates else "unknown"
    print(f"  Elapsed   : {elapsed}s")
    print(f"  Finish    : {finish}")
    print(f"  Chars out : {len(text)}")
    print(f"  Response  :\n{text}")
except Exception as e:
    elapsed = round(time.time() - t0, 1)
    print(f"  [ERR] {elapsed}s | {e}")
