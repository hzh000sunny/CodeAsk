import pytest

from codeask.agent.native_backend.chat_runtime.retrieval import LightweightRetrievalService


@pytest.mark.asyncio
async def test_retrieval_returns_candidates_without_backend_judgement() -> None:
    service = LightweightRetrievalService(
        feature_candidates=[{"feature_id": 3, "name": "小米", "score": 0.91}],
        wiki_hits=[{"node_id": 10, "title": "小米病历", "snippet": "体重下降"}],
        report_hits=[],
    )

    context = await service.retrieve(
        user_message="小米最近病情趋势是什么？",
        session_summary=None,
        attachments=[],
    )

    assert context["feature_candidates"][0]["name"] == "小米"
    assert context["wiki_hits"][0]["title"] == "小米病历"
    serialized = str(context)
    assert "insufficient" not in serialized
    assert "next_step" not in serialized
    assert "scope_detection" not in serialized
