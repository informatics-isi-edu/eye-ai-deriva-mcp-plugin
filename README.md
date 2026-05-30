# eye-ai-deriva-mcp-plugin

Eye-AI domain RAG-indexing plugin for [deriva-mcp-core](https://github.com/informatics-isi-edu/deriva-mcp-core).

On connect to an eye-ai catalog, the plugin indexes the catalog's
eye-ai domain tables into the RAG vector store so an LLM can
semantically search eye-ai data via `rag_search`. It ships **no domain
query tools** — generic catalog operations come from `deriva-mcp-core`
and DerivaML operations from the `deriva-ml-mcp` plugin.

## Status

Pre-alpha. Versioned `v0.x.y`.

## What it does

- **On-connect indexing.** An `on_catalog_connect` hook fires when a
  tool connects to a configured eye-ai host. It submits a background
  task that fetches each configured `EyeAI:<table>`, serializes rows to
  Markdown, and writes them to the vector store under catalog-public
  `eye-ai:{host}:{cat}:{schema}.{table}` source names. The catalog has
  auth-gating but **no row-level ACLs**, so a single shared index is
  correct — the `eye-ai:` prefix bypasses the per-user `data:`
  `rag_search` filter and serves chunks to all authorized users.
- **TTL-gated.** Re-indexing on reconnect is skipped within a
  configurable window (default 24h).
- **Manual reindex.** `deriva_eye_ai_reindex_catalog(hostname,
  catalog_id)` forces a full re-index (bypasses the TTL).

## Requirements

- **HTTP transport.** On-connect indexing re-resolves the caller's
  credential from the background TaskManager, which is only available
  in HTTP transport mode. Under stdio transport the background index
  does not run. The dockerized deriva-mcp server runs HTTP, which is
  the intended deployment.
- **RAG enabled.** `DERIVA_MCP_RAG_ENABLED=true`. With RAG disabled the
  plugin loads but the hook and tool are no-ops.

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EYE_AI_DERIVA_MCP_HOSTS` | `www.eye-ai.org,dev.eye-ai.org` | Hosts that trigger indexing |
| `EYE_AI_DERIVA_MCP_TABLES` | placeholder `EyeAI:Subject,...` | `schema:table` list to index |
| `EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS` | `86400` | Re-index TTL |
| `DERIVA_MCP_RAG_ENABLED` | `false` | Must be `true` for any indexing |

> The default `EYE_AI_DERIVA_MCP_TABLES` list is a placeholder
> (`EyeAI:Subject`, `EyeAI:Image`, `EyeAI:Observation`,
> `EyeAI:Diagnosis`, `EyeAI:Condition_Label`). Set the env var (or edit
> `config.py`) to the real curated eye-ai table set.

## Deployment (deriva-docker)

Add to `DERIVA_MCP_EXTRA_PACKAGES` (alongside deriva-ml-mcp + deriva-ml + the deriva-py `deriva-ml` branch):

```bash
DERIVA_MCP_EXTRA_PACKAGES="eye-ai-deriva-mcp-plugin@git+https://github.com/informatics-isi-edu/eye-ai-deriva-mcp-plugin.git@main deriva-ml-mcp@git+https://github.com/informatics-isi-edu/deriva-ml-mcp.git@main deriva-ml@git+https://github.com/informatics-isi-edu/deriva-ml.git@main deriva@git+https://github.com/informatics-isi-edu/deriva-py@deriva-ml"
```

Add `eye-ai-deriva-mcp-plugin` to `DERIVA_MCP_PLUGIN_ALLOWLIST` in `mcp/config/deriva-mcp.env`, then rebuild `--no-cache` + restart. The `scripts/rebuild-deriva-docker-mcp.sh` helper wraps the three commands.

## Development

```bash
uv sync --extra dev          # install
uv run pytest                # test
uv run ruff check src tests  # lint
uv run bump-version patch    # release
```

## License

Apache-2.0.
