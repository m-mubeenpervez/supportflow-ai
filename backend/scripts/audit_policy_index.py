"""Read-only verification of the live policy index against checked-in markdown."""
import asyncio
from hashlib import sha256
from sqlalchemy import text
from app.db import engine
from app.policy_chunks import load_policy_chunks


async def main():
    local = {item["chunk_id"]: item for item in load_policy_chunks()}
    async with engine.connect() as conn:
        counts = (await conn.execute(text(
            "SELECT count(*) AS total, "
            "count(*) FILTER (WHERE embedding IS NOT NULL) AS embedded, "
            "count(*) FILTER (WHERE policy_id = 'SF-REFUND-001') AS refund "
            "FROM policy_chunks"
        ))).mappings().one()
        rows = (await conn.execute(text(
            "SELECT chunk_id, policy_id, source, section, content "
            "FROM policy_chunks WHERE policy_id = 'SF-REFUND-001' "
            "ORDER BY chunk_id"
        ))).mappings().all()
    mismatches = []
    for row in rows:
        item = local.get(row["chunk_id"])
        if not item or item["text"].strip() != row["content"].strip():
            mismatches.append(row["chunk_id"])
    print(f"live_total={counts['total']} live_embedded={counts['embedded']} live_refund={counts['refund']}")
    print(f"local_chunks={len(local)} refund_rows={len(rows)} content_mismatches={mismatches}")
    for row in rows:
        digest = sha256(row["content"].encode()).hexdigest()[:12]
        print(f"{row['chunk_id']}|{row['section']}|sha256={digest}")


if __name__ == "__main__":
    asyncio.run(main())
