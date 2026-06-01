import asyncio
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from openviking_cli.exceptions import NotFoundError, UnavailableError
from sqlalchemy import select

from codeask.rag.openviking.client import OpenVikingClient
from codeask.rag.openviking.models import OpenVikingDashboardEvent


class FakeAsyncHTTPClient:
    instances: list["FakeAsyncHTTPClient"] = []

    def __init__(
        self,
        *,
        url: str,
        account: str,
        user: str,
        agent_id: str,
        timeout: float,
    ) -> None:
        self.url = url
        self.account = account
        self.user = user
        self.agent_id = agent_id
        self.timeout = timeout
        self.initialized = False
        self.added_resources: list[dict[str, Any]] = []
        self.finds: list[dict[str, Any]] = []
        self.removes: list[dict[str, Any]] = []
        self.tasks: list[str] = []
        self.find_result: Any = {"resources": []}
        self.closed = False
        FakeAsyncHTTPClient.instances.append(self)

    async def initialize(self) -> None:
        self.initialized = True

    async def close(self) -> None:
        self.closed = True

    async def add_resource(
        self,
        *,
        path: str,
        to: str,
        reason: str,
        instruction: str,
        wait: bool = False,
        strict: bool = False,
        preserve_structure: bool | None = None,
    ) -> dict[str, Any]:
        path_obj = Path(path)
        if path_obj.is_dir():
            content = None
            files = sorted(
                item.relative_to(path_obj).as_posix()
                for item in path_obj.rglob("*")
                if item.is_file()
            )
        else:
            content = path_obj.read_text(encoding="utf-8")
            files = []
        self.added_resources.append(
            {
                "path": path,
                "to": to,
                "reason": reason,
                "instruction": instruction,
                "wait": wait,
                "strict": strict,
                "preserve_structure": preserve_structure,
                "content": content,
                "files": files,
            }
        )
        return {"uri": to, "status": "queued", "task_id": "task_1"}

    async def find(
        self,
        *,
        query: str,
        target_uri: str,
        limit: int,
        score_threshold: float | None,
    ) -> Any:
        self.finds.append(
            {
                "query": query,
                "target_uri": target_uri,
                "limit": limit,
                "score_threshold": score_threshold,
            }
        )
        return self.find_result

    async def rm(self, uri: str, *, recursive: bool = False) -> None:
        self.removes.append({"uri": uri, "recursive": recursive})

    async def get_task(self, task_id: str) -> dict[str, Any] | None:
        self.tasks.append(task_id)
        return {"task_id": task_id, "status": "indexed"}


@pytest.fixture(autouse=True)
def clear_fake_instances() -> None:
    FakeAsyncHTTPClient.instances.clear()


@pytest.mark.asyncio
async def test_add_wiki_feature_uses_official_http_sdk_add_resource_with_directory(
    tmp_path: Path,
) -> None:
    knowledge_base = tmp_path / "wiki_workspace" / "current" / "anything-llm" / "knowledge-base"
    knowledge_base.mkdir(parents=True)
    (knowledge_base / "index.md").write_text("# AnythingLLM", encoding="utf-8")
    (knowledge_base / "server").mkdir()
    (knowledge_base / "server" / "embedding.md").write_text("# Embedding", encoding="utf-8")
    client = OpenVikingClient(
        base_url="http://openviking.local/",
        timeout=12.5,
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    result = await client.add_wiki_feature(
        feature_slug="anything-llm",
        knowledge_base_path=knowledge_base,
    )

    assert result["task_id"] == "task_1"
    sdk = FakeAsyncHTTPClient.instances[0]
    assert sdk.url == "http://openviking.local"
    assert sdk.account == "codeask"
    assert sdk.user == "codeask"
    assert sdk.agent_id == "codeask"
    assert sdk.timeout == 12.5
    assert sdk.initialized is True
    assert len(sdk.added_resources) == 1
    added = sdk.added_resources[0]
    assert added == {
        "path": str(knowledge_base),
        "to": "viking://resources/codeask/wiki/anything-llm",
        "reason": "CodeAsk wiki feature sync anything-llm",
        "instruction": "Index this CodeAsk feature wiki knowledge base for semantic retrieval.",
        "wait": False,
        "strict": False,
        "preserve_structure": True,
        "content": None,
        "files": ["index.md", "server/embedding.md"],
    }


@pytest.mark.asyncio
async def test_add_wiki_feature_rejects_missing_knowledge_base(tmp_path: Path) -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local/",
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    with pytest.raises(ValueError, match="knowledge-base path does not exist"):
        await client.add_wiki_feature(
            feature_slug="anything-llm",
            knowledge_base_path=tmp_path / "missing",
        )


def test_sdk_client_is_not_reused_across_event_loops() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    first = asyncio.run(client.sdk_client())
    second = asyncio.run(client.sdk_client())

    assert first is not second
    assert len(FakeAsyncHTTPClient.instances) == 2


@pytest.mark.asyncio
async def test_close_closes_current_loop_sdk_client() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )
    sdk = await client.sdk_client()

    await client.close()

    assert sdk.closed is True


