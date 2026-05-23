"""
Embedding service — uses Google AI gemini-embedding-exp-03-07
with output_dimensionality=1024 to match the PgVector store
(populated by BAAI/bge-large-en-v1.5 via the upstream agent).
"""
from google import genai
from google.genai import types


def generate_embedding(text: str, api_key: str) -> list[float]:
    """Return a 1024-dimensional embedding for *text* via Google AI Studio."""
    client = genai.Client(api_key=api_key)
    result = client.models.embed_content(
        model="gemini-embedding-exp-03-07",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=1024,
        ),
    )
    return list(result.embeddings[0].values)
