"""Registry for chat runtime tools."""

from __future__ import annotations

from dataclasses import dataclass

from codeask.agent.native_backend.chat_runtime.tool_contracts import ToolHandler, ToolSpec
from codeask.llm.types import ToolDef


@dataclass(frozen=True)
class RegisteredRuntimeTool:
    spec: ToolSpec
    handler: ToolHandler


class ToolRegistry:
    """Stores tool contracts and handlers visible to the chat runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredRuntimeTool] = {}

    def register(self, spec: ToolSpec, handler: ToolHandler) -> None:
        self._tools[spec.name] = RegisteredRuntimeTool(spec=spec, handler=handler)

    def get(self, name: str) -> RegisteredRuntimeTool | None:
        return self._tools.get(name)

    def available_tools(self) -> list[ToolSpec]:
        return [tool.spec for tool in self._tools.values() if tool.spec.enabled]

    def tool_defs_for_llm(self) -> list[ToolDef]:
        return [
            ToolDef(
                name=spec.name,
                description=spec.description,
                input_schema=spec.input_schema(),
            )
            for spec in self.available_tools()
        ]
