"""Plugin entry point: declare the eye-ai RAG indexers + domain prompts.

``register(ctx)`` is called once at server startup by deriva-mcp-core's
plugin loader (subject to ``DERIVA_MCP_PLUGIN_ALLOWLIST``). It wires:

1. One ``ctx.rag_dataset_indexer`` per (host, table) in the configured
   set. Each indexer renders eye-ai clinical rows to Markdown and writes
   them to the catalog-public ``enriched:`` RAG source. ``is_public=True``
   is correct because the eye-ai catalog has auth-gating but no row-level
   ACLs -- every authorized user sees the same rows.
2. One ``ctx.rag_github_source`` for the eye-ai-rag-docs repo, whose
   ``markdown/`` directory holds section-aware Markdown of the project's
   research papers. The framework crawls it (public repo, ``.md`` only)
   and chunks each file by its section headings.
3. Three eye-ai domain MCP prompts (``eye-ai-assistant``,
   ``find-images``, ``explore-diagnosis``).

The framework owns fetching, chunking, TTL-gating, credential handling,
source naming, and the on-connect/background execution -- this plugin
only declares what to index and how to render a row. ``auto_enrich=True``
marks the indexers eligible for automatic on-connect execution (the
operator still gates it with ``DERIVA_MCP_RAG_AUTO_ENRICH=true``); manual
re-indexing is available through the framework's ``rag_ingest_datasets``
tool.

No domain query tools -- generic catalog tools come from core and
DerivaML tools from the co-loaded deriva-ml-mcp-plugin (which also
already RAG-indexes all vocabularies and the deriva-ml datasets).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from eye_ai_deriva_mcp_plugin import config, prompts
from eye_ai_deriva_mcp_plugin.enricher import make_enricher

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext

_DOC_TYPE = "eye-ai-data"

# The eye-ai-rag-docs GitHub source: section-aware Markdown of the
# project's research papers, under the repo's ``markdown/`` prefix. The
# framework's GitHub crawler indexes ``.md`` files only, so the PDFs that
# sit alongside in that repo are ignored; the Markdown is what gets
# chunked (by its ## / ### section headings) and searched.
_PAPERS_RAG_SOURCE = {
    "name": "eye-ai-rag-docs",
    "repo_owner": "eye-ai-usc",
    "repo_name": "eye-ai-rag-docs",
    "branch": "main",
    "path_prefix": "markdown/",
    "doc_type": "eye-ai-paper",
}


def register(ctx: PluginContext) -> None:
    """Register the eye-ai RAG indexers, papers source, and domain prompts.

    Declares one ``rag_dataset_indexer`` per (host, schema, table) in the
    configured set, the eye-ai-rag-docs papers ``rag_github_source``, then
    registers the eye-ai domain prompts. All RAG registrations are no-ops
    when RAG is disabled (``DERIVA_MCP_RAG_ENABLED=false``); the prompts
    always register.

    Args:
        ctx: PluginContext supplied by deriva-mcp-core at startup.

    Returns:
        None.

    Example:
        >>> from deriva_mcp_core.plugin.api import PluginContext
        >>> # ctx provided by the framework
        >>> register(ctx)  # doctest: +SKIP
    """
    hosts = sorted(config.eye_ai_hosts(ctx.env))
    tables = config.eye_ai_tables(ctx.env)
    ttl = config.index_ttl_seconds(ctx.env)

    for hostname in hosts:
        for schema, table in tables:
            ctx.rag_dataset_indexer(
                schema=schema,
                table=table,
                enricher=make_enricher(table),
                doc_type=_DOC_TYPE,
                ttl_seconds=ttl,
                hostname=hostname,
                auto_enrich=True,
                is_public=True,
            )

    ctx.rag_github_source(**_PAPERS_RAG_SOURCE)

    prompts.register(ctx)
