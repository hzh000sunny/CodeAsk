"""End-to-end native wiki import API tests."""

import pytest
from httpx import AsyncClient
from codeask.settings import Settings


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89"
    b"\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0\x00\x00\x03\x01\x01\x00"
    b"\x18\xdd\x8d\xb1"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def _create_space_and_folder(
    client: AsyncClient,
    *,
    slug: str = "wiki-imports",
    folder_name: str = "Docs",
) -> tuple[int, int]:
    feature = await client.post(
        "/api/features",
        json={"name": "Wiki Imports", "slug": slug},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    feature_id = int(feature.json()["id"])

    tree = await client.get("/api/wiki/tree", params={"feature_id": feature_id})
    assert tree.status_code == 200, tree.text
    space_id = int(tree.json()["space"]["id"])

    folder = await client.post(
        "/api/wiki/nodes",
        json={"space_id": space_id, "parent_id": None, "type": "folder", "name": folder_name},
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert folder.status_code == 201, folder.text
    return space_id, int(folder.json()["id"])


@pytest.mark.asyncio
async def test_import_preflight_accepts_uploaded_markdown_relationships(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-ready")

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is True
    assert body["summary"] == {
        "total_files": 3,
        "document_count": 2,
        "asset_count": 1,
        "conflict_count": 0,
        "warning_count": 0,
    }
    items = {item["relative_path"]: item for item in body["items"]}
    assert items["Runbook.md"]["target_path"] == "docs/runbook"
    assert items["Runbook.md"]["status"] == "ready"
    assert items["Runbook.md"]["issues"] == []
    assert items["guides/Guide.md"]["target_path"] == "docs/guides/guide"
    assert items["images/diagram.png"]["target_path"] == "docs/images/diagram.png"


@pytest.mark.asyncio
async def test_import_preflight_reports_conflicts_and_broken_links(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-conflict")

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Existing",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Existing.md",
                    b"# Existing\n\nSee [Missing](./missing.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["ready"] is False
    assert body["summary"] == {
        "total_files": 2,
        "document_count": 1,
        "asset_count": 1,
        "conflict_count": 1,
        "warning_count": 1,
    }
    items = {item["relative_path"]: item for item in body["items"]}
    assert items["Existing.md"]["target_path"] == "docs/existing"
    assert items["Existing.md"]["status"] == "conflict"
    issue_codes = {issue["code"] for issue in items["Existing.md"]["issues"]}
    assert issue_codes == {"path_conflict", "broken_link"}
    broken_link = next(issue for issue in items["Existing.md"]["issues"] if issue["code"] == "broken_link")
    assert broken_link["target"] == "./missing.md"
    assert broken_link["resolved_path"] == "docs/missing"
    assert items["images/diagram.png"]["status"] == "ready"


@pytest.mark.asyncio
async def test_non_owner_cannot_run_import_preflight(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-denied")

    response = await client.post(
        "/api/wiki/imports/preflight",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Runbook.md", b"# Runbook", "text/markdown"))],
        headers={"X-Subject-Id": "viewer@dev-9"},
    )

    assert response.status_code == 403, response.text


@pytest.mark.asyncio
async def test_create_import_job_persists_staged_files_and_items(
    client: AsyncClient,
    settings: Settings,
) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-job")

    response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    job_id = int(body["id"])
    assert body["status"] == "queued"
    assert body["space_id"] == space_id
    assert body["summary"] == {
        "total_files": 3,
        "document_count": 2,
        "asset_count": 1,
        "conflict_count": 0,
        "warning_count": 0,
    }

    job_response = await client.get(
        f"/api/wiki/imports/{job_id}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert job_response.status_code == 200, job_response.text
    assert job_response.json()["id"] == job_id
    assert job_response.json()["summary"] == body["summary"]

    items_response = await client.get(
        f"/api/wiki/imports/{job_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}
    assert items["Runbook.md"]["target_path"] == "docs/runbook"
    assert items["Runbook.md"]["status"] == "pending"
    assert items["Runbook.md"]["item_kind"] == "document"
    assert items["guides/Guide.md"]["target_path"] == "docs/guides/guide"
    assert items["images/diagram.png"]["target_path"] == "docs/images/diagram.png"
    assert items["images/diagram.png"]["item_kind"] == "asset"
    assert items["Runbook.md"]["warnings"] == []

    staged_root = settings.data_dir / "wiki" / "imports" / f"job_{job_id}"
    assert (staged_root / "Runbook.md").read_text(encoding="utf-8") == (
        "# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)"
    )
    assert (staged_root / "guides" / "Guide.md").read_text(encoding="utf-8") == "# Guide\n"
    assert (staged_root / "images" / "diagram.png").read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_create_import_job_rejects_conflicts(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-job-conflict")

    existing = await client.post(
        "/api/wiki/nodes",
        json={
            "space_id": space_id,
            "parent_id": parent_id,
            "type": "document",
            "name": "Existing",
        },
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Existing.md", b"# Existing", "text/markdown"))],
        headers={"X-Subject-Id": "owner@dev-1"},
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "import preflight has conflicts"


@pytest.mark.asyncio
async def test_apply_import_job_creates_native_wiki_content(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-apply")

    create_response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[
            (
                "files",
                (
                    "Runbook.md",
                    b"# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)",
                    "text/markdown",
                ),
            ),
            ("files", ("guides/Guide.md", b"# Guide\n", "text/markdown")),
            ("files", ("images/diagram.png", PNG_BYTES, "image/png")),
        ],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = int(create_response.json()["id"])

    apply_response = await client.post(
        f"/api/wiki/imports/{job_id}/apply",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert apply_response.status_code == 200, apply_response.text
    assert apply_response.json()["status"] == "succeeded"

    items_response = await client.get(
        f"/api/wiki/imports/{job_id}/items",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert items_response.status_code == 200, items_response.text
    items = {item["source_path"]: item for item in items_response.json()["items"]}
    assert items["Runbook.md"]["status"] == "imported"
    assert items["Runbook.md"]["result_node_id"] is not None
    assert items["guides/Guide.md"]["status"] == "imported"
    assert items["images/diagram.png"]["status"] == "imported"
    assert items["images/diagram.png"]["result_node_id"] is not None

    runbook_response = await client.get(
        f"/api/wiki/documents/{items['Runbook.md']['result_node_id']}",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert runbook_response.status_code == 200, runbook_response.text
    runbook = runbook_response.json()
    assert runbook["current_body_markdown"] == (
        "# Runbook\n\nSee [Guide](./guides/Guide.md)\n\n![Diagram](./images/diagram.png)"
    )
    refs = {item["target"]: item for item in runbook["resolved_refs_json"]}
    assert refs["./guides/Guide.md"]["broken"] is False
    assert refs["./guides/Guide.md"]["resolved_node_id"] == items["guides/Guide.md"]["result_node_id"]
    assert refs["./images/diagram.png"]["broken"] is False
    assert refs["./images/diagram.png"]["resolved_node_id"] == items["images/diagram.png"]["result_node_id"]
    assert runbook["broken_refs_json"] == {"links": [], "assets": []}

    asset_response = await client.get(
        f"/api/wiki/assets/{items['images/diagram.png']['result_node_id']}/content",
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert asset_response.status_code == 200, asset_response.text
    assert asset_response.content == PNG_BYTES


@pytest.mark.asyncio
async def test_non_owner_cannot_apply_import_job(client: AsyncClient) -> None:
    space_id, parent_id = await _create_space_and_folder(client, slug="wiki-imports-apply-denied")

    create_response = await client.post(
        "/api/wiki/imports",
        data={"space_id": str(space_id), "parent_id": str(parent_id)},
        files=[("files", ("Runbook.md", b"# Runbook", "text/markdown"))],
        headers={"X-Subject-Id": "owner@dev-1"},
    )
    assert create_response.status_code == 201, create_response.text
    job_id = int(create_response.json()["id"])

    response = await client.post(
        f"/api/wiki/imports/{job_id}/apply",
        headers={"X-Subject-Id": "viewer@dev-9"},
    )

    assert response.status_code == 403, response.text
