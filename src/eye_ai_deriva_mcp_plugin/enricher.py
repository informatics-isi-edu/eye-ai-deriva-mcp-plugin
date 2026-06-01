"""Row enrichers for eye-ai RAG indexing.

``make_enricher(table)`` builds the ``async (row, catalog) -> str``
callable that ``ctx.rag_dataset_indexer`` invokes once per fetched row.
Each call renders one eye-ai row to a Markdown section: a header line
carrying the table name + RID, then each non-empty, non-system field as
a ``**Field:** value`` line. That Markdown is what the framework chunks
and embeds.

No FK joins. Eye-ai's categorical columns are foreign keys that
reference the target vocabulary's ``Name`` column, so the fetched row
dict already carries the human-readable label (e.g.
``Subject_Gender = "Female"``) -- no extra fetch is needed to make the
chunk searchable. This is the opposite of facebase, whose dataset FKs
are RID-referencing and must be resolved in the enricher. The
``catalog`` argument is part of the framework's required enricher
signature; it is accepted and ignored here, leaving the door open for
cross-row enrichment (Image -> Observation -> Subject context, Diagnosis
traversal) in a later change.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# ERMrest system columns -- never useful in a search chunk.
_SYSTEM_COLUMNS = frozenset({"RID", "RCT", "RMT", "RCB", "RMB"})


def make_enricher(table: str) -> Callable[[dict, Any], Awaitable[str]]:
    """Build the per-row enricher for one eye-ai table.

    The returned coroutine renders a single row of ``table`` to a
    Markdown section. It is the callable passed as the ``enricher=``
    argument to ``ctx.rag_dataset_indexer``.

    Args:
        table: ERMrest-cased table name (e.g. ``"Subject"``). Bound into
            the enricher's H2 header so a search hit names its table.

    Returns:
        An ``async (row: dict, catalog) -> str`` callable. The string is
        Markdown for that one row, or ``""`` for a row with no ``RID``
        (the framework skips empty-string results).

    Example:
        >>> import asyncio
        >>> enrich = make_enricher("Subject")
        >>> asyncio.run(enrich({"RID": "1-A", "Subject_Gender": "Female"}, None))
        '## Subject: 1-A\\n\\n**Subject_Gender:** Female'
    """

    async def enrich(row: dict, catalog: Any) -> str:  # noqa: ARG001 -- signature contract
        rid = row.get("RID")
        if not rid:
            return ""
        lines = [f"## {table}: {rid}", ""]
        for key, value in row.items():
            if key in _SYSTEM_COLUMNS:
                continue
            if value is None or value == "":
                continue
            lines.append(f"**{key}:** {value}")
        return "\n".join(lines)

    return enrich
