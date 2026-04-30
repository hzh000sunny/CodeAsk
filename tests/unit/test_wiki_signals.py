"""Tests for engineering signal extraction."""

from codeask.wiki.signals import extract_signals


def test_error_codes() -> None:
    sig = extract_signals("see ERR_ORDER_CONTEXT_EMPTY and SQLSTATE 40001")
    assert "ERR_ORDER_CONTEXT_EMPTY" in sig["error_codes"]
    assert "SQLSTATE 40001" in sig["error_codes"]


def test_exception_names() -> None:
    sig = extract_signals("got NullPointerException, then TimeoutError")
    assert "NullPointerException" in sig["exception_names"]
    assert "TimeoutError" in sig["exception_names"]


def test_routes() -> None:
    sig = extract_signals("call /api/order/submit and /api/v1/users/list")
    assert "/api/order/submit" in sig["routes"]
    assert "/api/v1/users/list" in sig["routes"]


def test_config_keys() -> None:
    sig = extract_signals("flag order.payment.retry.enabled = true")
    assert "order.payment.retry.enabled" in sig["config_keys"]


def test_symbols() -> None:
    sig = extract_signals("OrderService.submitOrder() inside UserContextInterceptor")
    assert "OrderService" in sig["symbols"]
    assert "submitOrder" in sig["symbols"]
    assert "UserContextInterceptor" in sig["symbols"]


def test_file_paths() -> None:
    sig = extract_signals("see src/order/service.py and src/main.ts")
    assert "src/order/service.py" in sig["file_paths"]
    assert "src/main.ts" in sig["file_paths"]


def test_empty_buckets_when_no_match() -> None:
    sig = extract_signals("just plain prose")
    for key in (
        "error_codes",
        "exception_names",
        "routes",
        "config_keys",
        "symbols",
        "file_paths",
    ):
        assert sig[key] == []
