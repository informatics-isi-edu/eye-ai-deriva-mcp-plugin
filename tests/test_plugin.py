"""Smoke tests for the plugin entry point."""

from __future__ import annotations

from importlib import metadata

from eye_ai_deriva_mcp_plugin import config
from eye_ai_deriva_mcp_plugin.plugin import register


def test_register_declares_one_indexer_per_host_table(ctx):
    register(ctx)
    hosts = config.eye_ai_hosts(ctx.env)
    tables = config.eye_ai_tables(ctx.env)
    indexers = ctx._rag_dataset_indexers
    assert len(indexers) == len(hosts) * len(tables)
    # Every indexer is the catalog-public, auto-enriched shape.
    assert all(ix.is_public for ix in indexers)
    assert all(ix.auto_enrich for ix in indexers)
    assert all(ix.doc_type == "eye-ai-data" for ix in indexers)
    # Coverage is exactly the (host, schema, table) cross product.
    declared = {(ix.hostname, ix.schema, ix.table) for ix in indexers}
    expected = {(h, s, t) for h in hosts for s, t in tables}
    assert declared == expected


def test_register_declares_the_domain_prompts(ctx):
    register(ctx)
    assert set(ctx._mcp.prompts) == {"eye-ai-assistant", "find-images", "explore-diagnosis"}


def test_register_adds_no_tools_or_connect_hooks(ctx):
    # The hand-rolled maintenance tool and on_catalog_connect hook are gone --
    # the framework's rag_dataset_indexer owns the on-connect execution.
    register(ctx)
    assert ctx._mcp.tools == {}
    assert ctx._catalog_connect_hooks == []


def test_entry_point_resolves_to_register():
    # Entry-point name is the bare domain ("eye-ai"), matching the
    # facebase-deriva-mcp-plugin convention (entry point "facebase").
    eps = metadata.entry_points(group="deriva_mcp.plugins")
    matching = [ep for ep in eps if ep.name == "eye-ai"]
    assert matching, "entry point 'eye-ai' not declared"
    assert matching[0].load() is register
