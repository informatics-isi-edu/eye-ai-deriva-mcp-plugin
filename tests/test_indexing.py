"""Tests for the indexing core."""

from __future__ import annotations

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
