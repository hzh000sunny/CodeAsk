"""LLMGateway: factory dispatch + retry-before-first-token only."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from codeask.llm.client import LLMClient
from codeask.llm.gateway import LLMGateway
from codeask.llm.repo import LLMConfigRepo
from codeask.llm.types import LLMEvent, LLMMessage, LLMRequest, TextBlock, ToolDef

ClientBuilder = Callable[..., LLMClient]


class ClientFactory:
    """Test double for the gateway client factory.

    The production ClientFactory always builds a single LiteLLM client; tests
    inject scripted clients via a one-entry ``provider_clients`` mapping (the key
    is irrelevant now that protocol dispatch is gone).
    """

    def __init__(self, *, provider_clients: dict[str, ClientBuilder]) -> None:
        self._builder = next(iter(provider_clients.values()))

    def create(self, **kwargs: Any) -> LLMClient:
        return self._builder(**kwargs)


class _ScriptedClient:
    def __init__(self, scripts: list[list[LLMEvent]]) -> None:
        self._scripts = scripts
        self._idx = 0

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        _ = (messages, tools, max_tokens, temperature, metadata)
        script = self._scripts[self._idx]
        self._idx += 1
        for event in script:
            yield event


class _CapturingFactoryClient(_ScriptedClient):
    def __init__(self) -> None:
        super().__init__(
            [
                [
                    LLMEvent(type="message_start", data={}),
                    LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
                ]
            ]
        )
        self.kwargs: dict[str, object] = {}
        self.stream_kwargs: dict[str, object] = {}

    async def stream(
        self,
        messages: list[LLMMessage],
        tools: list[ToolDef],
        max_tokens: int,
        temperature: float,
        metadata: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMEvent]:
        self.stream_kwargs = {
            "messages": messages,
            "tools": tools,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "metadata": metadata,
        }
        async for event in super().stream(
            messages=messages,
            tools=tools,
            max_tokens=max_tokens,
            temperature=temperature,
            metadata=metadata,
        ):
            yield event


@dataclass(frozen=True)
class _Config:
    id: str
    mode: str = "catalog"
    provider_id: str = "openai"
    api_key: str = "x"
    base_url: str | None = None
    model_name: str = "m"
    headers: dict[str, str] = field(default_factory=dict)
    scope: str = "global"
    owner_subject_id: str | None = None
    is_default: bool = False
    enabled: bool = True
    reasoning_profile: str = "none"
    reasoning_profile_json: str | None = None


class _FakeRepo:
    def __init__(
        self,
        *,
        explicit_config: _Config | None = None,
        user_configs: list[_Config] | None = None,
        global_configs: list[_Config] | None = None,
    ) -> None:
        self.explicit_config = explicit_config or _Config(id="cfg")
        self.user_configs = user_configs or []
        self.global_configs = global_configs or [self.explicit_config]

    async def get_default_or(self, _id: str | None, *, subject_id: str | None = None) -> object:
        return self.explicit_config

    async def list_runtime_user_configs(self, subject_id: str) -> list[_Config]:
        return self.user_configs

    async def list_runtime_global_configs(self) -> list[_Config]:
        return self.global_configs


def _repo(repo: _FakeRepo) -> LLMConfigRepo:
    return cast(LLMConfigRepo, repo)


def _client_builder(callback: ClientBuilder) -> ClientBuilder:
    return callback


def _kwargs_client_builder(callback: Callable[..., LLMClient]) -> ClientBuilder:
    def build_client(**kwargs: Any) -> LLMClient:
        return callback(**kwargs)

    return build_client


def _scripted_client_builder(client: LLMClient) -> ClientBuilder:
    def build_client(**kwargs: Any) -> LLMClient:
        _ = kwargs
        return client

    return build_client


def _request(
    *,
    subject_id: str | None = None,
    session_id: str | None = None,
    config_id: str | None = None,
    runtime_llm_config: dict[str, Any] | None = None,
) -> LLMRequest:
    metadata: dict[str, Any] = {}
    if subject_id is not None:
        metadata["subject_id"] = subject_id
    if session_id is not None:
        metadata["session_id"] = session_id
    if runtime_llm_config is not None:
        metadata["runtime_llm_config"] = runtime_llm_config
    return LLMRequest(
        config_id=config_id,
        messages=[LLMMessage(role="user", content=[TextBlock(type="text", text="hi")])],
        max_tokens=100,
        temperature=0.0,
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_retry_when_error_before_first_token() -> None:
    bad = LLMEvent(type="error", data={"retryable": True, "message": "transient"})
    good = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": "ok"}),
        LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
    ]
    client = _ScriptedClient([[bad], good])

    factory = ClientFactory(provider_clients={"openai": _scripted_client_builder(client)})
    gateway = LLMGateway(_repo(_FakeRepo()), factory, base_delay=0.0)
    out = [event async for event in gateway.stream(_request())]
    assert out[-1].data["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_no_retry_after_first_token() -> None:
    partial = [
        LLMEvent(type="message_start", data={}),
        LLMEvent(type="text_delta", data={"delta": "abc"}),
        LLMEvent(type="error", data={"retryable": True, "message": "stream cut"}),
    ]
    client = _ScriptedClient([partial])

    factory = ClientFactory(provider_clients={"openai": _scripted_client_builder(client)})
    gateway = LLMGateway(_repo(_FakeRepo()), factory, base_delay=0.0)
    out = [event async for event in gateway.stream(_request())]
    assert out[-1].type == "error"


@pytest.mark.asyncio
async def test_gateway_passes_timeout_to_client_factory() -> None:
    client = _CapturingFactoryClient()

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        client.kwargs = kwargs
        return client

    factory = ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)})
    gateway = LLMGateway(_repo(_FakeRepo()), factory, timeout_seconds=600, base_delay=0.0)
    _ = [event async for event in gateway.stream(_request())]
    assert client.kwargs["timeout_seconds"] == 600


@pytest.mark.asyncio
async def test_gateway_passes_reasoning_profile_to_client_factory() -> None:
    client = _CapturingFactoryClient()

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        client.kwargs = kwargs
        return client

    repo = _FakeRepo(
        explicit_config=_Config(
            id="cfg_reasoning",
            reasoning_profile="custom_json",
            reasoning_profile_json='{"extra_body":{"include_reasoning":true}}',
        )
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
    )

    _ = [event async for event in gateway.stream(_request(config_id="cfg_reasoning"))]

    assert client.kwargs["reasoning_request_profile"] == "custom_json"
    assert client.kwargs["reasoning_request_profile_json"] == (
        '{"extra_body":{"include_reasoning":true}}'
    )


@pytest.mark.asyncio
async def test_gateway_passes_request_metadata_to_client_stream() -> None:
    client = _CapturingFactoryClient()

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        client.kwargs = kwargs
        return client

    gateway = LLMGateway(
        _repo(_FakeRepo()),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    request = _request(subject_id="alice", session_id="sess_meta")
    request.metadata["reasoning_history"] = {
        "mode": "openai_interleaved",
        "field": "reasoning_content",
    }

    _ = [event async for event in gateway.stream(request)]

    assert client.stream_kwargs["metadata"] == request.metadata


@pytest.mark.asyncio
async def test_gateway_uses_runtime_llm_config_without_persisted_repo_lookup() -> None:
    client = _CapturingFactoryClient()

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        client.kwargs = kwargs
        return client

    repo = _FakeRepo(
        user_configs=[_Config(id="user_cfg", model_name="user-model", scope="user")],
        global_configs=[_Config(id="global_cfg", model_name="global-model")],
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"anthropic": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(
                subject_id="client_guest",
                session_id="sess_guest",
                runtime_llm_config={
                    "name": "访客模型",
                    "mode": "catalog",
                    "provider_id": "anthropic",
                    "base_url": "http://guest.llm/v1",
                    "api_key": "sk-guest",
                    "model_name": "guest-model",
                    "reasoning_profile": "custom_json",
                    "reasoning_profile_json": '{"thinking":true}',
                },
            )
        )
    ]

    assert out[-1].type == "message_stop"
    assert client.kwargs["api_key"] == "sk-guest"
    assert client.kwargs["base_url"] == "http://guest.llm/v1"
    assert client.kwargs["model_name"] == "guest-model"
    assert client.kwargs["reasoning_request_profile"] == "custom_json"
    assert client.kwargs["reasoning_request_profile_json"] == '{"thinking":true}'


@pytest.mark.asyncio
async def test_gateway_prefers_enabled_user_config_over_global_pool() -> None:
    clients: dict[str, _CapturingFactoryClient] = {}

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        client = _CapturingFactoryClient()
        client.kwargs = kwargs
        clients[str(kwargs["model_name"])] = client
        return client

    repo = _FakeRepo(
        user_configs=[_Config(id="user_cfg", model_name="user-model", scope="user")],
        global_configs=[_Config(id="global_cfg", model_name="global-model")],
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
    )

    _ = [
        event
        async for event in gateway.stream(_request(subject_id="alice@dev", session_id="sess_user"))
    ]

    assert "user-model" in clients
    assert "global-model" not in clients


@pytest.mark.asyncio
async def test_gateway_does_not_fallback_when_user_config_fails() -> None:
    selected_models: list[str] = []
    bad = LLMEvent(type="error", data={"retryable": False, "message": "user config failed"})

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "user-model":
            return _ScriptedClient([[bad]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        user_configs=[_Config(id="user_cfg", model_name="user-model", scope="user")],
        global_configs=[_Config(id="global_cfg", model_name="global-model")],
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_user_fail")
        )
    ]

    assert selected_models == ["user-model"]
    assert out[-1].type == "error"
    assert "user config failed" in str(out[-1].data["message"])


@pytest.mark.asyncio
async def test_gateway_does_not_fallback_when_explicit_config_fails() -> None:
    selected_models: list[str] = []
    bad = LLMEvent(type="error", data={"retryable": False, "message": "explicit failed"})

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "explicit-model":
            return _ScriptedClient([[bad]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        explicit_config=_Config(id="explicit_cfg", model_name="explicit-model"),
        global_configs=[_Config(id="global_cfg", model_name="global-model")],
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(
                subject_id="alice@dev",
                session_id="sess_explicit_fail",
                config_id="explicit_cfg",
            )
        )
    ]

    assert selected_models == ["explicit-model"]
    assert out[-1].type == "error"
    assert "explicit failed" in str(out[-1].data["message"])


@pytest.mark.asyncio
async def test_gateway_does_not_limit_global_config_parallel_sessions() -> None:
    selected_models: list[str] = []

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        selected_models.append(str(kwargs["model_name"]))
        return _CapturingFactoryClient()

    repo = _FakeRepo(global_configs=[_Config(id="global_cfg", model_name="global-model")])
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    for session_id in ["sess_1", "sess_2", "sess_3", "sess_4"]:
        out = [
            event
            async for event in gateway.stream(
                _request(subject_id="alice@dev", session_id=session_id)
            )
        ]
        assert out[-1].type == "message_stop"

    assert selected_models == ["global-model"] * 4


@pytest.mark.asyncio
async def test_gateway_counts_same_session_once_per_window() -> None:
    selected_models: list[str] = []

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        selected_models.append(str(kwargs["model_name"]))
        return _CapturingFactoryClient()

    repo = _FakeRepo(global_configs=[_Config(id="global_cfg", model_name="global-model")])
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        base_delay=0.0,
    )

    for session_id in ["sess_1", "sess_1", "sess_1", "sess_2", "sess_3"]:
        out = [
            event
            async for event in gateway.stream(
                _request(subject_id="alice@dev", session_id=session_id)
            )
        ]
        assert out[-1].type == "message_stop"

    out = [
        event
        async for event in gateway.stream(_request(subject_id="alice@dev", session_id="sess_4"))
    ]

    assert selected_models == ["global-model"] * 6
    assert out[-1].type == "message_stop"


@pytest.mark.asyncio
async def test_gateway_keeps_session_sticky_on_previous_global_config() -> None:
    clients: list[str] = []

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        clients.append(str(kwargs["model_name"]))
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
    )

    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_sticky")
        )
    ]
    gateway._global_usage.record_session("cfg_a", "other_1")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "other_2")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "other_3")  # pyright: ignore[reportPrivateUsage]
    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_sticky")
        )
    ]

    assert clients == ["model-a", "model-a"]


@pytest.mark.asyncio
async def test_gateway_drops_sticky_global_config_after_five_minutes() -> None:
    now = 1000.0

    def monotonic() -> float:
        return now

    clients: list[str] = []

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        clients.append(str(kwargs["model_name"]))
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        monotonic=monotonic,
        random_choice=lambda configs: configs[0],
    )

    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_sticky")
        )
    ]
    now += 301
    gateway._global_usage.record_session("cfg_a", "other_1")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "other_2")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "other_3")  # pyright: ignore[reportPrivateUsage]
    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_sticky")
        )
    ]

    assert clients == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_gateway_switches_when_sticky_config_disappears_from_pool() -> None:
    clients: list[str] = []

    def build_client(**kwargs: object) -> _CapturingFactoryClient:
        clients.append(str(kwargs["model_name"]))
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
    )

    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_deleted_sticky")
        )
    ]
    repo.global_configs = [_Config(id="cfg_b", model_name="model-b")]
    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_deleted_sticky")
        )
    ]

    assert clients == ["model-a", "model-b"]


@pytest.mark.asyncio
async def test_gateway_temporarily_removes_repeatedly_failing_global_config() -> None:
    now = 1000.0

    def monotonic() -> float:
        return now

    bad = LLMEvent(type="error", data={"retryable": False, "message": "bad provider"})
    selected_models: list[str] = []

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient([[bad], [bad], [bad]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        monotonic=monotonic,
        random_choice=lambda configs: configs[0],
        unhealthy_failure_threshold=3,
        unhealthy_window_seconds=300,
        unhealthy_cooldown_seconds=600,
        base_delay=0.0,
    )

    for session_id in ["sess_fail_1", "sess_fail_2", "sess_fail_3"]:
        _ = [
            event
            async for event in gateway.stream(
                _request(subject_id="alice@dev", session_id=session_id)
            )
        ]

    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_after_fail")
        )
    ]
    now += 599
    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_during_cooldown")
        )
    ]
    now += 2
    _ = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_after_cooldown")
        )
    ]

    assert selected_models == [
        "model-a",
        "model-b",
        "model-a",
        "model-b",
        "model-a",
        "model-b",
        "model-b",
        "model-b",
        "model-a",
        "model-b",
    ]


@pytest.mark.asyncio
async def test_gateway_switches_to_next_global_config_after_initial_failure() -> None:
    selected_models: list[str] = []
    bad = LLMEvent(type="error", data={"retryable": True, "message": "temporary fail"})

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient([[bad]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_switch")
        )
    ]

    assert selected_models == ["model-a", "model-b"]
    assert out[-1].type == "message_stop"


@pytest.mark.asyncio
async def test_gateway_does_not_cool_down_config_for_context_length_errors() -> None:
    selected_models: list[str] = []
    context_error = LLMEvent(
        type="error",
        data={
            "retryable": False,
            "error_code": "BadRequestError",
            "message": "Input length exceeds the maximum length",
        },
    )

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient([[context_error], [context_error], [context_error]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
        unhealthy_failure_threshold=3,
        base_delay=0.0,
    )

    for _ in range(3):
        out = [
            event
            async for event in gateway.stream(
                _request(subject_id="alice@dev", session_id="sess_ctx_same")
            )
        ]
        assert out[-1].type == "error"

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_ctx_same")
        )
    ]

    assert selected_models == ["model-a", "model-a", "model-a", "model-a"]
    assert out[-1].type == "error"
    assert "Input length" in str(out[-1].data["message"])


@pytest.mark.asyncio
async def test_gateway_does_not_cool_down_config_for_nested_context_length_errors() -> None:
    selected_models: list[str] = []
    context_error = LLMEvent(
        type="error",
        data={
            "backend": "opencode",
            "error": {
                "name": "BadRequestError",
                "data": {"message": "Input length exceeds the maximum length"},
            },
        },
    )

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient([[context_error], [context_error], [context_error]])
        return _CapturingFactoryClient()

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
        unhealthy_failure_threshold=3,
        base_delay=0.0,
    )

    for _ in range(3):
        out = [
            event
            async for event in gateway.stream(
                _request(subject_id="alice@dev", session_id="sess_nested_ctx_same")
            )
        ]
        assert out[-1].type == "error"

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_nested_ctx_same")
        )
    ]

    assert selected_models == ["model-a", "model-a", "model-a", "model-a"]
    assert out[-1].type == "error"


@pytest.mark.asyncio
async def test_gateway_returns_last_error_when_all_global_candidates_fail() -> None:
    selected_models: list[str] = []

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient(
                [[LLMEvent(type="error", data={"retryable": False, "message": "a failed"})]]
            )
        return _ScriptedClient(
            [[LLMEvent(type="error", data={"retryable": False, "message": "b failed"})]]
        )

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_all_fail")
        )
    ]

    assert selected_models == ["model-a", "model-b"]
    assert out[-1].type == "error"
    assert "b failed" in str(out[-1].data["message"])


@pytest.mark.asyncio
async def test_gateway_rotates_global_config_for_nested_opencode_api_error() -> None:
    selected_models: list[str] = []

    def build_client(**kwargs: object) -> _ScriptedClient:
        selected_models.append(str(kwargs["model_name"]))
        if kwargs["model_name"] == "model-a":
            return _ScriptedClient(
                [
                    [
                        LLMEvent(
                            type="error",
                            data={
                                "backend": "opencode",
                                "error": {
                                    "name": "APIError",
                                    "data": {
                                        "message": (
                                            "InvalidSubscription: account has no valid plan"
                                        )
                                    },
                                },
                            },
                        )
                    ]
                ]
            )
        return _ScriptedClient(
            [
                [
                    LLMEvent(type="message_start", data={}),
                    LLMEvent(type="text_delta", data={"delta": "ok"}),
                    LLMEvent(type="message_stop", data={"stop_reason": "end_turn"}),
                ]
            ]
        )

    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(provider_clients={"openai": _kwargs_client_builder(build_client)}),
        random_choice=lambda configs: configs[0],
        base_delay=0.0,
    )

    out = [
        event
        async for event in gateway.stream(
            _request(subject_id="alice@dev", session_id="sess_nested_opencode_error")
        )
    ]

    assert selected_models == ["model-a", "model-b"]
    assert out[-1].type == "message_stop"


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_uses_random_choice_among_least_busy_ties() -> None:
    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(
                id="cfg_b",
                model_name="model-b",
                reasoning_profile="custom_json",
                reasoning_profile_json='{"x":true}',
            ),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
        random_choice=lambda configs: configs[1],
    )

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_opencode_select",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_b"
    assert selection.config.model_name == "model-b"
    assert selection.config.reasoning_profile == "custom_json"
    assert selection.pooled_global is True


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_uses_least_busy_global_config() -> None:
    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(
                id="cfg_b",
                model_name="model-b",
                reasoning_profile="custom_json",
                reasoning_profile_json='{"x":true}',
            ),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
        random_choice=lambda configs: configs[0],
    )

    gateway._global_usage.record_session("cfg_a", "sess_a1")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "sess_a2")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_b", "sess_b1")  # pyright: ignore[reportPrivateUsage]

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_new",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_b"
    assert selection.config.model_name == "model-b"
    assert selection.config.reasoning_profile == "custom_json"
    assert selection.pooled_global is True


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_keeps_selecting_when_pool_has_no_limit() -> None:
    repo = _FakeRepo(global_configs=[_Config(id="cfg_a", model_name="model-a")])
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
    )

    for session_id in ["sess_1", "sess_2", "sess_3"]:
        selection = await gateway.select_runtime_config(
            config_id=None,
            subject_id="alice@dev",
            session_id=session_id,
        )
        assert not isinstance(selection, LLMEvent)

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_4",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_a"
    assert selection.pooled_global is True


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_uses_single_unhealthy_global_config() -> None:
    repo = _FakeRepo(global_configs=[_Config(id="cfg_a", model_name="model-a")])
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
        unhealthy_failure_threshold=1,
    )
    gateway._global_usage.record_failure("cfg_a")  # pyright: ignore[reportPrivateUsage]

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_after_unhealthy",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_a"
    assert selection.pooled_global is True


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_prefers_healthy_over_unhealthy_config() -> None:
    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
        unhealthy_failure_threshold=1,
    )
    gateway._global_usage.record_failure("cfg_a")  # pyright: ignore[reportPrivateUsage]

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_with_healthy_candidate",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_b"
    assert selection.pooled_global is True


@pytest.mark.asyncio
async def test_gateway_select_runtime_config_uses_least_busy_when_all_configs_unhealthy() -> None:
    repo = _FakeRepo(
        global_configs=[
            _Config(id="cfg_a", model_name="model-a"),
            _Config(id="cfg_b", model_name="model-b"),
        ]
    )
    gateway = LLMGateway(
        _repo(repo),
        ClientFactory(
            provider_clients={"openai": _scripted_client_builder(_CapturingFactoryClient())}
        ),
        unhealthy_failure_threshold=1,
        random_choice=lambda configs: configs[0],
    )
    gateway._global_usage.record_failure("cfg_a")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_failure("cfg_b")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "sess_a1")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_a", "sess_a2")  # pyright: ignore[reportPrivateUsage]
    gateway._global_usage.record_session("cfg_b", "sess_b1")  # pyright: ignore[reportPrivateUsage]

    selection = await gateway.select_runtime_config(
        config_id=None,
        subject_id="alice@dev",
        session_id="sess_all_unhealthy",
    )

    assert not isinstance(selection, LLMEvent)
    assert selection.config.id == "cfg_b"
    assert selection.pooled_global is True
