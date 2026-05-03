from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from codeask.app import create_app
from codeask.settings import Settings

FEATURE_NAME = "AnythingLLM Reference"
FEATURE_SLUG = "anything-llm-reference"
FEATURE_DESCRIPTION = (
    "Curated reference knowledge base extracted from AnythingLLM and filtered "
    "for CodeAsk product and architecture learning."
)
KB_ROOT = Path(__file__).resolve().parents[1] / "references" / "anything-llm" / "codeask-kb"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed the AnythingLLM reference knowledge base into CodeAsk."
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Delete same-path existing documents in the feature before re-uploading.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the actions without writing to the CodeAsk data store.",
    )
    return parser.parse_args()


def iter_markdown_files() -> list[Path]:
    return sorted(path for path in KB_ROOT.glob("*.md") if path.is_file())


def title_for(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return path.stem.replace("-", " ")


async def ensure_feature(client: AsyncClient, dry_run: bool) -> tuple[int, bool]:
    response = await client.get("/api/features")
    response.raise_for_status()
    for feature in response.json():
        if feature["slug"] == FEATURE_SLUG:
            return int(feature["id"]), False

    if dry_run:
        return -1, True

    response = await client.post(
        "/api/features",
        json={
            "name": FEATURE_NAME,
            "slug": FEATURE_SLUG,
            "description": FEATURE_DESCRIPTION,
        },
    )
    response.raise_for_status()
    return int(response.json()["id"]), True


async def list_documents(client: AsyncClient, feature_id: int) -> list[dict]:
    response = await client.get(f"/api/documents?feature_id={feature_id}")
    response.raise_for_status()
    return list(response.json())


async def delete_document(client: AsyncClient, document_id: int) -> None:
    response = await client.delete(f"/api/documents/{document_id}")
    response.raise_for_status()


async def upload_document(client: AsyncClient, feature_id: int, path: Path) -> None:
    with path.open("rb") as handle:
        response = await client.post(
            "/api/documents",
            data={
                "feature_id": str(feature_id),
                "title": title_for(path),
                "tags": "reference,anything-llm,codeask",
            },
            files={"file": (path.name, handle, "text/markdown")},
        )
    response.raise_for_status()


async def main() -> None:
    args = parse_args()
    if not KB_ROOT.is_dir():
        raise SystemExit(f"knowledge base directory not found: {KB_ROOT}")

    docs = iter_markdown_files()
    if not docs:
        raise SystemExit(f"no markdown files found under: {KB_ROOT}")

    settings = Settings()  # type: ignore[call-arg]
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://seed.local",
        ) as client:
            feature_id, created = await ensure_feature(client, args.dry_run)
            existing = [] if args.dry_run else await list_documents(client, feature_id)
            by_path = {document["path"]: document for document in existing}

            deleted = 0
            uploaded = 0
            skipped = 0

            for path in docs:
                existing_doc = by_path.get(path.name)
                if existing_doc and args.refresh and not args.dry_run:
                    await delete_document(client, int(existing_doc["id"]))
                    deleted += 1
                    existing_doc = None

                if existing_doc is not None:
                    skipped += 1
                    print(f"skip    {path.name}")
                    continue

                if args.dry_run:
                    print(f"upload  {path.name}")
                    uploaded += 1
                    continue

                await upload_document(client, feature_id, path)
                uploaded += 1
                print(f"upload  {path.name}")

    feature_note = "create" if created else "reuse"
    print(
        f"feature={FEATURE_SLUG} action={feature_note} uploaded={uploaded} "
        f"skipped={skipped} deleted={deleted} dry_run={args.dry_run}"
    )


if __name__ == "__main__":
    asyncio.run(main())
