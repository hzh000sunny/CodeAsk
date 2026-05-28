from pathlib import Path
from types import SimpleNamespace

import pytest_asyncio
from fastapi import FastAPI

from codeask.agent.native_backend.chat_runtime.tool_registry import ToolRegistry as ChatToolRegistry
from codeask.agent.native_backend.chat_runtime.tools.attachments import register_attachment_tools
from codeask.agent.native_backend.chat_runtime.tools.live_code import register_live_code_tools
from codeask.agent.native_backend.chat_runtime.tools.reports import register_report_tools
from codeask.agent.native_backend.chat_runtime.tools.wiki import register_wiki_tools
from codeask.agent.native_backend.code_tools import AgentCodeSearchService
from codeask.agent.native_backend.tools import ToolRegistry
from codeask.agent.native_backend.wiki_tools import AgentWikiToolService
from codeask.app import create_app
from codeask.settings import Settings


@pytest_asyncio.fixture()
async def app(settings: Settings) -> FastAPI:
    application = create_app(settings)
    async with application.router.lifespan_context(application):
        _attach_legacy_native_state(application, settings)
        yield application


def _attach_legacy_native_state(app: FastAPI, settings: Settings) -> None:
    chat_tool_registry = ChatToolRegistry()
    register_wiki_tools(chat_tool_registry, session_factory=app.state.session_factory)
    register_report_tools(chat_tool_registry, session_factory=app.state.session_factory)
    register_attachment_tools(chat_tool_registry, session_factory=app.state.session_factory)
    register_live_code_tools(
        chat_tool_registry,
        session_factory=app.state.session_factory,
        worktree_manager=app.state.worktree_manager,
    )
    app.state.chat_runtime = SimpleNamespace(_tool_registry=chat_tool_registry)

    wiki_search = AgentWikiToolService(app.state.session_factory)
    code_search = AgentCodeSearchService(
        app.state.session_factory,
        app.state.worktree_manager,
        index_dir=Path(settings.data_dir) / "index",
    )
    app.state.tool_registry = ToolRegistry.bootstrap(
        wiki_search_service=wiki_search,
        code_search_service=code_search,
    )
