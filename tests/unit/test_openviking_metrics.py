import pytest

from codeask.rag.openviking.metrics import OpenVikingMetricsRecorder


@pytest.mark.asyncio
async def test_openviking_metrics_recorder_reports_latency_p95() -> None:
    recorder = OpenVikingMetricsRecorder(window_seconds=300, cap=1000)

    for _ in range(100):
        await recorder.record_latency(50)

    snapshot = recorder.snapshot()

    assert snapshot["collected"] is True
    assert snapshot["latency_samples"] == 100
    assert snapshot["latency_p95_ms"] == 50
    assert snapshot["message"] is None


def test_openviking_metrics_recorder_reports_warming_up_when_empty() -> None:
    recorder = OpenVikingMetricsRecorder(window_seconds=300, cap=1000)

    snapshot = recorder.snapshot()

    assert snapshot == {
        "collected": False,
        "window_seconds": 300,
        "latency_p95_ms": None,
        "latency_samples": 0,
        "message": "warming up",
    }


@pytest.mark.asyncio
async def test_snapshot_filters_samples_older_than_window(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = OpenVikingMetricsRecorder(window_seconds=300, cap=1000)

    monkeypatch.setattr("codeask.rag.openviking.metrics.time.time", lambda: 1000.0)
    for _ in range(50):
        await recorder.record_latency(500.0)

    monkeypatch.setattr("codeask.rag.openviking.metrics.time.time", lambda: 1600.0)
    for _ in range(10):
        await recorder.record_latency(50.0)

    snapshot = recorder.snapshot()

    assert snapshot["latency_samples"] == 10
    assert snapshot["latency_p95_ms"] == 50
