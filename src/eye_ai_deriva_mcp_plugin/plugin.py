"""Plugin entry point: declare the eye-ai RAG indexers + domain prompts.

``register(ctx)`` is called once at server startup by deriva-mcp-core's
plugin loader (subject to ``DERIVA_MCP_PLUGIN_ALLOWLIST``). It wires:

1. One ``ctx.rag_dataset_indexer`` per configured table, scoped to the
   single eye-ai host. Each indexer renders eye-ai clinical rows to
   Markdown and writes them to the catalog-public ``enriched:`` RAG
   source. ``is_public=True`` is correct because the eye-ai catalog has
   auth-gating but no row-level ACLs -- every authorized user sees the
   same rows.
2. One ``ctx.rag_github_source`` for the eye-ai-rag-docs repo, whose
   ``markdown/`` directory holds section-aware Markdown of the project's
   research papers. The framework crawls it (public repo, ``.md`` only)
   and chunks each file by its section headings.
3. One ``ctx.rag_github_source`` for the RETFoundMultimodal repo, whose
   root-level Markdown (README / BENCHMARK / EYE-AI) documents eye-ai's
   RETFound retinal foundation model. ``path_prefix=""`` crawls the whole
   tree; the ``.md``-only crawler ignores the model's Python sources.
4. One ``ctx.rag_web_source`` for the AI-READI documentation site
   (``https://docs.aireadi.org``). AI-READI is a public multimodal
   diabetic-eye dataset that is one of the eye-ai catalog's data
   sources; its docs give the LLM context on that data. It is on-demand
   by default (ingest via ``rag_ingest``); set
   ``DERIVA_MCP_RAG_AUTO_UPDATE_WEB_SOURCES=true`` to autoload it at
   startup.
5. Three eye-ai domain MCP prompts (``eye-ai-assistant``,
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

# The RETFoundMultimodal GitHub source: eye-ai's fork of the RETFound
# retinal foundation model, whose root-level Markdown (README.md,
# BENCHMARK.md, EYE-AI.md) documents the model, its benchmarks, and how it
# integrates with the eye-ai catalog. The repo keeps its docs at the root
# (no ``docs/`` or ``markdown/`` subdir), so ``path_prefix=""`` crawls the
# whole tree -- safe because the framework's GitHub crawler indexes ``.md``
# files only, so the Python sources / notebooks alongside are ignored.
_RETFOUND_RAG_SOURCE = {
    "name": "retfound-multimodal-docs",
    "repo_owner": "eye-ai-usc",
    "repo_name": "RETFoundMultimodal",
    "branch": "main",
    "path_prefix": "",
    "doc_type": "eye-ai-model",
}

# The AI-READI documentation website. AI-READI is a public multimodal
# diabetic-eye dataset ingested into the eye-ai catalog; its docs site
# describes the data. ``allowed_domains`` keeps the crawl on the docs
# subdomain (no off-site link following); ``max_pages`` bounds it.
#
# To autoload this at startup rather than leave it on-demand, set the
# framework env var ``DERIVA_MCP_RAG_AUTO_UPDATE_WEB_SOURCES=true``. The
# framework excludes web sources from the startup pass by default (a web
# crawl competes with ERMrest load on the same host); this plugin declares
# only this one web source, so that switch effectively governs just it.
# Without the env var, ingest on demand via ``rag_ingest`` /
# ``rag_update_docs``.
_AIREADI_WEB_SOURCE = {
    "name": "aireadi-docs",
    "base_url": "https://docs.aireadi.org",
    "max_pages": 200,
    "doc_type": "aireadi-docs",
    "allowed_domains": ["docs.aireadi.org"],
}


def register(ctx: PluginContext) -> None:
    """Register the eye-ai RAG indexers, doc sources, and domain prompts.

    Declares one ``rag_dataset_indexer`` per configured table (scoped to
    the single eye-ai host), the eye-ai-rag-docs papers and
    RETFoundMultimodal model ``rag_github_source`` declarations, the
    AI-READI ``rag_web_source``, then registers the eye-ai domain prompts.
    All RAG registrations are no-ops when RAG is disabled
    (``DERIVA_MCP_RAG_ENABLED=false``); the prompts always register.

    Args:
        ctx: PluginContext supplied by deriva-mcp-core at startup.

    Returns:
        None.

    Example:
        >>> from deriva_mcp_core.plugin.api import PluginContext
        >>> # ctx provided by the framework
        >>> register(ctx)  # doctest: +SKIP
    """
    hostname = config.eye_ai_host(ctx.env)
    tables = config.eye_ai_tables(ctx.env)
    ttl = config.index_ttl_seconds(ctx.env)

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
    ctx.rag_github_source(**_RETFOUND_RAG_SOURCE)
    ctx.rag_web_source(**_AIREADI_WEB_SOURCE)

    prompts.register(ctx)
