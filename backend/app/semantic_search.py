import json

from sqlalchemy import text

from .db import engine
from .embeddings import embed_query


async def semantic_search(query: str, top_k: int = 3):
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query cannot be empty.")

    if not isinstance(top_k, int) or isinstance(top_k, bool):
        raise ValueError("top_k must be an integer.")

    if not 1 <= top_k <= 10:
        raise ValueError("top_k must be between 1 and 10.")

    vector = await embed_query(query)
    vector_json = json.dumps(vector)

    statement = text("""
        SELECT
            chunk_id,
            policy_id,
            source,
            section,
            content,
            1 - (embedding <=> CAST(:query_vector AS vector)) AS score
        FROM policy_chunks
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> CAST(:query_vector AS vector),
                 chunk_id
        LIMIT :limit
    """)

    async with engine.connect() as conn:
        result = await conn.execute(
            statement,
            {
                "query_vector": vector_json,
                "limit": top_k,
            },
        )
        rows = result.mappings().all()

    return [
        {
            "chunk_id": row["chunk_id"],
            "policy_id": row["policy_id"],
            "source": row["source"],
            "section": row["section"],
            "text": row["content"],
            "score": round(float(row["score"]), 4),
        }
        for row in rows
    ]
