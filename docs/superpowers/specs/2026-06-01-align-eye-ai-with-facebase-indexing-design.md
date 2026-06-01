# Align eye-ai with facebase: declarative indexer + domain prompts

**Date:** 2026-06-01
**Status:** Approved (design)
**Supersedes:** the v1 draft of this file (indexing-only scope).

## Goal

Bring the eye-ai plugin in line with the
[`facebase-deriva-mcp-plugin`](https://github.com/informatics-isi-edu/facebase-deriva-mcp-plugin)
shape on two axes:

1. **Indexing mechanism** — replace the hand-rolled `on_catalog_connect` +
   background-task RAG indexer with the framework's declarative
   `ctx.rag_dataset_indexer()`, exactly as facebase uses it.
2. **Domain prompts** — add three eye-ai-themed MCP prompts (assistant +
   two task workflows), mirroring facebase's `facebase-assistant` /
   `find-datasets` / `explore-anatomy` trio.

## Context: what the co-loaded sibling already covers

Eye-ai is always deployed alongside `deriva-ml-mcp-plugin`. That sibling's
`resources/rag.py` already RAG-indexes, on every catalog connect:

- **All vocabularies in any schema**, catalog-public, via
  `ml.find_vocabularies()` → `vocab:` source prefix. This already covers
  eye-ai's domain vocab tables: `Subject_Gender`, `Subject_Ethnicity`,
  `Image_Side`, `Image_Angle`, `Image_Tag`, `Modality_Type`,
  `Condition_Label`, `Severity_Label`, the `Diagnosis_*` vocabs, and the
  eight `Subject_*` clinical-flag vocabs.
- **All `deriva-ml` Dataset / Workflow / Execution rows**, per-user-per-RID.

And its prompts (`deriva_ml_concepts`, `deriva_ml_getting_started`) cover only
the **ML-domain layer** (the five abstractions, stateless model, pagination,
tool domains) — not eye-ai's clinical domain.

**Implication for this plugin's scope:** eye-ai's unique contribution is
indexing the **clinical domain data rows** (`Subject`, `Image`, `Observation`)
that the sibling does not touch, plus **eye-ai-domain prompts** that neither the
sibling nor core provides. Per the decision below we also index
`Condition_Label` (accepting minor redundancy with the sibling's vocab hook).

## Why facebase's mechanism is SAFE here (the load-bearing fact)

`rag_dataset_indexer` writes a **catalog-public** shared index under the
`enriched:` prefix, which `rag_search` serves to every authorized user of the
catalog (`deriva-mcp-core/.../rag/tools.py` ~line 463-471). The sibling
deliberately avoids `rag_dataset_indexer` for ML data because that data has
**per-user ACLs** and a shared index would leak rows across users
(`resources/rag.py:40-46`).

**Eye-ai's clinical tables have NO row-level ACLs** — catalog-level
auth-gating only; every authorized user sees the same rows (confirmed by the
catalog owner, 2026-06-01; recorded in memory `eye-ai-no-row-acls`). Therefore
the shared `enriched:` index is correct and safe here, and facebase's mechanism
is the right choice. This is the OPPOSITE posture from the sibling's ML data,
and the difference is intentional and documented.

> If eye-ai ever gains per-user row ACLs on clinical tables, this mechanism
> would leak rows and must switch to the sibling's per-user pattern. Re-verify
> before assuming.

## Decisions (confirmed)

| # | Decision |
|---|---|
| 1 | **Mechanism:** `ctx.rag_dataset_indexer(..., is_public=True, auto_enrich=True)`. |
| 2 | **Host scoping:** register per host — loop `{www.eye-ai.org, dev.eye-ai.org}` × tables, one indexer per `(host, schema, table)`. Hosts sorted for deterministic registration order. |
| 3 | **Tables:** schema `eye-ai`; tables `Subject`, `Image`, `Observation`, `Condition_Label` (the four that exist; `Diagnosis` dropped — it does not exist as a table). |
| 4 | **Maintenance tool:** drop `deriva_eye_ai_reindex_catalog`; manual reindex via the framework's built-in `rag_ingest_datasets`. |
| 5 | **Prompts:** add three eye-ai domain prompts now (best draft from schema + facebase structure, for owner review in PR). |
| 6 | **README allowlist fix:** `eye-ai` (not `eye-ai-deriva-mcp-plugin`). |

## Architecture (after)

```
src/eye_ai_deriva_mcp_plugin/
├── plugin.py     # register(ctx): rag indexers (loop) + prompts.register(ctx)
├── config.py     # eye_ai_hosts / eye_ai_tables / index_ttl_seconds  (API unchanged)
├── enricher.py   # make_enricher(table) -> async (row, catalog) -> str  (flat Markdown)
└── prompts.py    # register(ctx): 3 eye-ai MCP prompts
```

Deleted: `indexing.py`, `maintenance.py`, `serializers.py`.

### `plugin.py`

```python
def register(ctx: PluginContext) -> None:
    hosts = sorted(config.eye_ai_hosts(ctx.env))
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
    prompts.register(ctx)
```

`register` stays synchronous. No hook, no `submit_task`, no maintenance tool.

### `enricher.py`

Ports the existing `EyeAIRowSerializer` rendering into the framework's enricher
signature `async (row, catalog) -> str`. Same flat Markdown the serializer
produced: `## {table}: {RID}` header, blank line, then `**Field:** value` per
non-empty, non-system column (system set: `RID RCT RMT RCB RMB`). RID-less rows
return `""` (framework skips empty strings).

**No FK joins.** Eye-ai's categorical FKs reference the vocabulary's `Name`
column, so the fetched row dict already carries readable labels
(`**Subject_Gender:** Female`) with zero extra fetches — unlike facebase, whose
vocab FKs are RID-referencing and require resolution. The `catalog` parameter
is accepted and ignored, leaving the door open for cross-row enrichment
(Image→Observation→Subject context; Diagnosis traversal) in a later change.

### `prompts.py`

Three static-string prompts, facebase's `prompts.py` as the structural
template, re-themed for ophthalmology / retinal imaging and pointed at the real
eye-ai schema. (Facebase's string-concat spacing bug between the assistant body
and "ADDITIONAL INSTRUCTIONS" is fixed in the port, not copied.)

| Prompt | Purpose | Schema touchpoints |
|---|---|---|
| `eye-ai-assistant` | Orientation: ophthalmology/retinal-imaging research assistant over the eye-ai catalog. | Subject / Image / Observation; diagnosis & imaging vocabularies. |
| `find-images` | Find fundus/OCT images by diagnosis, modality, laterality, angle. | `Image` + `Image_Diagnosis` assoc → `Diagnosis_Image` vocab; `Image_Side`, `Image_Angle`, `Modality_Type`. |
| `explore-diagnosis` | Given a condition, traverse to linked subjects/images/observations. | `Diagnosis_Image` vocab ← `Image_Diagnosis`/`Subject_Diagnosis`/`Observation_Diagnosis` assoc → domain rows. |

All three take `hostname`/`catalog_id` args (defaulting to `www.eye-ai.org` /
`eye-ai`) like facebase. They reference `rag_search` and generic
`deriva-mcp-core` query tools — they do not assume any eye-ai-specific tool
(this plugin ships none).

### `config.py`

- `eye_ai_hosts` / `index_ttl_seconds`: unchanged.
- `_DEFAULT_TABLES` → `("eye-ai", "Subject")`, `("eye-ai", "Image")`,
  `("eye-ai", "Observation")`, `("eye-ai", "Condition_Label")`.
- `eye_ai_tables` env-override parsing unchanged (`schema:table` tokens).

## Tests (after)

| File | Action |
|---|---|
| `tests/test_config.py` | Update `_DEFAULT_TABLES` expectations (schema `eye-ai`, 4 tables). |
| `tests/test_enricher.py` | New. Port the three serializer cases to `make_enricher(table)`: header+fields; omit empty/system; `""` for RID-less row. |
| `tests/test_prompts.py` | New. Assert the three prompts register, are non-empty, contain no f-string leakage (`{`/`}` only where intended), and name the right schema/tables. |
| `tests/test_plugin.py` | Rewrite: `register(ctx)` registers `len(hosts)*len(tables)` indexers (all `is_public=True`, `auto_enrich=True`) AND 3 prompts; no `on_catalog_connect` hook, no tool. Entry point resolves to `register`. |
| `tests/test_serializers.py`, `test_indexing.py`, `test_maintenance.py` | Delete. |
| `tests/conftest.py` | Extend capturing ctx to record `rag_dataset_indexer` declarations and `prompt` registrations (facebase conftest is the template). |

## Docs

- **`README.md`**: rewrite to the declarative model (drop on-connect-hook /
  background-task / HTTP-only / stdio-caveat language); document the 3 prompts;
  note `auto_enrich` needs `DERIVA_MCP_RAG_ENABLED=true` +
  `DERIVA_MCP_RAG_AUTO_ENRICH=true`; manual reindex via `rag_ingest_datasets`;
  **fix allowlist token to `eye-ai`**; drop `deriva_eye_ai_reindex_catalog`.
- **`CLAUDE.md`**: update the Architecture file map and "Key design decisions"
  to the declarative indexer + prompts; remove the hand-rolled-hook /
  background-task / stdio design notes; add a note that the sibling
  `deriva-ml-mcp-plugin` already covers vocabularies + ML rows, so this plugin
  indexes clinical domain rows and ships domain prompts only.

## Out of scope

- Cross-row FK enrichment (Image→Observation→Subject; Diagnosis traversal) —
  flat rows for now; `catalog` param wired for a later change.
- The project owner's final curated table list (verified starter set only).
- A version bump (separate `uv run bump-version` if/when released).

## Verification

- `uv run pytest` green.
- `uv run ruff check src tests` + `uv run ruff format --check src tests` clean.
- Under a capturing ctx: exactly `len(hosts)*len(tables)` indexers (all
  `is_public=True`), 3 prompts, 0 tools, 0 `on_catalog_connect` hooks.
