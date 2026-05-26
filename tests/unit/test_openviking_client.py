import httpx
import pytest

from codeask.rag.openviking.client import OpenVikingClient
from codeask.rag.openviking.sync import SyncResource


@pytest.mark.asyncio
async def test_add_text_resource_uses_temp_upload_then_add_resource() -> None:
    requests: list[tuple[str, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/v1/resources/temp_upload":
            return httpx.Response(200, json={"status": "ok", "result": {"temp_file_id": "tmp_1"}})
        if request.url.path == "/api/v1/resources":
            body = request.read().decode()
            assert '"temp_file_id":"tmp_1"' in body
            assert '"to":"viking://resources/codeask/features/f/knowledge-base/doc.md"' in body
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "result": {
                        "task_id": "task_1",
                        "uri": "viking://resources/codeask/features/f/knowledge-base/doc.md",
                        "status": "queued",
                    },
                },
            )
        return httpx.Response(404)

    client = OpenVikingClient(
        base_url="http://openviking.local",
        transport=httpx.MockTransport(handler),
    )

    result = await client.add_text_resource(
        SyncResource(
            source_type="manual_text",
            source_id="doc_1",
            content="# Doc",
            filename="doc.md",
            viking_uri="viking://resources/codeask/features/f/knowledge-base/doc.md",
        )
    )

    assert result["task_id"] == "task_1"
    assert requests == [
        ("POST", "/api/v1/resources/temp_upload"),
        ("POST", "/api/v1/resources"),
    ]


@pytest.mark.asyncio
async def test_find_uses_rest_search_endpoint_and_parses_resources_envelope() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/search/find"
        body = request.read().decode()
        assert '"query":"marker"' in body
        assert '"target_uri":"viking://resources/codeask/features/f"' in body
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "result": {
                    "resources": [
                        {
                            "uri": "viking://resources/codeask/features/f/knowledge-base/doc.md/doc.md",
                            "score": 0.91,
                            "context_type": "resource",
                            "level": 2,
                            "abstract": "Doc abstract",
                        }
                    ],
                    "total": 1,
                },
            },
        )

    client = OpenVikingClient(
        base_url="http://openviking.local",
        transport=httpx.MockTransport(handler),
    )

    hits = await client.find(
        query="marker",
        target_uri="viking://resources/codeask/features/f",
        limit=5,
    )

    assert len(hits) == 1
    assert hits[0].uri.endswith("/doc.md/doc.md")
    assert hits[0].score == 0.91
    assert hits[0].abstract == "Doc abstract"


@pytest.mark.asyncio
async def test_delete_resource_uses_fs_delete_recursive_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        assert request.url.path == "/api/v1/fs"
        assert request.url.params["uri"] == "viking://resources/codeask/features/f/doc.md"
        assert request.url.params["recursive"] == "true"
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "result": {
                    "uri": "viking://resources/codeask/features/f/doc.md",
                    "estimated_deleted_count": 0,
                },
            },
        )

    client = OpenVikingClient(
        base_url="http://openviking.local",
        transport=httpx.MockTransport(handler),
    )

    result = await client.delete_resource("viking://resources/codeask/features/f/doc.md")

    assert result["uri"] == "viking://resources/codeask/features/f/doc.md"
