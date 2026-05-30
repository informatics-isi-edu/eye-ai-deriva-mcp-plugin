"""Markdown serialization of eye-ai catalog rows for RAG indexing.

One generic serializer renders any eye-ai table row into a Markdown
section: a header line carrying the table name + RID, then each
non-empty, non-system field as a ``**Field:** value`` line. The result
is what gets chunked and embedded; richer per-table serializers can be
added later by dispatching on ``table_name``.
"""

from __future__ import annotations

from typing import Any

from deriva_mcp_core.rag.data import RowSerializer

# ERMrest system columns -- never useful in a search chunk.
_SYSTEM_COLUMNS = frozenset({"RID", "RCT", "RMT", "RCB", "RMB"})


class EyeAIRowSerializer(RowSerializer):
    """Render one eye-ai row to a Markdown section.

    Returns ``None`` for a row with no ``RID`` (cannot anchor a chunk).
    """

    def serialize(self, table_name: str, row: dict[str, Any]) -> str | None:
        """Render ``row`` from ``table_name`` to Markdown, or None.

        Args:
            table_name: ERMrest-cased table name (e.g. ``"Subject"``).
            row: A single entity row dict from an ERMrest fetch.

        Returns:
            A Markdown string, or ``None`` when the row has no RID.

        Example:
            >>> EyeAIRowSerializer().serialize("Subject", {"RID": "1-A", "Name": "x"})
            '## Subject: 1-A\\n\\n**Name:** x'
        """
        rid = row.get("RID")
        if not rid:
            return None
        lines = [f"## {table_name}: {rid}", ""]
        for key, value in row.items():
            if key in _SYSTEM_COLUMNS:
                continue
            if value is None or value == "":
                continue
            lines.append(f"**{key}:** {value}")
        return "\n".join(lines)
