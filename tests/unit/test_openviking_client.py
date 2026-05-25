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
