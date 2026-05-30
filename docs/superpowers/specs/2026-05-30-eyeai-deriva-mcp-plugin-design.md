# eyeai-deriva-mcp-plugin — design spec

**Date:** 2026-05-30
**Status:** approved design; ready for implementation plan

## Purpose

A `deriva-mcp-core` plugin that, on connect to an **eye-ai** catalog,
indexes the catalog's eye-ai domain tables into the RAG vector store so
an LLM can semantically search eye-ai data (`rag_search`). The plugin
ships **no domain query tools** in v0.1 — generic catalog operations
come from `deriva-mcp-core`'s built-in tools and DerivaML operations
come from the `deriva-ml-mcp` plugin. This plugin's sole job is
**catalog-data RAG indexing for the eye-ai domain**.

It is a **plugin package**, not a standalone server. The deployable
"MCP server" is `deriva-mcp-core` + this plugin (+ optionally
`deriva-ml-mcp`), wired together in a `deriva-docker` deployment via
`DERIVA_MCP_EXTRA_PACKAGES` and `DERIVA_MCP_PLUGIN_ALLOWLIST`.

## Non-goals (v0.1)

- No eye-ai domain query/lookup tools (RAG-indexing only).
- No MCP prompts (the generic-catalog + deriva-ml conceptual frames
  are already served by those plugins' prompts).
- No GitHub documentation RAG source (plugin docs are thin; marginal
  value — dropped per design review).
- No per-user ACL partitioning (the eye-ai catalog has auth-gating but
  **no row-level ACLs** — every authorized user sees everything, so a
  single catalog-public shared index is correct and safe).

## Repository & package layout

- **Repo:** `informatics-isi-edu/eyeai-deriva-mcp-plugin`
- **Python package:** `eyeai_deriva_mcp_plugin`
- **Entry-point name:** `eyeai-deriva-mcp-plugin` (deliberately identical
  to the PyPI/package name so the deriva-docker
  `DERIVA_MCP_PLUGIN_ALLOWLIST` value works without the
  name-vs-package confusion that bit deriva-ml-mcp early on).

```
eyeai-deriva-mcp-plugin/
├── pyproject.toml
├── README.md
├── CLAUDE.md
├── LICENSE                       # Apache-2.0
├── .gitignore
├── docs/
│   └── superpowers/specs/2026-05-30-eyeai-deriva-mcp-plugin-design.md
├── src/eyeai_deriva_mcp_plugin/
│   ├── __init__.py
│   ├── plugin.py                 # register(ctx) entry point
│   ├── config.py                 # host list, table list, TTL (env-overridable)
│   ├── indexing.py               # the on_catalog_connect hook + background index task
│   ├── serializers.py            # per-table RowSerializer subclasses
│   └── maintenance.py            # deriva_eyeai_reindex_catalog tool
└── tests/
    ├── conftest.py               # _CapturingMCP fixtures (from authoring guide)
    ├── test_plugin.py            # registration + entry-point name
    ├── test_indexing.py          # host-gate, TTL skip, task submission, write shape
    ├── test_serializers.py       # per-table markdown rendering
    └── test_maintenance.py       # reindex tool
```

## Dependencies

```toml
dependencies = [
    "deriva-mcp-core",
    "deriva-ml>=1.38.0",          # DerivaML-based catalog access for fetches
    "deriva @ git+https://github.com/informatics-isi-edu/deriva-py@deriva-ml",
]
[project.optional-dependencies]
system-certs = ["pip-system-certs>=5.3"]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23", "pytest-cov>=5.0", "ruff>=0.4", "bump-my-version"]
```

The direct `deriva @ git+...@deriva-ml` pin in `[project.dependencies]`
(plus `allow-direct-references = true` under `[tool.hatch.metadata]`)
mirrors the deriva-ml-mcp lesson: the wheel METADATA must name the
`deriva-ml` branch, not just `[tool.uv] override-dependencies` (which is
uv-local and does not ship). The `[tool.uv] override-dependencies` block
restates the pin to resolve the conflict with deriva-mcp-core's
`@master` pin during local `uv sync`.

`[tool.uv.sources]` declares editable path deps on `../deriva-mcp-core`
and `../deriva-ml` for workspace development, matching the sibling-repo
layout used by deriva-ml-mcp.

## Configuration (`config.py`)

All values are module constants with env overrides (read from `ctx.env`,
the merged env-file + os.environ map the framework provides):

| Constant | Default | Env override | Meaning |
|---|---|---|---|
| `EYEAI_HOSTS` | `{"www.eye-ai.org", "dev.eye-ai.org"}` | `EYEAI_DERIVA_MCP_HOSTS` (comma-sep) | Hostnames that trigger indexing. The hook no-ops on any other host. |
| `EYEAI_TABLES` | **placeholder list — finalized at spec review** | `EYEAI_DERIVA_MCP_TABLES` (comma-sep `schema:table`) | The eye-ai domain tables to index. |
| `EYEAI_INDEX_TTL_SECONDS` | `86400` (24h) | `EYEAI_DERIVA_MCP_INDEX_TTL_SECONDS` | Skip the on-connect background index if the catalog was indexed within this window. |

**Placeholder `EYEAI_TABLES` (build with this; user corrects later):**
`["EyeAI:Subject", "EyeAI:Image", "EyeAI:Observation",
"EyeAI:Diagnosis", "EyeAI:Condition_Label"]`. Per user direction,
implementation proceeds with this placeholder; the real curated list is
supplied later and swapped in via the one module constant + env
override. The indexer treats this list as the source of truth; it does
NOT auto-discover (per design decision — explicit curated list, not
schema-walk). Schema name `EyeAI` is confirmed.

## The on-connect indexer (`indexing.py`)

One `on_catalog_connect` hook registered via `ctx.on_catalog_connect`.
Signature per the authoring guide:
`async (hostname, catalog_id, schema_hash, schema_json) -> None`.

Hook flow:

1. **Host gate.** If `hostname not in EYEAI_HOSTS`, return immediately
   (debug-log and no-op). This makes the plugin safe to load on a
   multi-catalog server — it only acts on eye-ai catalogs.
2. **RAG-enabled gate.** If `get_rag_store()` returns `None` (RAG
   disabled in this deployment), return. Registration is always safe;
   the hook is a runtime no-op when RAG is off.
3. **TTL gate.** If the catalog's eye-ai index was written within
   `EYEAI_INDEX_TTL_SECONDS`, skip. Freshness is tracked per
   `(host, catalog_id)` using the store's source-timestamp metadata
   (same mechanism the framework's doc-source TTL uses). The manual
   reindex tool bypasses this gate.
4. **Submit background task.** `ctx.submit_task(_index_catalog(...),
   name="eyeai index {host}/{cat}")`. The connect call returns
   immediately; the full index runs async with no per-table row cap
   (background tasks are exempt from the bounded-per-call rule because
   they are not a tool response — they stream into the store). This
   matches how core's startup doc crawl runs.

`_index_catalog(host, catalog_id)` background coroutine:

- Re-resolves the credential from the TaskManager (background tasks do
  not carry the request contextvar credential — per the authoring
  guide's "Credential re-exchange for long tasks").
- For each `schema:table` in `EYEAI_TABLES`:
  - Fetches all rows under the resolved credential (in a worker thread
    via `asyncio.to_thread` — deriva-py I/O is sync).
  - Renders each row to Markdown via the table's `RowSerializer`
    (falling back to the generic serializer for unlisted tables).
  - Writes chunks to the vector store under a **catalog-public source
    name** of shape `eyeai:{host}:{cat}:{schema}.{table}` via direct
    `store.delete_source` + `store.add` (replace-then-write, so a
    re-index cleanly supersedes the prior pass).
- The `eyeai:` source prefix is deliberately NOT one of the prefixes
  the upstream `rag_search` user-id filter gates on (`data:`,
  `schema:`, `enriched:`) — verified the same way deriva-ml-mcp's
  `vocab:` prefix bypasses it — so the chunks are served to **all**
  authorized users. This is correct because eye-ai has no row-level
  ACLs.
- Per-table fetch failures are isolated (logged, loop continues). Per-
  row write failures are isolated (logged, loop continues). One bad
  table or row never poisons the whole pass.

**Why direct store writes, not `ctx.rag_dataset_indexer`:**
`rag_dataset_indexer` produces a single global `enriched:` source whose
enricher fires under whichever credential connects first, and its
source naming is fixed. We want (a) a `eyeai:`-prefixed public source
name (not `enriched:`), (b) replace-then-write per table for clean
re-index, and (c) no dependence on the `DERIVA_MCP_RAG_AUTO_ENRICH`
operator flag. Direct writes give all three. This mirrors the choice
deriva-ml-mcp made for its vocabulary indexer.

## Serializers (`serializers.py`)

One `RowSerializer` subclass per eye-ai table that benefits from rich
rendering (header line with a human label + RID, key fields as
`**Field:** value`, empty fields omitted). Tables without a dedicated
serializer fall through to core's generic serializer
(`## TableName: RID` + `**Column:** value` lines). The concrete set of
serializers is finalized alongside the table list at spec review.

## Maintenance tool (`maintenance.py`)

One tool, `mutates=False` (writes the vector store, not the catalog):

```
deriva_eyeai_reindex_catalog(hostname, catalog_id) -> str
```

- Host-gated identically to the hook (returns an error envelope if the
  host is not an eye-ai host, so a misdirected call is obvious).
- Bypasses the TTL gate — always re-indexes.
- Runs the same `_index_catalog` logic, returns
  `{"status": "reindexed", "host", "catalog_id", "tables_indexed": N,
  "rows_indexed": M}` (or `{"error": ...}`).
- Mirrors deriva-ml-mcp's `deriva_ml_reindex_vocabularies` /
  `deriva_ml_resync_indexes` maintenance-tool pattern.

This is the bridge for cross-user / out-of-band freshness (e.g. someone
loaded new eye-ai data via Chaise; the TTL has not expired; a user
calls this to force a refresh).

## Stateless / bounded-resource compliance

The plugin is designed to satisfy the same rule deriva-ml-mcp
formalized (and which this plugin's CLAUDE.md will restate):

- The **maintenance tool** is bounded — it returns counts, not data,
  and consumes no unbounded per-call resource on the wire.
- The **indexing** itself runs as a background task writing to the
  server-side vector store. The vector store IS legitimate server-side
  state (it is the RAG index, shared infrastructure, not per-user
  workspace state) — same posture as every other plugin's RAG
  indexing. No `~/.deriva-ml/` workspace reads, no local-FS bag
  materialization, no git introspection.

## Testing

`tests/conftest.py` copies the `_CapturingMCP` + `ctx` fixtures from the
authoring guide. Test modules:

- **`test_plugin.py`** — `register(ctx)` runs without error; the
  entry-point name resolves to `register`; the expected tool set
  (`{deriva_eyeai_reindex_catalog}`) and the catalog-connect hook are
  registered.
- **`test_indexing.py`** — host gate (non-eye-ai host → no task
  submitted); RAG-disabled gate (no store → no-op); TTL skip (fresh →
  no task); task submission on a fresh eye-ai catalog; the per-table
  fetch → serialize → `store.delete_source + store.add` write shape;
  source-name shape `eyeai:{host}:{cat}:{schema}.{table}`; fetch-error
  and row-error isolation.
- **`test_serializers.py`** — each serializer renders the expected
  Markdown; unlisted table falls through to the generic serializer.
- **`test_maintenance.py`** — reindex tool host-gates, bypasses TTL,
  returns counts; error envelope on non-eye-ai host and on fetch
  failure.

All sync deriva-ml/deriva-py calls inside async tool/hook bodies are
wrapped in `asyncio.to_thread` (the load-bearing rule from
deriva-ml-mcp; a structural AST test can be ported later if the surface
grows).

## Docs & conventions (`CLAUDE.md`, `README.md`)

`CLAUDE.md` mirrors the deriva-ml-mcp conventions:
- `uv` for everything; Google-style docstrings with examples; no
  backwards-compat shims; no over-engineering.
- The stateless / bounded-resource rule (restated; the plugin must obey
  it as it grows).
- Tool implementation rules (explicit `mutates=`, `deriva_call()`
  wrapping, `asyncio.to_thread` for sync calls, audit events for
  mutating tools — though v0.1 has none).
- The deriva-docker run section: the `DERIVA_MCP_EXTRA_PACKAGES`
  incantation (this plugin + deriva-ml + deriva-py branch), the
  `DERIVA_MCP_PLUGIN_ALLOWLIST=...,eyeai-deriva-mcp-plugin` requirement,
  and the rebuild/restart flow.
- The entry-point-name == package-name rule (with the deriva-ml-mcp war
  story as the rationale).

`README.md`: what the plugin does, install (uv-tool + deriva-docker),
the eye-ai host/table config knobs, and the `rag_search` usage example.

## Versioning

Pre-release `v0.x.y` semver starting at `v0.1.0`, via the shared
`bump-version` CLI (never `bump-my-version` directly). Working tree must
be clean before bumping; tag + commit pushed automatically.

## Deployment (deriva-docker)

The plugin is added to a deriva-docker deployment by:
1. Adding it to `DERIVA_MCP_EXTRA_PACKAGES` (git ref) alongside
   deriva-ml and the deriva-py `deriva-ml` branch.
2. Adding `eyeai-deriva-mcp-plugin` to `DERIVA_MCP_PLUGIN_ALLOWLIST` in
   `mcp/config/deriva-mcp.env`.
3. Rebuild `--no-cache` + restart.
A `scripts/rebuild-deriva-docker-mcp.sh` helper (ported from
deriva-ml-mcp) wraps the rebuild.

On first connect to an eye-ai catalog with RAG enabled, the plugin
indexes the configured eye-ai tables in the background; `rag_search`
returns eye-ai data chunks thereafter.

## Resolved at spec review (2026-05-30)

- **Domain schema name:** `EyeAI` (confirmed). The placeholder
  `EYEAI_TABLES` entries use `EyeAI:<Table>`.
- **Co-located `deriva-ml-mcp`:** yes. The target deployment runs this
  plugin alongside `deriva-ml-mcp`; the CLAUDE.md deployment example
  lists both in `DERIVA_MCP_PLUGIN_ALLOWLIST` and
  `DERIVA_MCP_EXTRA_PACKAGES`.

## Still open (deferred — implement with placeholders, user corrects later)

1. **The `EYEAI_TABLES` list** — the user will supply the curated set
   of `EyeAI:<Table>` names (and thus which serializers to write).
   Implementation proceeds with the placeholder list
   (`EyeAI:Subject`, `EyeAI:Image`, `EyeAI:Observation`,
   `EyeAI:Diagnosis`, `EyeAI:Condition_Label`); the list lives in one
   module constant + an env override, so correcting it later is a
   one-line change plus (optionally) adding/removing a serializer.
   Per user direction: build with placeholders, correct later.
