import pytest

from codeask.rag.openviking.tuning import (
    detect_preset,
    ollama_snippet,
    verify_ollama_recommend,
)


def test_detect_preset_prefers_cloud_embedding_provider() -> None:
    preset_id, values = detect_preset(
        cpu_count=8,
        memory_gb=16,
        has_gpu=False,
        embedding_provider="openai",
    )

    assert preset_id == "cloud_embedding"
    assert values[("openviking", "embedding.max_concurrent")].recommended == "4"


def test_detect_preset_prefers_gpu_host_over_cpu_size() -> None:
    preset_id, values = detect_preset(
        cpu_count=8,
        memory_gb=16,
        has_gpu=True,
        embedding_provider="ollama",
    )

    assert preset_id == "gpu_host"
    assert values[("openviking", "embedding.max_concurrent")].recommended == "2"


def test_detect_preset_uses_cpu_and_memory_for_local_ollama() -> None:
    small_preset = detect_preset(
        cpu_count=6,
        memory_gb=8,
        has_gpu=False,
        embedding_provider="ollama",
    )[0]

    assert small_preset == "small_machine"
    assert (
        detect_preset(
            cpu_count=24,
            memory_gb=64,
            has_gpu=False,
            embedding_provider="ollama",
        )[0]
        == "medium_server"
    )
    assert (
        detect_preset(
            cpu_count=64,
            memory_gb=128,
            has_gpu=False,
            embedding_provider="ollama",
        )[0]
        == "large_server"
    )


def test_ollama_snippet_includes_parallel_and_thread_values() -> None:
    snippet = ollama_snippet(num_parallel=2, num_thread=8)

    assert "OLLAMA_NUM_PARALLEL=2" in snippet
    assert "OLLAMA_NUM_THREAD=8" in snippet
    assert "systemctl daemon-reload" in snippet


@pytest.mark.asyncio
async def test_verify_ollama_recommend_reports_probe_result() -> None:
    calls: list[int] = []

    async def fake_probe(expected_num_parallel: int) -> int:
        calls.append(expected_num_parallel)
        return 2

    result = await verify_ollama_recommend(expected_num_parallel=2, probe=fake_probe)

    assert result.verified is True
    assert result.expected_num_parallel == 2
    assert result.observed_parallel == 2
    assert calls == [2]
