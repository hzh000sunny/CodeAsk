"""ScriptedMockLLMClient replays eval steps in order."""

import pytest

from tests.mocks.mock_llm import ScriptedMockLLMClient, ScriptStep


@pytest.mark.asyncio
async def test_replays_in_order() -> None:
    client = ScriptedMockLLMClient(
        [
            ScriptStep(tool_name="search_wiki", tool_arguments={"query": "order"}),
            ScriptStep(text="The answer is..."),
            ScriptStep(text="...done.", finish=True),
        ]
    )

    first = await client.next_step()
    second = await client.next_step()
    third = await client.next_step()

    assert first.tool_name == "search_wiki"
    assert second.text == "The answer is..."
    assert third.finish is True


@pytest.mark.asyncio
async def test_exhaustion_raises() -> None:
    client = ScriptedMockLLMClient([ScriptStep(text="only", finish=True)])
    await client.next_step()

    with pytest.raises(IndexError):
        await client.next_step()


def test_requires_at_least_one_step() -> None:
    with pytest.raises(ValueError):
        ScriptedMockLLMClient([])
