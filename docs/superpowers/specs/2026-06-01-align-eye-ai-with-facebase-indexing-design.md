# Align eye-ai indexing with facebase's `rag_dataset_indexer`

**Date:** 2026-06-01
**Status:** Approved (design)

## Goal

Replace the eye-ai plugin's hand-rolled `on_catalog_connect` + background-task
RAG indexer with the framework's declarative `ctx.rag_dataset_indexer()` API,
matching the [`facebase-deriva-mcp-plugin`](https://github.com/informatics-isi-edu/facebase-deriva-mcp-plugin)
mechanism. Net effect: delete ~280 lines of bespoke indexing/maintenance code
and let `deriva-mcp-core` own fetching, chunking, TTL-gating, credential
re-resolution, source naming, and the background task.

## Why this is safe (access-control equivalence)

The original rationale for going hand-rolled was a **catalog-public shared
index**: eye-ai has auth-gating but no row-level ACLs, so every authorized user
should see every indexed row. The hand-rolled code achieved this with a custom
`eye-ai:` source prefix that bypassed `rag_search`'s per-user `data:` filter.

Verified in `deriva-mcp-core`:

- `rag_dataset_indexer` stores enriched rows under the **`enriched:`** prefix
  (`rag/tools.py` `_run_dataset_enricher`, source name
  `enriched:{hostname}:{catalog_id}:{schema}:{table}`).
- `rag_search` restricts `enriched:` results to **this catalog only**
  (`enriched:{hostname}:{catalog_id}:` — `rag/tools.py` ~line 463-471), i.e.
  catalog-public: served to every authorized user of that catalog, not
  per-user.

So `rag_dataset_indexer(..., is_public=True)` yields the **same** access-control
semantics the `eye-ai:` prefix did. Alignment loses nothing. (See memory
`rag-source-prefix-access-control` for the prefix-filtering reference.)

## Decisions (confirmed)

1. **Host scoping: register per host.** Loop the host set × the table list,
   registering one indexer per `(host, schema, table)`. Preserves today's
   `{www.eye-ai.org, dev.eye-ai.org}` gating exactly.
2. **Drop the maintenance tool.** Remove `deriva_eye_ai_reindex_catalog`;
   manual reindex is covered by the framework's built-in `rag_ingest_datasets`
   tool (facebase ships no equivalent).
3. **Fix the table list.** Schema is `eye-ai` (not `EyeAI`); tables are the four
   that exist on the live catalog: `Subject`, `Image`, `Observation`,
   `Condition_Label`. Drop the nonexistent `Diagnosis`. Still a starter set
   pending the project owner's curated list.

## Architecture (after)

```
src/eye_ai_deriva_mcp_plugin/
├── plugin.py     # register(ctx): loop hosts × tables -> ctx.rag_dataset_indexer(...)
├── config.py     # eye_ai_hosts / eye_ai_tables / index_ttl_seconds (unchanged API)
└── enricher.py   # make_enricher(table) -> async (row, catalog) -> str  (Markdown)
```

Deleted: `indexing.py`, `maintenance.py`, `serializers.py`.

### `plugin.py`

```python
def register(ctx: PluginContext) -> None:
    hosts = config.eye_ai_hosts(ctx.env)
    tables = config.eye_ai_tables(ctx.env)
    ttl = config.index_ttl_seconds(ctx.env)
    for hostname in hosts:
        for schema, table in tables:
            ctx.rag_dataset_indexer(
                schema=schema,
                table=table,
                enricher=make_enricher(table),
                doc_type="eye-ai-data",
                ttl_seconds=ttl,
                hostname=hostname,
                auto_enrich=True,
                is_public=True,
            )
```

`register` stays synchronous. No hook, no `submit_task`, no maintenance tool.

### `enricher.py`

Ports the existing `EyeAIRowSerializer` rendering into the framework's enricher
signature. Same Markdown shape the serializer produced:
`## {table}: {RID}` header, blank line, then `**Field:** value` for each
non-empty, non-system column. System columns (`RID`, `RCT`, `RMT`, `RCB`,
`RMB`) are skipped. A row with no `RID` returns `""` (framework skips empty
strings), matching the serializer's `None`-skip behavior.

```python
_SYSTEM_COLUMNS = frozenset({"RID", "RCT", "RMT", "RCB", "RMB"})

def make_enricher(table: str) -> Callable[[dict, Any], Awaitable[str]]:
    async def enrich(row: dict, catalog: Any) -> str:  # catalog unused (no joins yet)
        rid = row.get("RID")
        if not rid:
            return ""
        lines = [f"## {table}: {rid}", ""]
        for key, value in row.items():
            if key in _SYSTEM_COLUMNS or value is None or value == "":
                continue
            lines.append(f"**{key}:** {value}")
        return "\n".join(lines)
    return enrich
```

The enricher does no catalog joins (eye-ai v0.1 indexes flat rows). The
`catalog` parameter is part of the framework's required signature; it is
accepted and ignored, leaving the door open for FK enrichment later (as
facebase does).

### `config.py`

- `eye_ai_hosts` / `index_ttl_seconds`: unchanged.
- `_DEFAULT_TABLES` updated to schema `eye-ai`, tables
  `Subject, Image, Observation, Condition_Label`.
- `eye_ai_tables` env-override parsing unchanged (`schema:table` tokens).

## Tests (after)

| File | Action |
|---|---|
| `tests/test_config.py` | Update `_DEFAULT_TABLES` expectations (schema `eye-ai`, 4 tables). |
| `tests/test_enricher.py` | New. Port the three `test_serializers.py` cases to `make_enricher(table)`: renders header + fields; omits empty/system fields; returns `""` for RID-less row. |
| `tests/test_plugin.py` | Rewrite against facebase's template: `register(ctx)` registers `len(hosts) * len(tables)` indexers; entry point resolves to `register`. Assert via a `_CapturingMCP`/ctx that records `rag_dataset_indexer` calls. |
| `tests/test_serializers.py` | Delete. |
| `tests/test_indexing.py` | Delete. |
| `tests/test_maintenance.py` | Delete. |
| `tests/conftest.py` | Extend the capturing ctx to record `rag_dataset_indexer` declarations (facebase's conftest is the template). |

## Docs

- **`README.md`**: rewrite "What it does" / "Requirements" to the declarative
  model (no on-connect-hook/background-task/HTTP-only language; `rag_search`
  serves the `enriched:` index; manual reindex via `rag_ingest_datasets`). Fix
  the allowlist token to `eye-ai` (was incorrectly `eye-ai-deriva-mcp-plugin`).
  Drop the `deriva_eye_ai_reindex_catalog` reference. Note `auto_enrich`
  requires both `DERIVA_MCP_RAG_ENABLED=true` and
  `DERIVA_MCP_RAG_AUTO_ENRICH=true`.
- **`CLAUDE.md`**: update the Architecture file map and the "Key design
  decisions" section to reflect the declarative indexer; remove the
  hand-rolled-hook / background-task / stdio-caveat design notes that no longer
  apply.

## Out of scope

- FK/vocabulary enrichment (facebase-style joins) — flat rows for v0.1.
- MCP prompts (facebase ships 3; eye-ai intentionally ships none in v0.1).
- The project owner's final curated table list (this lands a verified starter
  set only).
- A version bump (separate `uv run bump-version` step if/when released).

## Verification

- `uv run pytest` green.
- `uv run ruff check src tests` and `uv run ruff format --check src tests`
  clean.
- `register(ctx)` registers the expected number of indexers under a capturing
  ctx; no `on_catalog_connect` hook and no tool are registered.
