"""Plugin entry point: register the eye-ai indexer + maintenance tool.

``register(ctx)`` is called once at server startup by deriva-mcp-core's
plugin loader (subject to ``DERIVA_MCP_PLUGIN_ALLOWLIST``). It wires:

1. The ``on_catalog_connect`` hook that indexes eye-ai catalogs on
   connect (host/RAG/TTL gated; background task).
2. The ``deriva_eye_ai_reindex_catalog`` maintenance tool.

No domain query tools and no prompts in v0.1 -- generic catalog tools
come from core and DerivaML tools from the deriva-ml-mcp sibling plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eye_ai_deriva_mcp_plugin.indexing import make_catalog_connect_hook
from eye_ai_deriva_mcp_plugin.maintenance import register_maintenance_tools

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext


def register(ctx: PluginContext) -> None:
    """Register the eye-ai plugin's hook and tool with ``ctx``.

    Args:
        ctx: PluginContext supplied by deriva-mcp-core at startup.

    Returns:
        None.

    Example:
        >>> from deriva_mcp_core.plugin.api import PluginContext
        >>> # ctx provided by the framework
        >>> register(ctx)  # doctest: +SKIP
    """
    ctx.on_catalog_connect(make_catalog_connect_hook(ctx))
    register_maintenance_tools(ctx)
