"""Shared test fixtures: a minimal FastMCP stand-in and a PluginContext."""

from __future__ import annotations

from typing import Any

import pytest
from deriva_mcp_core.plugin.api import PluginContext, _set_plugin_context


class _CapturingMCP:
    """Minimal FastMCP stand-in that stores registered tools by name."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, **kwargs: Any):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, *a: Any, **kw: Any):
        return lambda fn: fn

    def prompt(self, *a: Any, **kw: Any):
        return lambda fn: fn


@pytest.fixture()
def mcp():
    return _CapturingMCP()


@pytest.fixture()
def ctx(mcp):
    _ctx = PluginContext(mcp)
    _set_plugin_context(_ctx)
    yield _ctx
    _set_plugin_context(None)