def test_close_does_not_close_sdk_clients_from_other_event_loops() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    async def create_and_close_current_loop_client() -> FakeAsyncHTTPClient:
        sdk = await client.sdk_client()
        await client.close()
        return sdk

    other_loop = asyncio.new_event_loop()
    try:
        first = other_loop.run_until_complete(client.sdk_client())

        second = asyncio.run(create_and_close_current_loop_client())

        assert first.closed is False
        assert second.closed is True
        assert len(FakeAsyncHTTPClient.instances) == 2
    finally:
        other_loop.run_until_complete(client.close())
        other_loop.close()


@pytest.mark.asyncio
async def test_find_uses_official_http_sdk_and_parses_resources_envelope() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )
    sdk = await client.sdk_client()
    sdk.find_result = {
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
    }

    hits = await client.find(
        query="marker",
        target_uri="viking://resources/codeask/features/f",
        limit=5,
    )

    assert sdk.finds == [
        {
            "query": "marker",
            "target_uri": "viking://resources/codeask/features/f",
            "limit": 5,
            "score_threshold": 0.0,
        }
    ]
    assert len(hits) == 1
    assert hits[0].uri.endswith("/doc.md/doc.md")
    assert hits[0].score == 0.91
    assert hits[0].abstract == "Doc abstract"


@pytest.mark.asyncio
async def test_find_parses_list_result_from_official_http_sdk() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )
    sdk = await client.sdk_client()
    sdk.find_result = [
        {
            "uri": "viking://resources/codeask/features/f/doc.md",
            "score": 0.72,
            "content": "matching body",
        }
    ]

    hits = await client.find(
        query="marker",
        target_uri="viking://resources/codeask/features/f",
    )

    assert len(hits) == 1
    assert hits[0].content == "matching body"
    assert hits[0].score == 0.72


@pytest.mark.asyncio
async def test_find_parses_find_result_object_from_official_http_sdk() -> None:
    class FakeFindResult:
        def to_dict(self) -> dict[str, Any]:
            return {
                "resources": [
                    {
                        "uri": "viking://resources/codeask/features/f/doc.md",
                        "score": 0.66,
                        "overview": "Doc overview",
                    }
                ]
            }

    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )
    sdk = await client.sdk_client()
    sdk.find_result = FakeFindResult()

    hits = await client.find(
        query="marker",
        target_uri="viking://resources/codeask/features/f",
    )

    assert len(hits) == 1
    assert hits[0].overview == "Doc overview"
    assert hits[0].score == 0.66


@pytest.mark.asyncio
async def test_delete_resource_uses_official_http_sdk_rm_recursive() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    result = await client.delete_resource("viking://resources/codeask/features/f/doc.md")

    sdk = FakeAsyncHTTPClient.instances[0]
    assert sdk.removes == [
        {"uri": "viking://resources/codeask/features/f/doc.md", "recursive": True}
    ]
    assert result == {"uri": "viking://resources/codeask/features/f/doc.md", "deleted": True}


@pytest.mark.asyncio
async def test_delete_resource_uses_not_found_error_type_for_missing_resource() -> None:
    class MissingResourceFakeAsyncHTTPClient(FakeAsyncHTTPClient):
        async def rm(self, uri: str, *, recursive: bool = False) -> None:
            self.removes.append({"uri": uri, "recursive": recursive})
            raise NotFoundError(uri, "file")

    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=MissingResourceFakeAsyncHTTPClient,
    )

    result = await client.delete_resource("viking://resources/codeask/features/f/missing.md")

    assert result == {
        "uri": "viking://resources/codeask/features/f/missing.md",
        "not_found": True,
    }


@pytest.mark.asyncio
async def test_sdk_unavailable_error_emits_breaker_event(app: FastAPI) -> None:
    class UnavailableFakeAsyncHTTPClient(FakeAsyncHTTPClient):
        async def find(
            self,
            *,
            query: str,
            target_uri: str,
            limit: int,
            score_threshold: float | None,
        ) -> Any:
            raise UnavailableError("breaker open")

    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=UnavailableFakeAsyncHTTPClient,
        session_factory=app.state.session_factory,
    )

    with pytest.raises(UnavailableError):
        await client.find(
            query="marker",
            target_uri="viking://resources/codeask/features/f",
        )

    async with app.state.session_factory() as session:
        events = (await session.execute(select(OpenVikingDashboardEvent))).scalars().all()

    assert len(events) == 1
    assert events[0].event_type == "openviking_breaker_tripped"
    assert events[0].outcome == "warning"
    assert events[0].payload["code"] == "UNAVAILABLE"
    assert "unavailable" in events[0].payload["detail"].lower()


@pytest.mark.asyncio
async def test_task_status_uses_official_http_sdk_get_task() -> None:
    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=FakeAsyncHTTPClient,
    )

    result = await client.task_status("task_1")

    sdk = FakeAsyncHTTPClient.instances[0]
    assert sdk.tasks == ["task_1"]
    assert result == {"task_id": "task_1", "status": "indexed"}


@pytest.mark.asyncio
async def test_task_status_returns_not_found_payload_when_sdk_returns_none() -> None:
    class MissingTaskFakeAsyncHTTPClient(FakeAsyncHTTPClient):
        async def get_task(self, task_id: str) -> dict[str, Any] | None:
            self.tasks.append(task_id)
            return None

    client = OpenVikingClient(
        base_url="http://openviking.local",
        sdk_client_factory=MissingTaskFakeAsyncHTTPClient,
    )

    result = await client.task_status("missing")

    assert result == {"task_id": "missing", "not_found": True}
