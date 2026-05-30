"""On-connect eye-ai catalog indexing.

When a tool connects to an eye-ai catalog, an ``on_catalog_connect``
hook submits a background task that fetches each configured
``EyeAI:<table>``, serializes its rows to Markdown, and writes them to
the RAG vector store under a catalog-public source name
``eye-ai:{host}:{cat}:{schema}.{table}``.

The ``eye-ai:`` source prefix is deliberately NOT one of the prefixes
the upstream ``rag_search`` user-id filter gates on (``data:``,
``schema:``, ``enriched:``), so the chunks are served to all authorized
users. This is correct because the eye-ai catalog has auth-gating but
no row-level ACLs -- every authorized user sees everything.

This module provides the source-name helper, the ERMrest fetch, and the
per-table write. The full-catalog pass, freshness check, and the
on-connect hook are added in later modules/tasks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from deriva_mcp_core import deriva_call, get_catalog
from deriva_mcp_core.rag import get_rag_store
from deriva_mcp_core.rag.chunker import chunk_markdown
from deriva_mcp_core.rag.store import Chunk

from eye_ai_deriva_mcp_plugin import config
from eye_ai_deriva_mcp_plugin.serializers import EyeAIRowSerializer

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext

logger = logging.getLogger(__name__)

_SERIALIZER = EyeAIRowSerializer()
_DOC_TYPE = "eye-ai-data"


def _source_name(hostname: str, catalog_id: str, schema: str, table: str) -> str:
    """Build the catalog-public source name for one eye-ai table.

    Shape: ``eye-ai:{host}:{cat}:{schema}.{table}``. The ``eye-ai:``
    prefix bypasses the upstream per-user ``data:`` filter so all users
    see the chunks.

    Example:
        >>> _source_name("www.eye-ai.org", "5", "EyeAI", "Subject")
        'eye-ai:www.eye-ai.org:5:EyeAI.Subject'
    """
    return f"eye-ai:{hostname}:{catalog_id}:{schema}.{table}"


def _fetch_table_rows(
    hostname: str, catalog_id: str, schema: str, table: str
) -> list[dict[str, Any]]:
    """Fetch all rows of one eye-ai table via generic ERMrest.

    Synchronous deriva-py I/O -- the async caller wraps this in
    ``asyncio.to_thread``. Uses ``get_catalog`` (the per-request
    credential path), so it must run inside a request or a background
    task that has set the credential contextvar.

    Args:
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        schema: ERMrest schema name (e.g. ``"EyeAI"``).
        table: ERMrest table name (e.g. ``"Subject"``).

    Returns:
        A list of row dicts.
    """
    with deriva_call():
        catalog = get_catalog(hostname, catalog_id)
        return catalog.get(f"/entity/{schema}:{table}").json()


async def _write_table(
    store: Any,
    source: str,
    table: str,
    rows: list[dict[str, Any]],
) -> int:
    """Replace ``source`` with the chunks rendered from ``rows``.

    ``delete_source`` first (idempotent -- drains any prior pass), then
    serialize each row, chunk it, and ``store.add`` the lot in one call.

    Args:
        store: An active vector store.
        source: The canonical source name for this table.
        table: ERMrest table name (passed to the serializer).
        rows: Row dicts for the table.

    Returns:
        Count of chunks written.
    """
    await store.delete_source(source)
    chunks: list[Chunk] = []
    chunk_index = 0
    for row in rows:
        try:
            rendered = _SERIALIZER.serialize(table, row)
        except Exception:  # noqa: BLE001 -- one bad row must not poison the table
            logger.exception("eye-ai RAG: serialize failed for %s row %r", table, row.get("RID"))
            continue
        if rendered is None:
            continue
        for c in chunk_markdown(rendered, source=source, doc_type=_DOC_TYPE):
            chunks.append(
                Chunk(
                    text=c.text,
                    source=source,
                    doc_type=_DOC_TYPE,
                    section_heading=c.section_heading,
                    heading_hierarchy=c.heading_hierarchy,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
    if chunks:
        await store.add(chunks)
    return len(chunks)


def _parse_iso(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; return None on any failure."""
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


async def _is_index_fresh(store: Any, hostname: str, catalog_id: str, ttl_seconds: int) -> bool:
    """Return True if this catalog's eye-ai index is within the TTL.

    Reads the most recent ``indexed_at`` across the catalog's
    ``eye-ai:{host}:{cat}:`` sources from ``store.source_stats()``. If
    none exist (never indexed) or the freshest is older than the TTL,
    returns False.

    Args:
        store: An active vector store.
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        ttl_seconds: Freshness window.

    Returns:
        True if a re-index can be skipped; False otherwise.
    """
    if ttl_seconds <= 0:
        return False
    prefix = f"eye-ai:{hostname}:{catalog_id}:"
    stats = await store.source_stats()
    newest: datetime | None = None
    for source, stat in stats.items():
        if not source.startswith(prefix) or stat.indexed_at is None:
            continue
        dt = _parse_iso(stat.indexed_at)
        if dt is not None and (newest is None or dt > newest):
            newest = dt
    if newest is None:
        return False
    age = (datetime.now(UTC) - newest).total_seconds()
    return age < ttl_seconds


