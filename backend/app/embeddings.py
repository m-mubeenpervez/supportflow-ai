import math

from google import genai
from google.genai import types

from .config import settings


EMBEDDING_MODEL = settings.gemini_embedding_model
EMBEDDING_DIM = settings.gemini_embed_dim


def validate_embedding(values):
    if values is None:
        raise ValueError("Gemini returned no embedding.")

    vector = [float(value) for value in values]

    if len(vector) != EMBEDDING_DIM:
        raise ValueError(
            f"Expected {EMBEDDING_DIM} dimensions, "
            f"received {len(vector)}."
        )

    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Embedding contains invalid numbers.")

    return vector


def prepare_document(text, title):
    if not text.strip():
        raise ValueError("Document text is empty.")

    return (
        f"title: {title}\n"
        f"content: {text.strip()}"
    )


def prepare_query(query):
    if not query.strip():
        raise ValueError("Search query is empty.")

    return f"task: search result | query: {query.strip()}"


async def embed_text(text):
    if not text.strip():
        raise ValueError("Embedding input is empty.")

    if EMBEDDING_MODEL != "gemini-embedding-2":
        raise ValueError("Unexpected embedding model.")

    if EMBEDDING_DIM != 768:
        raise ValueError("Expected 768 embedding dimensions.")

    if not settings.gemini_api_key:
        raise ValueError("Gemini API key is missing.")

    client = genai.Client(api_key=settings.gemini_api_key)

    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIM
            ),
        )

        embeddings = response.embeddings or []

        if len(embeddings) != 1:
            raise ValueError(
                "Expected exactly one embedding."
            )

        return validate_embedding(embeddings[0].values)

    finally:
        await client.aio.aclose()


async def embed_document(text, title):
    prepared = prepare_document(text, title)
    return await embed_text(prepared)


async def embed_query(query):
    prepared = prepare_query(query)
    return await embed_text(prepared)
