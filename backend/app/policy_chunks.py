from pathlib import Path
import re

POLICY_DIR = (
    Path(__file__).resolve().parents[1]
    / "knowledge"
    / "policies"
)


def load_policy_chunks():
    chunks = []

    for file in sorted(POLICY_DIR.glob("*.md")):
        content = file.read_text(encoding="utf-8-sig")

        match = re.search(
            r"^Policy ID:\s*(\S+)",
            content,
            re.MULTILINE,
        )

        if not match:
            raise ValueError(
                f"Missing Policy ID: {file.name}"
            )

        policy_id = match.group(1)

        sections = re.split(
            r"(?=^##\s+)",
            content,
            flags=re.MULTILINE,
        )

        for index, section in enumerate(sections):
            section = section.strip()

            if not section:
                continue

            heading = re.search(
                r"^##\s+(.+)$",
                section,
                re.MULTILINE,
            )

            title = (
                heading.group(1).strip()
                if heading
                else "Document Overview"
            )

            chunks.append({
                "chunk_id": f"{policy_id}-{index:03d}",
                "policy_id": policy_id,
                "source": file.name,
                "section": title,
                "text": section,
            })

    return chunks


if __name__ == "__main__":
    result = load_policy_chunks()

    print("Total policy chunks:", len(result))
    print("Total source documents:", len(
        set(item["source"] for item in result)
    ))

    print("\nSample chunks:")
    for item in result[:5]:
        print(
            item["chunk_id"],
            "|",
            item["source"],
            "|",
            item["section"],
        )
