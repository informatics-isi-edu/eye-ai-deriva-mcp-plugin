# CLAUDE.md

Guidance for Claude Code when working with `eye-ai-deriva-mcp-plugin`.

## Project Overview

A `deriva-mcp-core` plugin that RAG-indexes eye-ai catalog clinical
domain tables and ships eye-ai domain prompts. No domain query tools —
generic catalog tools come from core, DerivaML tools from the
co-located `deriva-ml-mcp` plugin. The deployable MCP server is
`deriva-mcp-core` + this plugin + `deriva-ml-mcp`.

The indexing mechanism is **declarative**, matching
`facebase-deriva-mcp-plugin`: `register()` calls
`ctx.rag_dataset_indexer(...)` per (host, table), and the framework owns
fetching, chunking, TTL-gating, credential handling, source naming, and
the on-connect/background execution. The plugin only supplies *what* to
index (the table list) and *how to render* a row (the enricher).

## Architecture

```
src/eye_ai_deriva_mcp_plugin/
├── plugin.py     # register(ctx): rag_dataset_indexer loop + prompts.register
├── config.py     # host set / table list / TTL (env-overridable)
├── enricher.py   # make_enricher(table) -> async (row, catalog) -> Markdown
└── prompts.py    # register(ctx): 3 eye-ai domain MCP prompts
```

## Key design decisions

- **Catalog-public `enriched:` index.** Eye-ai has auth-gating but **no
  row-level ACLs** (confirmed by the catalog owner) — every authorized
  user sees the same rows. `ctx.rag_dataset_indexer(..., is_public=True)`
  writes the catalog-public `enriched:` source prefix, which `rag_search`
  serves to all users of the catalog. This is correct here and SAFE.
  Note this is the **opposite** posture from the sibling
  `deriva-ml-mcp`, whose ML data has per-user ACLs and therefore
  deliberately avoids `rag_dataset_indexer` (it would leak rows across
  users) in favor of a per-user hand-rolled hook. Eye-ai's clinical data
  needs no such treatment. If eye-ai ever gains row-level ACLs, this
  mechanism would leak and must switch to the per-user pattern.
- **Don't duplicate the sibling.** The co-loaded `deriva-ml-mcp` already
  RAG-indexes all vocabularies (any schema, via `find_vocabularies`) and
  all deriva-ml Dataset/Workflow/Execution rows. So this plugin's clinical
  row indexing targets only domain rows like `Subject`, `Image`,
  `Observation` (avoid `Condition_Label` and other vocab tables — the
  sibling already covers those), and it ships the eye-ai *domain* prompts
  that neither the sibling nor core provides.
- **Clinical-row indexing is opt-in.** `_DEFAULT_TABLES` is empty;
  `EYE_AI_DERIVA_MCP_TABLES` (comma-separated `schema:table`) turns it on.
  With no override the plugin registers no `rag_dataset_indexer` — only
  the papers `rag_github_source` and the prompts. This keeps the default
  deployment from indexing clinical rows until an operator opts in with a
  vetted table list.
- **Flat enricher, no FK joins.** Eye-ai's categorical FKs reference the
  vocabulary's `Name` column, so the fetched row already carries readable
  labels — the flat row-to-Markdown render is sufficient, no resolve
  fetches needed (unlike facebase's RID-referencing FKs). The enricher's
  `catalog` arg is wired but unused, leaving room for cross-row
  enrichment (Image→Observation→Subject; Diagnosis traversal) later.
- **Auto-enrich + manual reindex.** Indexers declare `auto_enrich=True`;
  on-connect execution is operator-gated by `DERIVA_MCP_RAG_AUTO_ENRICH`.
  Manual re-indexing is the framework's `rag_ingest_datasets` tool —
  this plugin ships no maintenance tool.

## Conventions (shared workspace rules)

- **`uv` for everything** — `uv run pytest`, `uv run ruff ...`,
  `uv run bump-version`. Never call the tools directly.
- **Google-style docstrings** with `Args:`/`Returns:`/`Raises:`/
  `Example:`.
- **No backwards-compat shims; no over-engineering.**
- **Entry-point name is the bare domain** (`eye-ai`) — distinct from the
  distribution name (`eye-ai-deriva-mcp-plugin`) and the import package
  (`eye_ai_deriva_mcp_plugin`). The deriva-docker
  `DERIVA_MCP_PLUGIN_ALLOWLIST` value is the entry-point token `eye-ai`,
  matching the `facebase-deriva-mcp-plugin` convention (entry point
  `facebase`).

## Indexer / enricher rules (from the deriva-mcp-core authoring guide)

- The plugin registers no tools and no `on_catalog_connect` hook — the
  framework's `rag_dataset_indexer` owns the on-connect execution. If a
  tool is ever added, it must register with explicit `mutates=`.
- The enricher is `async (row, catalog) -> str`. It must not block: any
  catalog I/O it adds later must be wrapped in `await
  asyncio.to_thread(...)` (the framework calls it once per row, so a
  blocking call would stall the event loop for the whole pass). The
  current enricher does no I/O.
- Returning `""` from the enricher skips the row (framework contract).

## Stateless / bounded-resource rule

The indexing writes into the shared vector store (legitimate shared RAG
infra, not per-user workspace state) via the framework. No `~/.deriva-ml/`
reads, no local-FS materialization, no git introspection. The prompts are
static strings — no catalog access to render.

## Running under Docker (deriva-docker)

`DERIVA_MCP_EXTRA_PACKAGES` must include this plugin + deriva-ml-mcp +
deriva-ml + the deriva-py `deriva-ml` branch (pip inside the container
does not honor `[tool.uv] override-dependencies`). Add
`eye-ai-deriva-mcp-plugin` to `DERIVA_MCP_PLUGIN_ALLOWLIST`. Rebuild
`--no-cache` (else pip reuses the cached wheel layer):

```bash
docker-compose --env-file ~/.deriva-docker/env/localhost.env down deriva-mcp-test
docker-compose --env-file ~/.deriva-docker/env/localhost.env build deriva-mcp-test --no-cache
docker-compose --env-file ~/.deriva-docker/env/localhost.env up -d deriva-mcp-test
```

`scripts/rebuild-deriva-docker-mcp.sh` wraps these.

## Versioning

Pre-release `v0.x.y` from `v0.1.0`, via `uv run bump-version`. Working
tree must be clean before bumping.

## Development gotchas

- `src/eye_ai_deriva_mcp_plugin/_version.py` is auto-generated by
  hatch-vcs, gitignored, and ruff-excluded. Don't commit or format it.
- House style is `from __future__ import annotations`; leave
  annotations unquoted.
- This repo lives at `/Users/carl/GitHub/DerivaML/eye-ai-deriva-mcp-plugin`,
  a sibling of `deriva-mcp-core`, `deriva-ml`, and `deriva-ml-mcp`. The
  `[tool.uv.sources]` editable path deps (`../deriva-mcp-core`,
  `../deriva-ml`) resolve only from that workspace location.
