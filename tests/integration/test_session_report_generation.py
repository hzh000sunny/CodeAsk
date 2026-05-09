"""Integration tests for session-generated report drafting and saving."""

import asyncio
from datetime import date

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select

from codeask.db.models import AgentTrace, Report, SessionTurn, WikiNode, WikiReportRef, WikiSpace
from codeask.llm.types import LLMEvent
from codeask.wiki.sync import LegacyWikiSyncService
from tests.mocks.mock_llm import MockLLMClient, text_message


async def _create_default_llm_config(client: AsyncClient) -> None:
    login = await client.post("/api/auth/admin/login", json={"password": "admin"})
    assert login.status_code == 200
    config = await client.post(
        "/api/admin/llm-configs",
        json={
            "name": "default",
            "protocol": "openai",
            "base_url": None,
            "api_key": "sk-secret",
            "model_name": "gpt-test",
            "max_tokens": 1024,
            "temperature": 0.0,
            "is_default": True,
        },
    )
    assert config.status_code == 201, config.text
    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204


async def _create_feature(client: AsyncClient, *, name: str = "Payment") -> int:
    feature = await client.post(
        "/api/features",
        json={"name": name, "description": f"{name} feature"},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert feature.status_code == 201, feature.text
    return int(feature.json()["id"])


async def _create_session(client: AsyncClient, *, title: str = "支付启动失败") -> str:
    created = await client.post(
        "/api/sessions",
        json={"title": title},
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert created.status_code == 201, created.text
    return str(created.json()["id"])


async def _seed_turns(app: FastAPI, session_id: str) -> None:
    async with app.state.session_factory() as db:
        db.add_all(
            [
                SessionTurn(
                    id=f"{session_id}_user",
                    session_id=session_id,
                    turn_index=0,
                    role="user",
                    content="支付服务启动失败，启动阶段报缺失配置。",
                    evidence=None,
                ),
                SessionTurn(
                    id=f"{session_id}_agent",
                    session_id=session_id,
                    turn_index=1,
                    role="agent",
                    content="初步判断和配置缺失有关，建议先生成正式报告草稿。",
                    evidence=None,
                ),
            ]
        )
        await db.commit()


async def _seed_scope_trace(app: FastAPI, session_id: str, feature_id: int) -> None:
    async with app.state.session_factory() as db:
        db.add(
            AgentTrace(
                id=f"{session_id}_scope",
                session_id=session_id,
                turn_id=f"{session_id}_user",
                stage="scope_detection",
                event_type="scope_decision",
                payload={
                    "output": {
                        "feature_ids": [feature_id],
                        "confidence": 0.91,
                        "reason": "命中特性",
                    }
                },
            )
        )
        await db.commit()


async def _seed_duplicate_session_reports(
    app: FastAPI,
    session_id: str,
    *,
    feature_id: int,
) -> tuple[int, int]:
    async with app.state.session_factory() as db:
        legacy = Report(
            feature_id=feature_id,
            session_id=None,
            title="旧版会话报告",
            body_markdown="# 旧版",
            metadata_json={"source": "session", "session_id": session_id},
            status="draft",
            verified=False,
            created_by_subject_id="alice@dev-1",
        )
        current = Report(
            feature_id=feature_id,
            session_id=session_id,
            title="当前会话报告",
            body_markdown="# 当前",
            metadata_json={"source": "session", "session_id": session_id},
            status="draft",
            verified=False,
            created_by_subject_id="alice@dev-1",
        )
        db.add_all([legacy, current])
        await db.flush()
        sync_service = LegacyWikiSyncService()
        await sync_service.sync_report_ref(
            db,
            report_id=int(legacy.id),
            feature_id=feature_id,
            title=legacy.title,
        )
        await sync_service.sync_report_ref(
            db,
            report_id=int(current.id),
            feature_id=feature_id,
            title=current.title,
        )
        await db.commit()
        return int(legacy.id), int(current.id)


async def _seed_retrieval_trace_with_catalog_noise(
    app: FastAPI,
    session_id: str,
    *,
    catalog_feature_id: int,
    hit_feature_id: int,
) -> None:
    async with app.state.session_factory() as db:
        db.add_all(
            [
                AgentTrace(
                    id=f"{session_id}_catalog",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="context_preparation",
                    event_type="retrieval_context",
                    payload={
                        "feature_catalog": [
                            {
                                "feature_id": catalog_feature_id,
                                "name": "GLM-5.1 端到端调试 20260502-194633",
                            }
                        ],
                        "feature_knowledge_index": [
                            {
                                "feature_id": catalog_feature_id,
                                "wiki_count": 8,
                            }
                        ],
                    },
                ),
                AgentTrace(
                    id=f"{session_id}_wiki_hit",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="context_preparation",
                    event_type="retrieval_context",
                    payload={
                        "feature_candidates": [
                            {
                                "feature_id": hit_feature_id,
                                "name": "小米",
                                "score": 0.93,
                            }
                        ],
                        "wiki_hits": [
                            {
                                "feature_id": hit_feature_id,
                                "title": "小米病历",
                                "path": "knowledge-base/小米病历",
                            }
                        ],
                    },
                ),
                AgentTrace(
                    id=f"{session_id}_tool_evidence",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="tool_use",
                    event_type="tool_result",
                    payload={
                        "summary": "读取 Wiki：小米病历",
                        "evidence_refs": [
                            {
                                "title": "小米病历",
                                "metadata": {
                                    "feature_id": hit_feature_id,
                                    "path": "knowledge-base/小米病历",
                                },
                            }
                        ],
                    },
                ),
            ]
        )
        await db.commit()


async def _seed_retrieval_trace_with_weak_candidate_before_strong_hit(
    app: FastAPI,
    session_id: str,
    *,
    candidate_feature_id: int,
    hit_feature_id: int,
) -> None:
    async with app.state.session_factory() as db:
        db.add_all(
            [
                AgentTrace(
                    id=f"{session_id}_candidate",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="context_preparation",
                    event_type="retrieval_context",
                    payload={
                        "feature_candidates": [
                            {
                                "feature_id": candidate_feature_id,
                                "name": "候选但未命中的特性",
                                "score": 0.51,
                            }
                        ],
                    },
                ),
                AgentTrace(
                    id=f"{session_id}_hit",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="context_preparation",
                    event_type="retrieval_context",
                    payload={
                        "wiki_hits": [
                            {
                                "feature_id": hit_feature_id,
                                "title": "小米病历",
                                "path": "knowledge-base/小米病历",
                            },
                            {
                                "feature_id": hit_feature_id,
                                "title": "小米治疗记录",
                                "path": "knowledge-base/小米治疗记录",
                            },
                        ],
                    },
                ),
                AgentTrace(
                    id=f"{session_id}_hit_tool",
                    session_id=session_id,
                    turn_id=f"{session_id}_user",
                    stage="tool_use",
                    event_type="tool_result",
                    payload={
                        "summary": "读取 Wiki：小米病历",
                        "evidence_refs": [
                            {
                                "title": "小米病历",
                                "metadata": {
                                    "feature_id": hit_feature_id,
                                    "path": "knowledge-base/小米病历",
                                },
                            }
                        ],
                    },
                ),
            ]
        )
        await db.commit()


async def _wait_prepare_status(
    client: AsyncClient,
    session_id: str,
    request_id: str,
    *,
    subject_id: str = "alice@dev-1",
) -> dict[str, object]:
    for _ in range(20):
        response = await client.get(
            f"/api/sessions/{session_id}/reports/prepare/{request_id}",
            headers={"X-Subject-Id": subject_id},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        if payload["status"] != "running":
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError("report prepare task did not finish")


@pytest.mark.asyncio
async def test_prepare_session_report_calls_llm_with_report_rules(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"支付服务启动失败","body_markdown":"# 问题背景\\n\\n支付服务启动失败。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": feature_id},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    start_payload = started.json()
    assert start_payload["status"] == "running"
    request_id = str(start_payload["request_id"])

    payload = await _wait_prepare_status(client, session_id, request_id)
    assert payload["status"] == "succeeded"
    draft = payload["draft"]
    assert draft["feature_id"] == feature_id
    assert draft["existing_report_id"] is None
    assert draft["title"] == f"{date.today().isoformat()} 支付服务启动失败"
    assert draft["body_markdown"].startswith("# 问题背景")

    prompt_text = "\n".join(
        block["text"]
        for message in mock.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "报告不是聊天记录副本" in prompt_text
    assert "已确认事实" in prompt_text
    assert "未确认项" in prompt_text


@pytest.mark.asyncio
async def test_prepare_session_report_infers_feature_from_scope_trace(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)
    await _seed_scope_trace(app, session_id, feature_id)

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"支付服务启动失败","body_markdown":"# 问题背景\\n\\n支付服务启动失败。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": None},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    payload = await _wait_prepare_status(
        client,
        session_id,
        str(started.json()["request_id"]),
    )
    assert payload["status"] == "succeeded"
    draft = payload["draft"]
    assert draft["feature_id"] == feature_id
    assert draft["inferred_feature_ids"] == [feature_id]

    prompt_text = "\n".join(
        block["text"]
        for message in mock.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "当前建议绑定特性：Payment" in prompt_text


@pytest.mark.asyncio
async def test_prepare_session_report_ignores_feature_catalog_when_inferring_feature(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    catalog_feature_id = await _create_feature(
        client,
        name="GLM-5.1 端到端调试 20260502-194633",
    )
    hit_feature_id = await _create_feature(client, name="小米")
    session_id = await _create_session(client, title="新的研发会话")
    await _seed_turns(app, session_id)
    await _seed_retrieval_trace_with_catalog_noise(
        app,
        session_id,
        catalog_feature_id=catalog_feature_id,
        hit_feature_id=hit_feature_id,
    )

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"小米病历查询端到端调试","body_markdown":"# 问题背景\\n\\n基于小米病历查询生成报告。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": None},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    payload = await _wait_prepare_status(
        client,
        session_id,
        str(started.json()["request_id"]),
    )
    assert payload["status"] == "succeeded"
    draft = payload["draft"]
    assert draft["feature_id"] == hit_feature_id
    assert draft["inferred_feature_ids"] == [hit_feature_id]

    prompt_text = "\n".join(
        block["text"]
        for message in mock.calls[0]["messages"]
        for block in message["content"]
        if block["type"] == "text"
    )
    assert "当前建议绑定特性：小米" in prompt_text
    assert "当前建议绑定特性：GLM-5.1" not in prompt_text


@pytest.mark.asyncio
async def test_prepare_session_report_prefers_strong_evidence_over_first_candidate(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    candidate_feature_id = await _create_feature(client, name="弱候选特性")
    hit_feature_id = await _create_feature(client, name="小米")
    session_id = await _create_session(client, title="小米病情变化")
    await _seed_turns(app, session_id)
    await _seed_retrieval_trace_with_weak_candidate_before_strong_hit(
        app,
        session_id,
        candidate_feature_id=candidate_feature_id,
        hit_feature_id=hit_feature_id,
    )

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"小米病情变化","body_markdown":"# 问题背景\\n\\n小米病情变化分析。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": None},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    payload = await _wait_prepare_status(
        client,
        session_id,
        str(started.json()["request_id"]),
    )
    assert payload["status"] == "succeeded"
    draft = payload["draft"]
    assert draft["feature_id"] == hit_feature_id
    assert draft["inferred_feature_ids"][0] == hit_feature_id
    assert candidate_feature_id in draft["inferred_feature_ids"]


@pytest.mark.asyncio
async def test_prepare_session_report_prefers_current_evidence_over_existing_wrong_binding(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    wrong_feature_id = await _create_feature(client, name="Browser Smoke")
    hit_feature_id = await _create_feature(client, name="AnythingLLM Reference")
    session_id = await _create_session(client, title="AnythingLLM 文档摄入分析")
    await _seed_turns(app, session_id)
    await _seed_retrieval_trace_with_weak_candidate_before_strong_hit(
        app,
        session_id,
        candidate_feature_id=wrong_feature_id,
        hit_feature_id=hit_feature_id,
    )
    existing = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": wrong_feature_id,
            "title": f"{date.today().isoformat()} 错误绑定的旧报告",
            "body_markdown": "# 旧报告",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert existing.status_code == 201, existing.text

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"AnythingLLM 文档摄入分析","body_markdown":"# 问题背景\\n\\n分析 AnythingLLM 文档摄入流程。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": None},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    payload = await _wait_prepare_status(
        client,
        session_id,
        str(started.json()["request_id"]),
    )
    assert payload["status"] == "succeeded"
    draft = payload["draft"]
    assert draft["existing_report_id"] == existing.json()["id"]
    assert draft["feature_id"] == hit_feature_id
    assert draft["inferred_feature_ids"][0] == hit_feature_id


@pytest.mark.asyncio
async def test_prepare_session_report_status_records_error_detail_when_llm_fails(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)

    mock = MockLLMClient(
        [
            [
                LLMEvent(
                    type="error",
                    data={
                        "provider": "openai",
                        "error_code": "TimeoutError",
                        "message": "upstream timed out",
                        "retryable": False,
                    },
                )
            ]
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": feature_id},
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert started.status_code == 200, started.text
    payload = await _wait_prepare_status(
        client,
        session_id,
        str(started.json()["request_id"]),
    )
    assert payload["status"] == "failed"
    assert "报告草稿生成失败" in str(payload["error"])
    assert "upstream timed out" in str(payload["error"])


@pytest.mark.asyncio
async def test_prepare_session_report_echoes_request_id_header(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"支付服务启动失败","body_markdown":"# 问题背景\\n\\n支付服务启动失败。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{session_id}/reports/prepare",
        json={"feature_id": feature_id},
        headers={
            "X-Subject-Id": "alice@dev-1",
            "X-CodeAsk-Request-Id": "req_prepare_123",
        },
    )

    assert started.status_code == 200, started.text
    assert started.headers["X-CodeAsk-Request-Id"] == "req_prepare_123"
    assert started.json()["request_id"] == "req_prepare_123"
    assert started.json()["status"] == "running"

    payload = await _wait_prepare_status(client, session_id, "req_prepare_123")

    assert payload["status"] == "succeeded"
    assert payload["request_id"] == "req_prepare_123"
    assert payload["draft"]["title"] == f"{date.today().isoformat()} 支付服务启动失败"


@pytest.mark.asyncio
async def test_prepare_session_report_status_is_scoped_to_session(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    await _create_default_llm_config(client)
    feature_id = await _create_feature(client)
    first_session_id = await _create_session(client, title="支付启动失败")
    second_session_id = await _create_session(client, title="库存启动失败")
    await _seed_turns(app, first_session_id)

    mock = MockLLMClient(
        [
            text_message(
                '{"title_description":"支付服务启动失败","body_markdown":"# 问题背景\\n\\n支付服务启动失败。"}'
            )
        ]
    )
    app.state.llm_gateway.client_factory.provider_clients["openai"] = lambda **_: mock

    started = await client.post(
        f"/api/sessions/{first_session_id}/reports/prepare",
        json={"feature_id": feature_id},
        headers={
            "X-Subject-Id": "alice@dev-1",
            "X-CodeAsk-Request-Id": "req_prepare_shared",
        },
    )
    assert started.status_code == 200, started.text

    cross_session_status = await client.get(
        f"/api/sessions/{second_session_id}/reports/prepare/req_prepare_shared",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert cross_session_status.status_code == 404

    payload = await _wait_prepare_status(
        client,
        first_session_id,
        "req_prepare_shared",
    )
    assert payload["status"] == "succeeded"


@pytest.mark.asyncio
async def test_save_session_report_updates_existing_report_instead_of_creating_new_one(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)

    first = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": f"{date.today().isoformat()} 支付服务启动失败",
            "body_markdown": "# 第一版",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    second = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": f"{date.today().isoformat()} 支付服务启动失败",
            "body_markdown": "# 第二版",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["body_markdown"] == "# 第二版"

    async with app.state.session_factory() as db:
        reports = (await db.execute(select(Report).order_by(Report.id))).scalars().all()
        assert len(reports) == 1


@pytest.mark.asyncio
async def test_session_report_survives_session_delete(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    feature_id = await _create_feature(client)
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)

    saved = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": feature_id,
            "title": f"{date.today().isoformat()} 支付服务启动失败",
            "body_markdown": "# 正式报告",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert saved.status_code == 201, saved.text
    report_id = int(saved.json()["id"])

    deleted = await client.delete(
        f"/api/sessions/{session_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert deleted.status_code == 204

    report = await client.get(
        f"/api/reports/{report_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert report.status_code == 200, report.text
    assert report.json()["id"] == report_id


@pytest.mark.asyncio
async def test_save_session_report_removes_legacy_duplicate_when_rebinding_feature(
    app: FastAPI,
    client: AsyncClient,
) -> None:
    old_feature_id = await _create_feature(client, name="旧特性")
    new_feature_id = await _create_feature(client, name="新特性")
    session_id = await _create_session(client)
    await _seed_turns(app, session_id)
    legacy_report_id, current_report_id = await _seed_duplicate_session_reports(
        app,
        session_id,
        feature_id=old_feature_id,
    )

    saved = await client.post(
        f"/api/sessions/{session_id}/reports",
        json={
            "feature_id": new_feature_id,
            "title": f"{date.today().isoformat()} 重新生成的问题报告",
            "body_markdown": "# 新报告",
        },
        headers={"X-Subject-Id": "alice@dev-1"},
    )

    assert saved.status_code == 201, saved.text
    assert saved.json()["id"] == current_report_id
    assert saved.json()["feature_id"] == new_feature_id

    old_feature_reports = await client.get(
        f"/api/reports?feature_id={old_feature_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    new_feature_reports = await client.get(
        f"/api/reports?feature_id={new_feature_id}",
        headers={"X-Subject-Id": "alice@dev-1"},
    )
    assert old_feature_reports.status_code == 200
    assert old_feature_reports.json() == []
    assert [item["id"] for item in new_feature_reports.json()] == [current_report_id]

    async with app.state.session_factory() as db:
        legacy_report = await db.get(Report, legacy_report_id)
        current_report = await db.get(Report, current_report_id)
        old_space = (
            await db.execute(
                select(WikiSpace).where(
                    WikiSpace.feature_id == old_feature_id,
                    WikiSpace.scope == "current",
                )
            )
        ).scalar_one()
        old_report_refs = (
            await db.execute(
                select(WikiReportRef)
                .join(WikiNode, WikiNode.id == WikiReportRef.node_id)
                .where(WikiNode.space_id == old_space.id)
            )
        ).scalars().all()

    assert legacy_report is None
    assert current_report is not None
    assert current_report.feature_id == new_feature_id
    assert old_report_refs == []
