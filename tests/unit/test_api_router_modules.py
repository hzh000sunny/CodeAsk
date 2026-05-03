"""Router module split smoke tests."""

from importlib import import_module


def test_split_api_router_modules_export_router() -> None:
    modules = [
        "codeask.api.features",
        "codeask.api.reports",
        "codeask.api.documents_compat",
        "codeask.api.wiki",
    ]

    for module_name in modules:
        module = import_module(module_name)
        assert hasattr(module, "router"), module_name
