# eye-ai-deriva-mcp-plugin

Eye-AI domain RAG-indexing plugin for [deriva-mcp-core](https://github.com/informatics-isi-edu/deriva-mcp-core).

On connect to an eye-ai catalog, the plugin indexes the catalog's
eye-ai clinical domain tables into the RAG vector store so an LLM can
semantically search eye-ai data via `rag_search`, and registers a small
set of eye-ai domain prompts. It ships **no domain query tools** —
generic catalog operations come from `deriva-mcp-core` and DerivaML
operations from the co-loaded `deriva-ml-mcp` plugin (which also already
RAG-indexes all vocabularies and the deriva-ml datasets).

## Status

Pre-alpha. Versioned `v0.x.y`.

## What it does

- **Declarative RAG indexing.** `register()` declares one
  `ctx.rag_dataset_indexer` per (host, table) in the configured set,
  using the same framework API as
  [facebase-deriva-mcp-plugin](https://github.com/informatics-isi-edu/facebase-deriva-mcp-plugin).
  The framework fetches each configured `eye-ai:<table>`, calls the
  plugin's enricher to render each row to Markdown, and writes the
  chunks to the catalog-public `enriched:` RAG source. `is_public=True`
  is correct because the eye-ai catalog has auth-gating but **no
  row-level ACLs** — every authorized user sees the same rows, and
  `rag_search` serves the `enriched:` index to all of them. The
  framework also owns chunking, TTL-gating, credential handling, and the
  on-connect/background execution.
- **Auto-enrich on connect.** Indexers are declared with
  `auto_enrich=True`, so they run automatically on first catalog connect
  when the operator sets `DERIVA_MCP_RAG_AUTO_ENRICH=true`. Manual
  re-indexing is available through the framework's `rag_ingest_datasets`
  tool.
- **Domain prompts.** Three MCP prompts — `eye-ai-assistant`,
  `find-images`, `explore-diagnosis` — prime an LLM for eye-ai
  ophthalmology / retinal-imaging workflows. They complement (do not
  duplicate) the co-loaded `deriva-ml-mcp` plugin's ML-domain prompts.

## Requirements

- **RAG enabled.** `DERIVA_MCP_RAG_ENABLED=true`. With RAG disabled the
  indexer declarations are no-ops (the prompts still register).
- **Auto-enrich enabled** (for automatic on-connect indexing).
  `DERIVA_MCP_RAG_AUTO_ENRICH=true`. With it off, indexing runs only
  when triggered via the `rag_ingest_datasets` tool.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EYE_AI_DERIVA_MCP_HOSTS` | `www.eye-ai.org,dev.eye-ai.org` | Hosts each indexer is scoped to |
| `EYE_AI_DERIVA_MCP_TABLES` | `eye-ai:Subject,eye-ai:Image,eye-ai:Observation,eye-ai:Condition_Label` | `schema:table` list to index |
| `EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS` | `86400` | Re-index TTL |
| `DERIVA_MCP_RAG_ENABLED` | `false` | Must be `true` for any indexing |
| `DERIVA_MCP_RAG_AUTO_ENRICH` | `false` | Must be `true` for automatic on-connect indexing |

> The default `EYE_AI_DERIVA_MCP_TABLES` list is a verified starter set
> (the four tables exist on the live catalog under the `eye-ai` schema).
> The project owner's final curated set is swapped in later via the env
> var or `config.py`.

## Deployment (deriva-docker)

Add to `DERIVA_MCP_EXTRA_PACKAGES` (alongside deriva-ml-mcp + deriva-ml + the deriva-py `deriva-ml` branch):

```bash
DERIVA_MCP_EXTRA_PACKAGES="eye-ai-deriva-mcp-plugin@git+https://github.com/informatics-isi-edu/eye-ai-deriva-mcp-plugin.git@main deriva-ml-mcp@git+https://github.com/informatics-isi-edu/deriva-ml-mcp.git@main deriva-ml@git+https://github.com/informatics-isi-edu/deriva-ml.git@main deriva@git+https://github.com/informatics-isi-edu/deriva-py@deriva-ml"
```

Add `eye-ai` to `DERIVA_MCP_PLUGIN_ALLOWLIST` in `mcp/config/deriva-mcp.env`, then rebuild `--no-cache` + restart. The allowlist matches the **entry-point name** (`eye-ai`, the bare domain), not the distribution name (`eye-ai-deriva-mcp-plugin`) or the import package (`eye_ai_deriva_mcp_plugin`). The `scripts/rebuild-deriva-docker-mcp.sh` helper wraps the three commands.

## Development

```bash
uv sync --extra dev          # install
uv run pytest                # test
uv run ruff check src tests  # lint
uv run bump-version patch    # release
```

## License

Apache-2.0.
