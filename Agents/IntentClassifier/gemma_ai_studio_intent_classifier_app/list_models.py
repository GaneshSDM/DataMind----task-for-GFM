"""List all models available to this API key."""
from google import genai
from config.settings import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)
models = client.models.list()
for m in models:
    print(m.name)
