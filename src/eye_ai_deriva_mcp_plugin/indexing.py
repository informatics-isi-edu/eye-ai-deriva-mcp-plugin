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

import logging
from typing import Any

from deriva_mcp_core import deriva_call, get_catalog
from deriva_mcp_core.rag.chunker import chunk_markdown
from deriva_mcp_core.rag.store import Chunk

from eye_ai_deriva_mcp_plugin.serializers import EyeAIRowSerializer

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
