"""Smoke tests for the plugin entry point."""

from __future__ import annotations

from importlib import metadata

from eye_ai_deriva_mcp_plugin.plugin import register


def test_register_runs_without_error(ctx):
    register(ctx)
    # The maintenance tool landed.
    assert "deriva_eye_ai_reindex_catalog" in ctx._mcp.tools
    # One catalog-connect hook registered.
    assert len(ctx._catalog_connect_hooks) == 1


def test_entry_point_resolves_to_register():
    # Entry-point name is the bare domain ("eye-ai"), matching the
    # facebase-deriva-mcp-plugin convention (entry point "facebase").
    eps = metadata.entry_points(group="deriva_mcp.plugins")
    matching = [ep for ep in eps if ep.name == "eye-ai"]
    assert matching, "entry point 'eye-ai' not declared"
    assert matching[0].load() is register
