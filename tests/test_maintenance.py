"""Tests for the manual reindex tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from eye_ai_deriva_mcp_plugin.maintenance import register_maintenance_tools


async def test_reindex_tool_registered(ctx):
    register_maintenance_tools(ctx)
    assert "deriva_eye_ai_reindex_catalog" in ctx._mcp.tools


async def test_reindex_rejects_non_eyeai_host(ctx):
    register_maintenance_tools(ctx)
    out = json.loads(await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("other.org", "1"))
    assert "error" in out
    assert "eye-ai" in out["error"]


async def test_reindex_runs_and_returns_counts(ctx):
    register_maintenance_tools(ctx)
    with patch(
        "eye_ai_deriva_mcp_plugin.maintenance._index_catalog",
        AsyncMock(return_value={"tables_indexed": 2, "tables_failed": 0, "rows_indexed": 7}),
    ):
        out = json.loads(
            await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("www.eye-ai.org", "5")
        )
    assert out["status"] == "reindexed"
    assert out["host"] == "www.eye-ai.org"
    assert out["catalog_id"] == "5"
    assert out["tables_indexed"] == 2
    assert out["rows_indexed"] == 7


async def test_reindex_error_envelope_on_failure(ctx):
    register_maintenance_tools(ctx)
    with patch(
        "eye_ai_deriva_mcp_plugin.maintenance._index_catalog",
        AsyncMock(side_effect=RuntimeError("store down")),
    ):
        out = json.loads(
            await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("www.eye-ai.org", "5")
        )
    assert out == {"error": "store down"}
