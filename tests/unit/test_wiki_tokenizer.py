"""Tests for wiki tokenizer and n-gram helpers."""

from codeask.wiki.tokenizer import to_ngrams, tokenize


def test_tokenize_english_words() -> None:
    out = tokenize("Submit Order Service v2 ")
    assert out == "submit order service v2"


def test_tokenize_chinese_per_char() -> None:
    out = tokenize("订单服务")
    assert out == "订 单 服 务"


def test_tokenize_mixed() -> None:
    out = tokenize("订单 SubmitOrder ERR_001")
    tokens = out.split()
    assert "订" in tokens
    assert "单" in tokens
    assert "submitorder" in tokens
    assert "err_001" in tokens


def test_tokenize_strips_punctuation_but_keeps_underscore_and_dash() -> None:
    out = tokenize("call /api/order/submit, see ERR-123!")
    tokens = set(out.split())
    assert "/api/order/submit" not in tokens
    assert "api" in tokens
    assert "order" in tokens
    assert "submit" in tokens
    assert "err-123" in tokens


def test_to_ngrams_trigram() -> None:
    out = to_ngrams("abcd", n=3)
    assert out.split() == ["abc", "bcd"]


def test_to_ngrams_strips_whitespace() -> None:
    out = to_ngrams("ab cd", n=3)
    assert out.split() == ["abc", "bcd"]


def test_to_ngrams_short_input() -> None:
    out = to_ngrams("ab", n=3)
    assert out == "ab"


def test_to_ngrams_chinese() -> None:
    out = to_ngrams("订单服务", n=3)
    assert out.split() == ["订单服", "单服务"]
