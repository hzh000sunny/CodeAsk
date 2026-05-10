"""Provider-neutral reasoning normalization."""

from codeask.llm.reasoning import normalize_anthropic_stream_event, normalize_openai_delta


def test_openai_reasoning_content_becomes_reasoning_delta() -> None:
    events = normalize_openai_delta({"reasoning_content": "内部思考"})

    assert events == [
        (
            "reasoning_delta",
            {"delta": "内部思考", "field": "reasoning_content", "redacted": False},
        )
    ]


def test_openai_content_becomes_text_delta() -> None:
    events = normalize_openai_delta({"content": "正式回答"})

    assert events == [("text_delta", {"delta": "正式回答"})]


def test_openai_same_delta_can_emit_reasoning_and_text() -> None:
    events = normalize_openai_delta(
        {"reasoning_content": "内部思考", "content": "正式回答"}
    )

    assert events == [
        (
            "reasoning_delta",
            {"delta": "内部思考", "field": "reasoning_content", "redacted": False},
        ),
        ("text_delta", {"delta": "正式回答"}),
    ]


def test_content_with_think_tag_is_not_parsed() -> None:
    events = normalize_openai_delta({"content": "<think>内部</think>正式回答"})

    assert events == [("text_delta", {"delta": "<think>内部</think>正式回答"})]


def test_anthropic_thinking_delta_becomes_reasoning_delta() -> None:
    events = normalize_anthropic_stream_event(
        {"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "内部"}}
    )

    assert events == [
        ("reasoning_delta", {"delta": "内部", "field": "thinking_delta", "redacted": False})
    ]


def test_anthropic_text_delta_becomes_text_delta() -> None:
    events = normalize_anthropic_stream_event(
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "回答"}}
    )

    assert events == [("text_delta", {"delta": "回答"})]


def test_anthropic_signature_delta_is_not_visible() -> None:
    events = normalize_anthropic_stream_event(
        {"type": "content_block_delta", "delta": {"type": "signature_delta", "signature": "sig"}}
    )

    assert events == []
