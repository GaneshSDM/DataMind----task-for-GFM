"""Test which GEMMA 4 models are responding correctly."""
from google import genai
from google.genai import types
from config.settings import GEMINI_API_KEY

client = genai.Client(
    api_key=GEMINI_API_KEY,
    http_options=types.HttpOptions(timeout=60_000),
)

MODELS = ["gemma-4-26b-a4b-it", "gemma-4-31b-it"]
PROMPT = 'Reply with only this JSON: {"status": "ok", "model": "<your model name>"}'

for model in MODELS:
    try:
        r = client.models.generate_content(
            model=model,
            contents=PROMPT,
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=50),
        )
        print(f"[OK]  {model} -> {r.text.strip()[:80]}")
    except Exception as e:
        print(f"[ERR] {model} -> {e}")
