"""Tests for the indexing core."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from eye_ai_deriva_mcp_plugin import indexing


def test_source_name_shape():
    assert (
        indexing._source_name("www.eye-ai.org", "5", "EyeAI", "Subject")
        == "eye-ai:www.eye-ai.org:5:EyeAI.Subject"
    )


def test_fetch_table_rows_builds_ermrest_path():
    catalog = MagicMock()
    resp = MagicMock()
    resp.json.return_value = [{"RID": "1-AAAA"}]
    catalog.get.return_value = resp
    with patch("eye_ai_deriva_mcp_plugin.indexing.get_catalog", return_value=catalog):
        rows = indexing._fetch_table_rows("www.eye-ai.org", "5", "EyeAI", "Subject")
    catalog.get.assert_called_once_with("/entity/EyeAI:Subject")
    assert rows == [{"RID": "1-AAAA"}]


async def test_write_table_replaces_then_adds():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    rows = [{"RID": "1-AAAA", "Name": "S1"}, {"RID": "2-BBBB", "Name": "S2"}]
    written = await indexing._write_table(store, "src1", "Subject", rows)
    store.delete_source.assert_awaited_once_with("src1")
    store.add.assert_awaited_once()
    assert written >= 2
    added_chunks = store.add.await_args.args[0]
    assert all(c.source == "src1" for c in added_chunks)


async def test_write_table_empty_rows_skips_add():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    written = await indexing._write_table(store, "src1", "Subject", [])
    store.delete_source.assert_awaited_once_with("src1")
    store.add.assert_not_awaited()
    assert written == 0


async def test_is_index_fresh_true_within_ttl():
    from deriva_mcp_core.rag.store import SourceStats

    now_iso = datetime.now(UTC).isoformat()
    store = MagicMock()
    store.source_stats = AsyncMock(
        return_value={"eye-ai:www.eye-ai.org:5:EyeAI.Subject": SourceStats(3, now_iso)}
    )
    fresh = await indexing._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is True


async def test_is_index_fresh_false_when_stale():
    from deriva_mcp_core.rag.store import SourceStats

    old_iso = "2000-01-01T00:00:00+00:00"
    store = MagicMock()
    store.source_stats = AsyncMock(
        return_value={"eye-ai:www.eye-ai.org:5:EyeAI.Subject": SourceStats(3, old_iso)}
    )
    fresh = await indexing._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is False


async def test_is_index_fresh_false_when_no_sources():
    store = MagicMock()
    store.source_stats = AsyncMock(return_value={})
    fresh = await indexing._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is False


async def test_index_catalog_indexes_each_configured_table():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch(
            "eye_ai_deriva_mcp_plugin.indexing._fetch_table_rows",
            return_value=[{"RID": "1-AAAA", "Name": "S1"}],
        ),
    ):
        result = await indexing._index_catalog(
            "www.eye-ai.org", "5", [("EyeAI", "Subject"), ("EyeAI", "Image")], {}
        )
    assert result["tables_indexed"] == 2
    assert result["rows_indexed"] == 2
    assert store.delete_source.await_count == 2
    assert store.add.await_count == 2


async def test_index_catalog_isolates_table_fetch_failure():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()

    def _fetch(host, cat, schema, table):
        if table == "Image":
            raise RuntimeError("ermrest 500")
        return [{"RID": "1-AAAA"}]

    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._fetch_table_rows", side_effect=_fetch),
    ):
        result = await indexing._index_catalog(
            "www.eye-ai.org", "5", [("EyeAI", "Subject"), ("EyeAI", "Image")], {}
        )
    assert result["tables_indexed"] == 1
    assert result["tables_failed"] == 1


async def test_index_catalog_returns_zero_when_store_none():
    with patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=None):
        result = await indexing._index_catalog("www.eye-ai.org", "5", [("EyeAI", "Subject")], {})
    assert result == {"tables_indexed": 0, "tables_failed": 0, "rows_indexed": 0}


async def test_index_catalog_isolates_write_failure():
    store = MagicMock()
    store.delete_source = AsyncMock(side_effect=RuntimeError("store add failed"))
    store.add = AsyncMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch(
            "eye_ai_deriva_mcp_plugin.indexing._fetch_table_rows",
            return_value=[{"RID": "1-AAAA", "Name": "S1"}],
        ),
    ):
        result = await indexing._index_catalog(
            "www.eye-ai.org", "5", [("EyeAI", "Subject"), ("EyeAI", "Image")], {}
        )
    # Both tables failed at the write step; neither aborted the pass.
    assert result["tables_failed"] == 2
    assert result["tables_indexed"] == 0


async def test_hook_no_ops_on_non_eyeai_host(ctx):
    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    hook = indexing.make_catalog_connect_hook(ctx)
    await hook("other.deriva.org", "1", "hash", {})
    assert submitted == []  # not an eye-ai host -> no task


async def test_hook_no_ops_when_rag_disabled(ctx):
    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    with patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=None):
        hook = indexing.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert submitted == []  # RAG off -> no task


async def test_hook_skips_when_fresh(ctx):
    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    store = MagicMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._is_index_fresh", AsyncMock(return_value=True)),
    ):
        hook = indexing.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert submitted == []  # fresh -> no task


async def test_hook_submits_task_when_stale(ctx):
    submitted = []

    def _submit(coro, name="", description=""):
        coro.close()  # avoid "coroutine never awaited" warning
        submitted.append(name)
        return "task-1"

    ctx.submit_task = _submit
    store = MagicMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._is_index_fresh", AsyncMock(return_value=False)),
    ):
        hook = indexing.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert len(submitted) == 1
    assert "www.eye-ai.org/5" in submitted[0]
