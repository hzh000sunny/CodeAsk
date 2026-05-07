from codeask.agent.chat_runtime.context import ContextAssembler, SessionMessage


def test_context_assembler_keeps_recent_history_and_candidate_context() -> None:
    assembler = ContextAssembler(max_history_messages=2)
    context = assembler.assemble(
        user_message="小米最近病情趋势是什么？",
        history=[
            SessionMessage(role="user", content="第一轮"),
            SessionMessage(role="assistant", content="第一轮回答"),
            SessionMessage(role="user", content="第二轮"),
        ],
        retrieval_context={"wiki_hits": [{"title": "小米病历", "snippet": "体重下降"}]},
        attachments=[],
        explicit_constraints={},
    )

    assert "小米最近病情趋势是什么？" in context.current_user_message
    assert len(context.recent_history) == 2
    assert context.retrieval_context["wiki_hits"][0]["title"] == "小米病历"