async def _index_catalog(
    hostname: str,
    catalog_id: str,
    tables: list[tuple[str, str]],
    env: dict[str, str],  # noqa: ARG001 -- reserved for future per-call config
) -> dict[str, int]:
    """Fetch + index every configured eye-ai table for one catalog.

    Per-table fetch failures are isolated: a failing table is logged and
    counted in ``tables_failed`` but does not abort the rest of the
    pass. Runs the synchronous ERMrest fetch in a worker thread.

    Args:
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        tables: Ordered ``(schema, table)`` pairs to index.
        env: Reserved (merged env map) for future per-call knobs.

    Returns:
        ``{"tables_indexed", "tables_failed", "rows_indexed"}``.
    """
    store = get_rag_store()
    if store is None:
        logger.debug("eye-ai RAG: store unavailable, skipping index of %s/%s", hostname, catalog_id)
        return {"tables_indexed": 0, "tables_failed": 0, "rows_indexed": 0}

    tables_indexed = 0
    tables_failed = 0
    rows_indexed = 0
    for schema, table in tables:
        source = _source_name(hostname, catalog_id, schema, table)
        try:
            rows = await asyncio.to_thread(_fetch_table_rows, hostname, catalog_id, schema, table)
            await _write_table(store, source, table, rows)
            tables_indexed += 1
            rows_indexed += len(rows)
        except Exception:  # noqa: BLE001 -- one bad table must not abort the pass
            logger.exception(
                "eye-ai RAG: index failed for %s:%s on %s/%s", schema, table, hostname, catalog_id
            )
            tables_failed += 1
            continue
    logger.info(
        "eye-ai RAG: indexed %s/%s -- %d tables, %d failed, %d rows",
        hostname,
        catalog_id,
        tables_indexed,
        tables_failed,
        rows_indexed,
    )
    return {
        "tables_indexed": tables_indexed,
        "tables_failed": tables_failed,
        "rows_indexed": rows_indexed,
    }


async def _index_catalog_task(
    task_id_ref: list[str],
    hostname: str,
    catalog_id: str,
    tables: list[tuple[str, str]],
    env: dict[str, str],
) -> dict[str, int]:
    """Background-task wrapper: re-resolve the credential, then index.

    Background tasks do not carry the per-request credential contextvar,
    so the credential is re-fetched from the TaskManager before any
    DERIVA I/O (the authoring guide's long-task pattern). The credential
    is set on the contextvar so ``get_catalog`` inside ``_fetch_table_rows``
    resolves it.

    Args:
        task_id_ref: A one-element list holding this task's id. The hook
            mutates element 0 after ``submit_task`` returns, so the task
            body reads it lazily rather than at submission time.
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        tables: Ordered ``(schema, table)`` pairs to index.
        env: The merged environment map (``ctx.env``).

    Returns:
        ``{"tables_indexed", "tables_failed", "rows_indexed"}`` from
        ``_index_catalog``.

    Example:
        >>> # Submitted by ``make_catalog_connect_hook``'s ``hook``:
        >>> ref = [""]
        >>> ref[0] = ctx.submit_task(  # doctest: +SKIP
        ...     _index_catalog_task(ref, host, cat, tables, env), name="...",
        ... )
    """
    from deriva_mcp_core.context import set_current_credential
    from deriva_mcp_core.tasks import get_task_manager

    task_id = task_id_ref[0]
    cred = await get_task_manager().get_credential(task_id)
    set_current_credential(cred)
    return await _index_catalog(hostname, catalog_id, tables, env)


def make_catalog_connect_hook(
    ctx: PluginContext,
) -> Callable[[str, str, str, dict], Any]:
    """Build the ``on_catalog_connect`` hook bound to ``ctx``.

    The hook host-gates, RAG-gates, and TTL-gates, then submits a
    background ``_index_catalog_task`` for stale eye-ai catalogs.

    Args:
        ctx: The plugin context (for ``ctx.env`` and ``ctx.submit_task``).

    Returns:
        An async hook with the ``on_catalog_connect`` signature.

    Example:
        >>> hook = make_catalog_connect_hook(ctx)  # doctest: +SKIP
        >>> await hook("www.eye-ai.org", "5", schema_hash, schema_json)  # doctest: +SKIP
    """
    hosts = config.eye_ai_hosts(ctx.env)
    tables = config.eye_ai_tables(ctx.env)
    ttl = config.index_ttl_seconds(ctx.env)

    async def hook(
        hostname: str,
        catalog_id: str,
        schema_hash: str,  # noqa: ARG001 -- hook signature requires it
        schema_json: dict,  # noqa: ARG001 -- hook signature requires it
    ) -> None:
        if hostname not in hosts:
            return
        store = get_rag_store()
        if store is None:
            return
        try:
            if await _is_index_fresh(store, hostname, catalog_id, ttl):
                logger.debug("eye-ai RAG: index fresh for %s/%s, skipping", hostname, catalog_id)
                return
        except Exception:  # noqa: BLE001 -- a freshness probe failure should not block indexing
            logger.exception("eye-ai RAG: freshness check failed for %s/%s", hostname, catalog_id)

        task_id_ref: list[str] = [""]
        task_id = ctx.submit_task(
            _index_catalog_task(task_id_ref, hostname, catalog_id, tables, ctx.env),
            name=f"eye-ai index {hostname}/{catalog_id}",
            description=f"Index eye-ai tables for catalog {catalog_id}",
        )
        task_id_ref[0] = task_id

    return hook
