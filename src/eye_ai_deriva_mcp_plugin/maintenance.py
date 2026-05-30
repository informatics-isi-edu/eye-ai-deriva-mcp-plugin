"""Manual re-index maintenance tool.

``deriva_eye_ai_reindex_catalog`` forces a full re-index of an eye-ai
catalog's configured tables, bypassing the on-connect TTL gate. Use it
when data changed out of band (e.g. via Chaise) and the TTL has not
expired. ``mutates=False`` -- it writes the vector store, not the
catalog, so it is not affected by the mutation kill switch.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eye_ai_deriva_mcp_plugin import config
from eye_ai_deriva_mcp_plugin.indexing import _index_catalog

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext


def register_maintenance_tools(ctx: PluginContext) -> None:
    """Register the eye-ai maintenance tool(s) on ``ctx``.

    Args:
        ctx: The plugin context.

    Returns:
        None.

    Example:
        >>> from deriva_mcp_core.plugin.api import PluginContext
        >>> # ctx provided by the framework
        >>> register_maintenance_tools(ctx)  # doctest: +SKIP
    """
    hosts = config.eye_ai_hosts(ctx.env)
    tables = config.eye_ai_tables(ctx.env)

    @ctx.tool(mutates=False)
    async def deriva_eye_ai_reindex_catalog(hostname: str, catalog_id: str) -> str:
        """Force a full re-index of an eye-ai catalog's configured tables.

        Bypasses the on-connect TTL gate. Host-gated: returns an error
        envelope if ``hostname`` is not a configured eye-ai host.

        Args:
            hostname: An eye-ai Deriva hostname (e.g. ``"www.eye-ai.org"``).
            catalog_id: The catalog ID as a string.

        Returns:
            JSON string ``{"status": "reindexed", "host", "catalog_id",
            "tables_indexed", "tables_failed", "rows_indexed"}`` on
            success, or ``{"error": "..."}`` on failure / wrong host.

        Example:
            ``{"status": "reindexed", "host": "www.eye-ai.org",
            "catalog_id": "5", "tables_indexed": 5, "tables_failed": 0,
            "rows_indexed": 1234}``
        """
        import json

        if hostname not in hosts:
            return json.dumps({"error": f"{hostname} is not a configured eye-ai host"})
        try:
            result = await _index_catalog(hostname, catalog_id, tables, ctx.env)
        except Exception as exc:  # noqa: BLE001 -- surface as an error envelope
            return json.dumps({"error": str(exc)})
        return json.dumps(
            {
                "status": "reindexed",
                "host": hostname,
                "catalog_id": catalog_id,
                **result,
            }
        )
