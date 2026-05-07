from codeask.agent.chat_runtime.events import (
    ChatRuntimeEvent,
    EvidenceRef,
    ToolResultEventData,
)


def test_tool_result_event_contains_audit_ready_fields() -> None:
    event = ChatRuntimeEvent(
        type="tool_result",
        data=ToolResultEventData(
            tool_call_id="call_1",
            tool_name="search_wiki",
            ok=True,
            summary="命中 2 篇 Wiki",
            evidence_refs=[
                EvidenceRef(
                    type="wiki",
                    title="小米病历",
                    path="小米 / 知识库 / 小米病历",
                )
            ],
            warnings=[],
            truncated=False,
            raw_result_ref="tool_result_1",
        ),
    )

    payload = event.model_dump()
    assert payload["type"] == "tool_result"
    assert payload["data"]["tool_name"] == "search_wiki"
    assert payload["data"]["evidence_refs"][0]["type"] == "wiki"
