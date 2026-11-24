import argparse
import asyncio
import json

from sqlalchemy.engine import make_url

from sqlalchemy import text

from backend.app.config import settings
from backend.app.db import engine
from backend.app.embeddings import embed_document


async def main(execute=False, limit=1):
    url = make_url(settings.database_url)

    if (
        url.drivername != "postgresql+asyncpg"
        or url.database != settings.application_database_name
    ):
        raise RuntimeError(
            "Refusing to run outside the authoritative application database."
        )

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("""
                SELECT chunk_id, policy_id, section, content
                FROM policy_chunks
                WHERE embedding IS NULL
                ORDER BY chunk_id
            """))

            pending = result.mappings().all()

        print("=== POLICY EMBEDDING INGESTION ===")
        print("Pending chunks:", len(pending))
        print("Requested batch limit:", limit)

        selected = pending[:limit]

        if not execute:
            print("Mode: DRY RUN")
            print("Gemini API calls: 0")
            print("Database writes: 0")

            for chunk in selected:
                print("PENDING:", chunk["chunk_id"])

            print("Dry run: PASSED")
            return

        print("Mode: EXECUTE")
        completed = 0

        for chunk in selected:
            print("Processing:", chunk["chunk_id"])

            try:
                vector = await embed_document(
                    chunk["content"],
                    f"{chunk['policy_id']} - {chunk['section']}",
                )

                vector_json = json.dumps(vector)

                async with engine.begin() as conn:
                    result = await conn.execute(
                        text("""
                            UPDATE policy_chunks
                            SET embedding = CAST(:embedding AS vector)
                            WHERE chunk_id = :chunk_id
                              AND embedding IS NULL
                        """),
                        {
                            "embedding": vector_json,
                            "chunk_id": chunk["chunk_id"],
                        },
                    )

                    if result.rowcount != 1:
                        raise RuntimeError(
                            "Chunk was changed during embedding."
                        )

                completed += 1
                print("SAVED:", chunk["chunk_id"])

            except Exception as error:
                print("Embedding stopped safely.")
                print("Error type:", type(error).__name__)
                raise

        print("Successfully embedded:", completed)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually call Gemini and save embeddings.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=1,
    )

    args = parser.parse_args()

    if not 1 <= args.limit <= 49:
        parser.error("--limit must be between 1 and 49")

    asyncio.run(main(args.execute, args.limit))
