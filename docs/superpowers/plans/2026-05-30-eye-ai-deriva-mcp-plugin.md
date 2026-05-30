# eye-ai-deriva-mcp-plugin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `deriva-mcp-core` plugin that indexes eye-ai catalog domain tables into the RAG vector store on connect, so `rag_search` returns eye-ai data.

**Architecture:** A plugin package exposing a `register(ctx)` entry point. On connect to an eye-ai hostname, an `on_catalog_connect` hook submits a TTL-gated background task that fetches each configured `EyeAI:<table>` via generic ERMrest (`get_catalog`), serializes rows to Markdown, and writes them to the vector store under catalog-public `eye-ai:{host}:{cat}:{schema}.{table}` source names (no per-user ACL split — eye-ai has none). One maintenance tool (`deriva_eye_ai_reindex_catalog`) forces a re-index.

**Tech Stack:** Python 3.12+, `uv`, `deriva-mcp-core` (plugin API + RAG store), `deriva-py` (ERMrest), `ruff`, `pytest`/`pytest-asyncio`, `hatchling`/`hatch-vcs`.

---

## File Structure

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, entry point, ruff/pytest/bumpversion config |
| `src/eye_ai_deriva_mcp_plugin/__init__.py` | Package marker |
| `src/eye_ai_deriva_mcp_plugin/config.py` | Host set, table list, TTL — module constants + env overrides |
| `src/eye_ai_deriva_mcp_plugin/serializers.py` | `EyeAIRowSerializer` (generic eye-ai row → Markdown) |
| `src/eye_ai_deriva_mcp_plugin/indexing.py` | `_source_name`, `_fetch_table_rows`, `_index_catalog`, `_is_index_fresh`, `make_catalog_connect_hook` |
| `src/eye_ai_deriva_mcp_plugin/maintenance.py` | `register_maintenance_tools(ctx)` → `deriva_eye_ai_reindex_catalog` |
| `src/eye_ai_deriva_mcp_plugin/plugin.py` | `register(ctx)` — wires the hook + the maintenance tool |
| `tests/conftest.py` | `_CapturingMCP` + `ctx` fixtures (from authoring guide) |
| `tests/test_config.py` | env-override parsing |
| `tests/test_serializers.py` | row → Markdown |
| `tests/test_indexing.py` | source name, fetch, freshness, `_index_catalog`, hook gating |
| `tests/test_maintenance.py` | reindex tool host-gate + counts + error envelope |
| `tests/test_plugin.py` | registration, entry-point resolves, expected surface |
| `CLAUDE.md`, `README.md`, `LICENSE`, `.gitignore` | docs/meta |
| `scripts/rebuild-deriva-docker-mcp.sh` | deriva-docker rebuild helper |

**Reference facts (verified against deriva-mcp-core @ this checkout):**

- `from deriva_mcp_core.plugin.api import PluginContext`
- `from deriva_mcp_core.rag import get_rag_store` → returns a `VectorStore | None` (`None` when RAG disabled).
- `from deriva_mcp_core.rag.store import Chunk, VectorStore`
  - `Chunk(text, source, doc_type, section_heading="", heading_hierarchy=[], chunk_index=0, url="", title="")`
  - `await store.add(chunks: list[Chunk]) -> None`
  - `await store.delete_source(source: str) -> None`
  - `await store.has_source(source: str) -> bool`
  - `await store.source_stats() -> dict[str, SourceStats]`; `SourceStats(chunk_count: int, indexed_at: str | None)` where `indexed_at` is ISO-8601.
- `from deriva_mcp_core.rag.chunker import chunk_markdown` → `chunk_markdown(text, source=..., doc_type=...)` yields chunk-like objects with `.text`, `.section_heading`, `.heading_hierarchy`.
- `from deriva_mcp_core.rag.data import RowSerializer`; subclass and implement `serialize(self, table_name: str, row: dict) -> str | None`.
- `from deriva_mcp_core import get_catalog, deriva_call` — `get_catalog(hostname, catalog_id)` returns an `ErmrestCatalog`; `catalog.get(path).json()` runs an ERMrest GET. Wrap in `with deriva_call():`.
- `ctx.on_catalog_connect(async_fn)`; hook signature `async (hostname, catalog_id, schema_hash, schema_json) -> None`.
- `ctx.submit_task(coroutine, name=..., description=...) -> str`. Background coroutine re-fetches credential from `get_task_manager().get_credential(task_id)`.
- `from deriva_mcp_core.plugin.api import fire_catalog_connect` for tests.
- `ctx.env: dict[str, str]` — merged env-file + os.environ. Read config overrides from here.
- `from deriva_mcp_core.context import set_current_credential` (tests set a fake credential).

---

## Task 1: Project scaffold (pyproject, package marker, meta files)

**Files:**
- Create: `pyproject.toml`, `src/eye_ai_deriva_mcp_plugin/__init__.py`, `.gitignore`, `LICENSE`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "eye-ai-deriva-mcp-plugin"
dynamic = ["version"]
description = "Eye-AI domain RAG indexing plugin for deriva-mcp-core"
readme = "README.md"
license = { text = "Apache-2.0" }
requires-python = ">=3.12"
authors = [{ name = "Informatics and Scientific Research Division, USC" }]
keywords = ["mcp", "deriva", "eye-ai", "rag"]
classifiers = [
    "Development Status :: 2 - Pre-Alpha",
    "Intended Audience :: Science/Research",
    "License :: OSI Approved :: Apache Software License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
]

dependencies = [
    "deriva-mcp-core",
    "deriva-ml>=1.38.0",
    # Pin deriva-py to the deriva-ml branch in the built wheel metadata --
    # not just in [tool.uv] (which is local-only and does not ship).
    "deriva @ git+https://github.com/informatics-isi-edu/deriva-py@deriva-ml",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "bump-my-version",
]
# Opt-in OS trust store for TLS behind a corporate MITM proxy.
system-certs = ["pip-system-certs>=5.3"]

[project.entry-points."deriva_mcp.plugins"]
# Entry-point name == package name so the deriva-docker
# DERIVA_MCP_PLUGIN_ALLOWLIST value works without name-vs-package confusion.
eye-ai-deriva-mcp-plugin = "eye_ai_deriva_mcp_plugin.plugin:register"

[tool.hatch.metadata]
# Required so the `deriva @ git+...` direct URL is allowed in wheel METADATA.
allow-direct-references = true

[tool.hatch.version]
source = "vcs"

[tool.hatch.build.hooks.vcs]
version-file = "src/eye_ai_deriva_mcp_plugin/_version.py"

[tool.hatch.build.targets.wheel]
packages = ["src/eye_ai_deriva_mcp_plugin"]

[tool.uv]
# Force the deriva-ml branch locally, overriding deriva-mcp-core's @master pin.
override-dependencies = [
    "deriva @ git+https://github.com/informatics-isi-edu/deriva-py@deriva-ml",
]

[tool.uv.sources]
deriva-mcp-core = { path = "../deriva-mcp-core", editable = true }
deriva-ml = { path = "../deriva-ml", editable = true }

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["src/eye_ai_deriva_mcp_plugin/_version.py"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "W"]
ignore = ["E402", "E501"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
addopts = "-vv -r w --tb=short --disable-warnings"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/eye_ai_deriva_mcp_plugin"]
omit = ["tests/*"]

[tool.bumpversion]
allow_dirty = false
commit = true
tag = true
current_version = "0.1.0"
```

- [ ] **Step 2: Write `src/eye_ai_deriva_mcp_plugin/__init__.py`**

```python
"""Eye-AI domain RAG indexing plugin for deriva-mcp-core."""
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
.coverage
dist/
build/
*.egg-info/
src/*/_version.py
```

- [ ] **Step 4: Write `LICENSE`**

Use the standard Apache License 2.0 text (copy from `../deriva-ml-mcp/LICENSE`).

Run: `cp ../deriva-ml-mcp/LICENSE LICENSE` (from the repo root).

- [ ] **Step 5: Sync the environment**

Run: `uv sync --extra dev`
Expected: resolves and installs `deriva-mcp-core`, `deriva-ml`, `deriva` (deriva-ml branch), pytest, ruff. No errors.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/eye_ai_deriva_mcp_plugin/__init__.py .gitignore LICENSE uv.lock
git commit -m "chore: project scaffold (pyproject, package, license, gitignore)"
```

---

## Task 2: Config module

**Files:**
- Create: `src/eye_ai_deriva_mcp_plugin/config.py`
- Test: `tests/test_config.py`, `tests/conftest.py`

- [ ] **Step 1: Write `tests/conftest.py`** (shared fixtures; from the authoring guide)

```python
"""Shared test fixtures: a minimal FastMCP stand-in and a PluginContext."""

from __future__ import annotations

from typing import Any

import pytest
from deriva_mcp_core.plugin.api import PluginContext, _set_plugin_context


class _CapturingMCP:
    """Minimal FastMCP stand-in that stores registered tools by name."""

    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self, **kwargs: Any):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator

    def resource(self, *a: Any, **kw: Any):
        return lambda fn: fn

    def prompt(self, *a: Any, **kw: Any):
        return lambda fn: fn


@pytest.fixture()
def mcp():
    return _CapturingMCP()


@pytest.fixture()
def ctx(mcp):
    _ctx = PluginContext(mcp)
    _set_plugin_context(_ctx)
    yield _ctx
    _set_plugin_context(None)
```

- [ ] **Step 2: Write the failing test `tests/test_config.py`**

```python
"""Tests for the config module (defaults + env overrides)."""

from __future__ import annotations

from eye_ai_deriva_mcp_plugin import config


def test_default_hosts():
    assert config.eye_ai_hosts({}) == {"www.eye-ai.org", "dev.eye-ai.org"}


def test_hosts_env_override():
    env = {"EYE_AI_DERIVA_MCP_HOSTS": "a.eye-ai.org, b.eye-ai.org"}
    assert config.eye_ai_hosts(env) == {"a.eye-ai.org", "b.eye-ai.org"}


def test_default_tables():
    # Placeholder set; corrected later by the user.
    assert config.eye_ai_tables({}) == [
        ("EyeAI", "Subject"),
        ("EyeAI", "Image"),
        ("EyeAI", "Observation"),
        ("EyeAI", "Diagnosis"),
        ("EyeAI", "Condition_Label"),
    ]


def test_tables_env_override():
    env = {"EYE_AI_DERIVA_MCP_TABLES": "EyeAI:Subject, EyeAI:Image"}
    assert config.eye_ai_tables(env) == [("EyeAI", "Subject"), ("EyeAI", "Image")]


def test_default_ttl():
    assert config.index_ttl_seconds({}) == 86400


def test_ttl_env_override():
    assert config.index_ttl_seconds({"EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS": "3600"}) == 3600
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError: module 'config' has no attribute 'eye_ai_hosts'`.

- [ ] **Step 4: Write `src/eye_ai_deriva_mcp_plugin/config.py`**

```python
"""Configuration for the eye-ai RAG indexer.

All values have a hard-coded default and an env override read from the
merged environment map (``ctx.env``). The plugin reads config through
these functions rather than module-level constants so an operator can
override the eye-ai host set, the indexed table list, and the re-index
TTL without code changes.
"""

from __future__ import annotations

_DEFAULT_HOSTS = ("www.eye-ai.org", "dev.eye-ai.org")

# Placeholder table list -- the real curated set is supplied by the
# project owner later and swapped in here (or via the env override).
# Each entry is a (schema, table) pair in ERMrest case.
_DEFAULT_TABLES = (
    ("EyeAI", "Subject"),
    ("EyeAI", "Image"),
    ("EyeAI", "Observation"),
    ("EyeAI", "Diagnosis"),
    ("EyeAI", "Condition_Label"),
)

_DEFAULT_TTL_SECONDS = 86400  # 24h


def eye_ai_hosts(env: dict[str, str]) -> set[str]:
    """Return the set of hostnames that trigger eye-ai indexing.

    Env override ``EYE_AI_DERIVA_MCP_HOSTS`` is a comma-separated list.

    Args:
        env: The merged environment map (``ctx.env``).

    Returns:
        Set of hostnames. The on-connect hook no-ops on any host not
        in this set.

    Example:
        >>> eye_ai_hosts({})
        {'www.eye-ai.org', 'dev.eye-ai.org'}
    """
    raw = env.get("EYE_AI_DERIVA_MCP_HOSTS")
    if not raw:
        return set(_DEFAULT_HOSTS)
    return {h.strip() for h in raw.split(",") if h.strip()}


def eye_ai_tables(env: dict[str, str]) -> list[tuple[str, str]]:
    """Return the ordered list of (schema, table) pairs to index.

    Env override ``EYE_AI_DERIVA_MCP_TABLES`` is a comma-separated list
    of ``schema:table`` tokens.

    Args:
        env: The merged environment map (``ctx.env``).

    Returns:
        Ordered list of ``(schema, table)`` tuples.

    Example:
        >>> eye_ai_tables({"EYE_AI_DERIVA_MCP_TABLES": "EyeAI:Subject"})
        [('EyeAI', 'Subject')]
    """
    raw = env.get("EYE_AI_DERIVA_MCP_TABLES")
    if not raw:
        return list(_DEFAULT_TABLES)
    out: list[tuple[str, str]] = []
    for token in raw.split(","):
        token = token.strip()
        if not token or ":" not in token:
            continue
        schema, table = token.split(":", 1)
        out.append((schema.strip(), table.strip()))
    return out


def index_ttl_seconds(env: dict[str, str]) -> int:
    """Return the re-index TTL in seconds.

    Env override ``EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS``. The on-connect
    hook skips the background index if the catalog was indexed within
    this window; the manual reindex tool bypasses it.

    Args:
        env: The merged environment map (``ctx.env``).

    Returns:
        TTL in seconds (default 86400).

    Example:
        >>> index_ttl_seconds({})
        86400
    """
    raw = env.get("EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS")
    if not raw:
        return _DEFAULT_TTL_SECONDS
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_TTL_SECONDS
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS — 6 tests.

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_config.py src/eye_ai_deriva_mcp_plugin/config.py
git commit -m "feat(config): host set, table list, TTL with env overrides"
```

---

## Task 3: Row serializer

**Files:**
- Create: `src/eye_ai_deriva_mcp_plugin/serializers.py`
- Test: `tests/test_serializers.py`

- [ ] **Step 1: Write the failing test `tests/test_serializers.py`**

```python
"""Tests for the eye-ai row serializer."""

from __future__ import annotations

from eye_ai_deriva_mcp_plugin.serializers import EyeAIRowSerializer


def test_serialize_renders_header_and_fields():
    s = EyeAIRowSerializer()
    md = s.serialize("Subject", {"RID": "1-AAAA", "Name": "S1", "Notes": "healthy"})
    assert md is not None
    assert "## Subject: 1-AAAA" in md
    assert "**Name:** S1" in md
    assert "**Notes:** healthy" in md


def test_serialize_omits_empty_and_system_fields():
    s = EyeAIRowSerializer()
    md = s.serialize(
        "Image",
        {"RID": "2-BBBB", "URL": "/hatrac/x", "Empty": "", "Null": None, "RCT": "2020"},
    )
    assert "**URL:** /hatrac/x" in md
    assert "Empty" not in md  # empty string omitted
    assert "Null" not in md  # None omitted
    assert "RCT" not in md  # system column omitted


def test_serialize_returns_none_for_rid_less_row():
    s = EyeAIRowSerializer()
    assert s.serialize("Subject", {"Name": "no rid"}) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_serializers.py -v`
Expected: FAIL — `ModuleNotFoundError: eye_ai_deriva_mcp_plugin.serializers`.

- [ ] **Step 3: Write `src/eye_ai_deriva_mcp_plugin/serializers.py`**

```python
"""Markdown serialization of eye-ai catalog rows for RAG indexing.

One generic serializer renders any eye-ai table row into a Markdown
section: a header line carrying the table name + RID, then each
non-empty, non-system field as a ``**Field:** value`` line. The result
is what gets chunked and embedded; richer per-table serializers can be
added later by dispatching on ``table_name``.
"""

from __future__ import annotations

from typing import Any

from deriva_mcp_core.rag.data import RowSerializer

# ERMrest system columns -- never useful in a search chunk.
_SYSTEM_COLUMNS = frozenset({"RID", "RCT", "RMT", "RCB", "RMB"})


class EyeAIRowSerializer(RowSerializer):
    """Render one eye-ai row to a Markdown section.

    Returns ``None`` for a row with no ``RID`` (cannot anchor a chunk).
    """

    def serialize(self, table_name: str, row: dict[str, Any]) -> str | None:
        """Render ``row`` from ``table_name`` to Markdown, or None.

        Args:
            table_name: ERMrest-cased table name (e.g. ``"Subject"``).
            row: A single entity row dict from an ERMrest fetch.

        Returns:
            A Markdown string, or ``None`` when the row has no RID.

        Example:
            >>> EyeAIRowSerializer().serialize("Subject", {"RID": "1-A", "Name": "x"})
            '## Subject: 1-A\\n\\n**Name:** x'
        """
        rid = row.get("RID")
        if not rid:
            return None
        lines = [f"## {table_name}: {rid}", ""]
        for key, value in row.items():
            if key in _SYSTEM_COLUMNS:
                continue
            if value is None or value == "":
                continue
            lines.append(f"**{key}:** {value}")
        return "\n".join(lines)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_serializers.py -v`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_serializers.py src/eye_ai_deriva_mcp_plugin/serializers.py
git commit -m "feat(serializers): generic eye-ai row -> Markdown"
```

---

## Task 4: Indexing core — source name + fetch + write

**Files:**
- Create: `src/eye_ai_deriva_mcp_plugin/indexing.py`
- Test: `tests/test_indexing.py`

- [ ] **Step 1: Write the failing test (source name + fetch + write_table)**

```python
"""Tests for the indexing core."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from eye_ai_deriva_mcp_plugin import indexing


def test_source_name_shape():
    assert (
        indexing._source_name("www.eye-ai.org", "5", "EyeAI", "Subject")
        == "eye-ai:www.eye-ai.org:5:EyeAI.Subject"
    )


def test_fetch_table_rows_builds_ermrest_path():
    catalog = MagicMock()
    resp = MagicMock()
    resp.json.return_value = [{"RID": "1-AAAA"}]
    catalog.get.return_value = resp
    with patch("eye_ai_deriva_mcp_plugin.indexing.get_catalog", return_value=catalog):
        rows = indexing._fetch_table_rows("www.eye-ai.org", "5", "EyeAI", "Subject")
    catalog.get.assert_called_once_with("/entity/EyeAI:Subject")
    assert rows == [{"RID": "1-AAAA"}]


async def test_write_table_replaces_then_adds():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    rows = [{"RID": "1-AAAA", "Name": "S1"}, {"RID": "2-BBBB", "Name": "S2"}]
    written = await indexing._write_table(store, "src1", "Subject", rows)
    store.delete_source.assert_awaited_once_with("src1")
    store.add.assert_awaited_once()
    # Both rows produced at least one chunk each.
    assert written >= 2
    added_chunks = store.add.await_args.args[0]
    assert all(c.source == "src1" for c in added_chunks)


async def test_write_table_empty_rows_skips_add():
    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    written = await indexing._write_table(store, "src1", "Subject", [])
    store.delete_source.assert_awaited_once_with("src1")
    store.add.assert_not_awaited()
    assert written == 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_indexing.py -v`
Expected: FAIL — `ModuleNotFoundError: eye_ai_deriva_mcp_plugin.indexing`.

- [ ] **Step 3: Write the first half of `src/eye_ai_deriva_mcp_plugin/indexing.py`**

```python
"""On-connect eye-ai catalog indexing.

When a tool connects to an eye-ai catalog, an ``on_catalog_connect``
hook submits a background task that fetches each configured
``EyeAI:<table>``, serializes its rows to Markdown, and writes them to
the RAG vector store under a catalog-public source name
``eye-ai:{host}:{cat}:{schema}.{table}``.

The ``eye-ai:`` source prefix is deliberately NOT one of the prefixes
the upstream ``rag_search`` user-id filter gates on (``data:``,
``schema:``, ``enriched:``), so the chunks are served to all authorized
users. This is correct because the eye-ai catalog has auth-gating but
no row-level ACLs -- every authorized user sees everything.

The full index runs as a background task (``ctx.submit_task``) so the
triggering connect call returns immediately. It is exempt from the
bounded-per-call rule because it is not a tool response -- it streams
into the shared vector store, the same posture as core's startup doc
crawl.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable

from deriva_mcp_core import deriva_call, get_catalog
from deriva_mcp_core.rag import get_rag_store
from deriva_mcp_core.rag.chunker import chunk_markdown
from deriva_mcp_core.rag.store import Chunk

from eye_ai_deriva_mcp_plugin import config
from eye_ai_deriva_mcp_plugin.serializers import EyeAIRowSerializer

if TYPE_CHECKING:
    from deriva_mcp_core.plugin.api import PluginContext
    from deriva_mcp_core.rag.store import VectorStore

logger = logging.getLogger(__name__)

_SERIALIZER = EyeAIRowSerializer()
_DOC_TYPE = "eye-ai-data"


def _source_name(hostname: str, catalog_id: str, schema: str, table: str) -> str:
    """Build the catalog-public source name for one eye-ai table.

    Shape: ``eye-ai:{host}:{cat}:{schema}.{table}``. The ``eye-ai:``
    prefix bypasses the upstream per-user ``data:`` filter so all users
    see the chunks.

    Example:
        >>> _source_name("www.eye-ai.org", "5", "EyeAI", "Subject")
        'eye-ai:www.eye-ai.org:5:EyeAI.Subject'
    """
    return f"eye-ai:{hostname}:{catalog_id}:{schema}.{table}"


def _fetch_table_rows(
    hostname: str, catalog_id: str, schema: str, table: str
) -> list[dict[str, Any]]:
    """Fetch all rows of one eye-ai table via generic ERMrest.

    Synchronous deriva-py I/O -- the async caller wraps this in
    ``asyncio.to_thread``. Uses ``get_catalog`` (the per-request
    credential path), so it must run inside a request or a background
    task that has set the credential contextvar.

    Args:
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        schema: ERMrest schema name (e.g. ``"EyeAI"``).
        table: ERMrest table name (e.g. ``"Subject"``).

    Returns:
        A list of row dicts.
    """
    with deriva_call():
        catalog = get_catalog(hostname, catalog_id)
        return catalog.get(f"/entity/{schema}:{table}").json()


async def _write_table(
    store: VectorStore,
    source: str,
    table: str,
    rows: list[dict[str, Any]],
) -> int:
    """Replace ``source`` with the chunks rendered from ``rows``.

    ``delete_source`` first (idempotent -- drains any prior pass), then
    serialize each row, chunk it, and ``store.add`` the lot in one call.

    Args:
        store: An active vector store.
        source: The canonical source name for this table.
        table: ERMrest table name (passed to the serializer).
        rows: Row dicts for the table.

    Returns:
        Count of chunks written.
    """
    await store.delete_source(source)
    chunks: list[Chunk] = []
    chunk_index = 0
    for row in rows:
        try:
            rendered = _SERIALIZER.serialize(table, row)
        except Exception:  # noqa: BLE001 -- one bad row must not poison the table
            logger.exception("eye-ai RAG: serialize failed for %s row %r", table, row.get("RID"))
            continue
        if rendered is None:
            continue
        for c in chunk_markdown(rendered, source=source, doc_type=_DOC_TYPE):
            chunks.append(
                Chunk(
                    text=c.text,
                    source=source,
                    doc_type=_DOC_TYPE,
                    section_heading=c.section_heading,
                    heading_hierarchy=c.heading_hierarchy,
                    chunk_index=chunk_index,
                )
            )
            chunk_index += 1
    if chunks:
        await store.add(chunks)
    return len(chunks)
```

- [ ] **Step 4: Run to verify the four tests pass**

Run: `uv run pytest tests/test_indexing.py -v`
Expected: PASS — 4 tests (`_source_name`, `_fetch_table_rows`, `_write_table` x2).

- [ ] **Step 5: Commit**

```bash
git add tests/test_indexing.py src/eye_ai_deriva_mcp_plugin/indexing.py
git commit -m "feat(indexing): source name, ERMrest fetch, per-table write"
```

---

## Task 5: Indexing core — freshness + full-catalog index

**Files:**
- Modify: `src/eye_ai_deriva_mcp_plugin/indexing.py` (append functions)
- Test: `tests/test_indexing.py` (append tests)

- [ ] **Step 1: Append failing tests to `tests/test_indexing.py`**

```python
async def test_is_index_fresh_true_within_ttl():
    from eye_ai_deriva_mcp_plugin import indexing as idx
    from deriva_mcp_core.rag.store import SourceStats

    now_iso = datetime.now(timezone.utc).isoformat()
    store = MagicMock()
    store.source_stats = AsyncMock(
        return_value={"eye-ai:www.eye-ai.org:5:EyeAI.Subject": SourceStats(3, now_iso)}
    )
    fresh = await idx._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is True


async def test_is_index_fresh_false_when_stale():
    from eye_ai_deriva_mcp_plugin import indexing as idx
    from deriva_mcp_core.rag.store import SourceStats

    old_iso = "2000-01-01T00:00:00+00:00"
    store = MagicMock()
    store.source_stats = AsyncMock(
        return_value={"eye-ai:www.eye-ai.org:5:EyeAI.Subject": SourceStats(3, old_iso)}
    )
    fresh = await idx._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is False


async def test_is_index_fresh_false_when_no_sources():
    from eye_ai_deriva_mcp_plugin import indexing as idx

    store = MagicMock()
    store.source_stats = AsyncMock(return_value={})
    fresh = await idx._is_index_fresh(store, "www.eye-ai.org", "5", ttl_seconds=86400)
    assert fresh is False


# needed for the datetime import in the appended tests
from datetime import datetime, timezone  # noqa: E402


async def test_index_catalog_indexes_each_configured_table():
    from eye_ai_deriva_mcp_plugin import indexing as idx

    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch(
            "eye_ai_deriva_mcp_plugin.indexing._fetch_table_rows",
            return_value=[{"RID": "1-AAAA", "Name": "S1"}],
        ),
    ):
        result = await idx._index_catalog(
            "www.eye-ai.org", "5", [("EyeAI", "Subject"), ("EyeAI", "Image")], {}
        )
    assert result["tables_indexed"] == 2
    assert result["rows_indexed"] == 2
    # delete_source + add called once per table.
    assert store.delete_source.await_count == 2
    assert store.add.await_count == 2


async def test_index_catalog_isolates_table_fetch_failure():
    from eye_ai_deriva_mcp_plugin import indexing as idx

    store = MagicMock()
    store.delete_source = AsyncMock()
    store.add = AsyncMock()

    def _fetch(host, cat, schema, table):
        if table == "Image":
            raise RuntimeError("ermrest 500")
        return [{"RID": "1-AAAA"}]

    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._fetch_table_rows", side_effect=_fetch),
    ):
        result = await idx._index_catalog(
            "www.eye-ai.org", "5", [("EyeAI", "Subject"), ("EyeAI", "Image")], {}
        )
    # Subject indexed; Image failed but did not abort the pass.
    assert result["tables_indexed"] == 1
    assert result["tables_failed"] == 1
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/test_indexing.py -v -k "fresh or index_catalog"`
Expected: FAIL — `_is_index_fresh` / `_index_catalog` not defined.

- [ ] **Step 3: Append to `src/eye_ai_deriva_mcp_plugin/indexing.py`**

```python
def _parse_iso(ts: str) -> datetime | None:
    """Parse an ISO-8601 timestamp; return None on any failure."""
    try:
        dt = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


async def _is_index_fresh(
    store: VectorStore, hostname: str, catalog_id: str, ttl_seconds: int
) -> bool:
    """Return True if this catalog's eye-ai index is within the TTL.

    Reads the most recent ``indexed_at`` across the catalog's
    ``eye-ai:{host}:{cat}:`` sources from ``store.source_stats()``. If
    none exist (never indexed) or the freshest is older than the TTL,
    returns False.

    Args:
        store: An active vector store.
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        ttl_seconds: Freshness window.

    Returns:
        True if a re-index can be skipped; False otherwise.
    """
    if ttl_seconds <= 0:
        return False
    prefix = f"eye-ai:{hostname}:{catalog_id}:"
    stats = await store.source_stats()
    newest: datetime | None = None
    for source, stat in stats.items():
        if not source.startswith(prefix) or stat.indexed_at is None:
            continue
        dt = _parse_iso(stat.indexed_at)
        if dt is not None and (newest is None or dt > newest):
            newest = dt
    if newest is None:
        return False
    age = (datetime.now(timezone.utc) - newest).total_seconds()
    return age < ttl_seconds


async def _index_catalog(
    hostname: str,
    catalog_id: str,
    tables: list[tuple[str, str]],
    env: dict[str, str],  # noqa: ARG001 -- reserved for future per-call config
) -> dict[str, int]:
    """Fetch + index every configured eye-ai table for one catalog.

    Per-table fetch failures are isolated: a failing table is logged and
    counted in ``tables_failed`` but does not abort the rest of the
    pass. Runs the synchronous ERMrest fetch in a worker thread.

    Args:
        hostname: Deriva server hostname.
        catalog_id: Catalog ID as a string.
        tables: Ordered ``(schema, table)`` pairs to index.
        env: Reserved (merged env map) for future per-call knobs.

    Returns:
        ``{"tables_indexed", "tables_failed", "rows_indexed"}``.
    """
    store = get_rag_store()
    if store is None:
        logger.debug("eye-ai RAG: store unavailable, skipping index of %s/%s", hostname, catalog_id)
        return {"tables_indexed": 0, "tables_failed": 0, "rows_indexed": 0}

    tables_indexed = 0
    tables_failed = 0
    rows_indexed = 0
    for schema, table in tables:
        source = _source_name(hostname, catalog_id, schema, table)
        try:
            rows = await asyncio.to_thread(
                _fetch_table_rows, hostname, catalog_id, schema, table
            )
        except Exception:  # noqa: BLE001 -- one bad table must not abort the pass
            logger.exception("eye-ai RAG: fetch failed for %s:%s on %s/%s", schema, table, hostname, catalog_id)
            tables_failed += 1
            continue
        await _write_table(store, source, table, rows)
        tables_indexed += 1
        rows_indexed += len(rows)
    logger.info(
        "eye-ai RAG: indexed %s/%s -- %d tables, %d failed, %d rows",
        hostname, catalog_id, tables_indexed, tables_failed, rows_indexed,
    )
    return {
        "tables_indexed": tables_indexed,
        "tables_failed": tables_failed,
        "rows_indexed": rows_indexed,
    }
```

- [ ] **Step 4: Run all indexing tests**

Run: `uv run pytest tests/test_indexing.py -v`
Expected: PASS — the prior 4 plus the 5 new (freshness x3, index_catalog x2).

- [ ] **Step 5: Commit**

```bash
git add tests/test_indexing.py src/eye_ai_deriva_mcp_plugin/indexing.py
git commit -m "feat(indexing): TTL freshness check + full-catalog index pass"
```

---

## Task 6: The on_catalog_connect hook factory

**Files:**
- Modify: `src/eye_ai_deriva_mcp_plugin/indexing.py` (append `make_catalog_connect_hook`)
- Test: `tests/test_indexing.py` (append hook tests)

- [ ] **Step 1: Append failing hook tests**

```python
async def test_hook_no_ops_on_non_eye_ai_host(ctx):
    from eye_ai_deriva_mcp_plugin import indexing as idx

    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    hook = idx.make_catalog_connect_hook(ctx)
    await hook("other.deriva.org", "1", "hash", {})
    assert submitted == []  # not an eye-ai host -> no task


async def test_hook_no_ops_when_rag_disabled(ctx):
    from eye_ai_deriva_mcp_plugin import indexing as idx

    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    with patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=None):
        hook = idx.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert submitted == []  # RAG off -> no task


async def test_hook_skips_when_fresh(ctx):
    from eye_ai_deriva_mcp_plugin import indexing as idx

    submitted = []
    ctx.submit_task = lambda coro, name="", description="": submitted.append(name) or "task-1"
    store = MagicMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._is_index_fresh", AsyncMock(return_value=True)),
    ):
        hook = idx.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert submitted == []  # fresh -> no task


async def test_hook_submits_task_when_stale(ctx):
    from eye_ai_deriva_mcp_plugin import indexing as idx

    submitted = []

    def _submit(coro, name="", description=""):
        coro.close()  # avoid "coroutine never awaited" warning
        submitted.append(name)
        return "task-1"

    ctx.submit_task = _submit
    store = MagicMock()
    with (
        patch("eye_ai_deriva_mcp_plugin.indexing.get_rag_store", return_value=store),
        patch("eye_ai_deriva_mcp_plugin.indexing._is_index_fresh", AsyncMock(return_value=False)),
    ):
        hook = idx.make_catalog_connect_hook(ctx)
        await hook("www.eye-ai.org", "5", "hash", {})
    assert len(submitted) == 1
    assert "www.eye-ai.org/5" in submitted[0]
```

- [ ] **Step 2: Run to verify the hook tests fail**

Run: `uv run pytest tests/test_indexing.py -v -k hook`
Expected: FAIL — `make_catalog_connect_hook` not defined.

- [ ] **Step 3: Append to `src/eye_ai_deriva_mcp_plugin/indexing.py`**

```python
async def _index_catalog_task(
    task_id_ref: list[str],
    hostname: str,
    catalog_id: str,
    tables: list[tuple[str, str]],
    env: dict[str, str],
) -> dict[str, int]:
    """Background-task wrapper: re-resolve the credential, then index.

    Background tasks do not carry the per-request credential contextvar,
    so the credential is re-fetched from the TaskManager before any
    DERIVA I/O (the authoring guide's long-task pattern). The credential
    is set on the contextvar so ``get_catalog`` inside ``_fetch_table_rows``
    resolves it.
    """
    from deriva_mcp_core.context import set_current_credential
    from deriva_mcp_core.tasks import get_task_manager

    task_id = task_id_ref[0]
    cred = await get_task_manager().get_credential(task_id)
    set_current_credential(cred)
    return await _index_catalog(hostname, catalog_id, tables, env)


def make_catalog_connect_hook(
    ctx: PluginContext,
) -> Callable[[str, str, str, dict], Any]:
    """Build the ``on_catalog_connect`` hook bound to ``ctx``.

    The hook host-gates, RAG-gates, and TTL-gates, then submits a
    background ``_index_catalog_task`` for stale eye-ai catalogs.

    Args:
        ctx: The plugin context (for ``ctx.env`` and ``ctx.submit_task``).

    Returns:
        An async hook with the ``on_catalog_connect`` signature.
    """
    hosts = config.eye_ai_hosts(ctx.env)
    tables = config.eye_ai_tables(ctx.env)
    ttl = config.index_ttl_seconds(ctx.env)

    async def hook(
        hostname: str,
        catalog_id: str,
        schema_hash: str,  # noqa: ARG001 -- hook signature requires it
        schema_json: dict,  # noqa: ARG001 -- hook signature requires it
    ) -> None:
        if hostname not in hosts:
            return
        store = get_rag_store()
        if store is None:
            return
        try:
            if await _is_index_fresh(store, hostname, catalog_id, ttl):
                logger.debug("eye-ai RAG: index fresh for %s/%s, skipping", hostname, catalog_id)
                return
        except Exception:  # noqa: BLE001 -- a freshness probe failure should not block indexing
            logger.exception("eye-ai RAG: freshness check failed for %s/%s", hostname, catalog_id)

        task_id_ref: list[str] = [""]
        task_id = ctx.submit_task(
            _index_catalog_task(task_id_ref, hostname, catalog_id, tables, ctx.env),
            name=f"eye-ai index {hostname}/{catalog_id}",
            description=f"Index eye-ai tables for catalog {catalog_id}",
        )
        task_id_ref[0] = task_id

    return hook
```

- [ ] **Step 4: Run all indexing tests**

Run: `uv run pytest tests/test_indexing.py -v`
Expected: PASS — all (fetch/write/fresh/index_catalog/hook).

- [ ] **Step 5: Commit**

```bash
git add tests/test_indexing.py src/eye_ai_deriva_mcp_plugin/indexing.py
git commit -m "feat(indexing): on_catalog_connect hook with host/RAG/TTL gating"
```

---

## Task 7: Maintenance tool

**Files:**
- Create: `src/eye_ai_deriva_mcp_plugin/maintenance.py`
- Test: `tests/test_maintenance.py`

- [ ] **Step 1: Write the failing test `tests/test_maintenance.py`**

```python
"""Tests for the manual reindex tool."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from eye_ai_deriva_mcp_plugin.maintenance import register_maintenance_tools


async def test_reindex_tool_registered(ctx):
    register_maintenance_tools(ctx)
    assert "deriva_eye_ai_reindex_catalog" in ctx._mcp.tools


async def test_reindex_rejects_non_eye_ai_host(ctx):
    register_maintenance_tools(ctx)
    out = json.loads(
        await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("other.org", "1")
    )
    assert "error" in out
    assert "eye-ai" in out["error"]


async def test_reindex_runs_and_returns_counts(ctx):
    register_maintenance_tools(ctx)
    with patch(
        "eye_ai_deriva_mcp_plugin.maintenance._index_catalog",
        AsyncMock(return_value={"tables_indexed": 2, "tables_failed": 0, "rows_indexed": 7}),
    ):
        out = json.loads(
            await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("www.eye-ai.org", "5")
        )
    assert out["status"] == "reindexed"
    assert out["host"] == "www.eye-ai.org"
    assert out["catalog_id"] == "5"
    assert out["tables_indexed"] == 2
    assert out["rows_indexed"] == 7


async def test_reindex_error_envelope_on_failure(ctx):
    register_maintenance_tools(ctx)
    with patch(
        "eye_ai_deriva_mcp_plugin.maintenance._index_catalog",
        AsyncMock(side_effect=RuntimeError("store down")),
    ):
        out = json.loads(
            await ctx._mcp.tools["deriva_eye_ai_reindex_catalog"]("www.eye-ai.org", "5")
        )
    assert out == {"error": "store down"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_maintenance.py -v`
Expected: FAIL — `ModuleNotFoundError: eye_ai_deriva_mcp_plugin.maintenance`.

- [ ] **Step 3: Write `src/eye_ai_deriva_mcp_plugin/maintenance.py`**

```python
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
            return json.dumps(
                {"error": f"{hostname} is not a configured eye-ai host"}
            )
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_maintenance.py -v`
Expected: PASS — 4 tests.

- [ ] **Step 5: Commit**

```bash
git add tests/test_maintenance.py src/eye_ai_deriva_mcp_plugin/maintenance.py
git commit -m "feat(maintenance): deriva_eye_ai_reindex_catalog tool"
```

---

## Task 8: The register entry point

**Files:**
- Create: `src/eye_ai_deriva_mcp_plugin/plugin.py`
- Test: `tests/test_plugin.py`

- [ ] **Step 1: Write the failing test `tests/test_plugin.py`**

```python
"""Smoke tests for the plugin entry point."""

from __future__ import annotations

from importlib import metadata

from eye_ai_deriva_mcp_plugin.plugin import register


def test_register_runs_without_error(ctx):
    register(ctx)
    # The maintenance tool landed.
    assert "deriva_eye_ai_reindex_catalog" in ctx._mcp.tools
    # One catalog-connect hook registered.
    assert len(ctx._catalog_connect_hooks) == 1


def test_entry_point_resolves_to_register():
    eps = metadata.entry_points(group="deriva_mcp.plugins")
    matching = [ep for ep in eps if ep.name == "eye-ai-deriva-mcp-plugin"]
    assert matching, "entry point 'eye-ai-deriva-mcp-plugin' not declared"
    assert matching[0].load() is register
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: FAIL — `ModuleNotFoundError: eye_ai_deriva_mcp_plugin.plugin`.

- [ ] **Step 3: Write `src/eye_ai_deriva_mcp_plugin/plugin.py`**

```python
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: PASS — 2 tests. (The entry-point test requires the package installed; `uv sync` from Task 1 did an editable install, so `metadata.entry_points` sees it.)

- [ ] **Step 5: Run the full suite + lint**

Run: `uv run pytest -v && uv run ruff check src tests`
Expected: All tests PASS; ruff "All checks passed!".

- [ ] **Step 6: Commit**

```bash
git add tests/test_plugin.py src/eye_ai_deriva_mcp_plugin/plugin.py
git commit -m "feat(plugin): register entry point wiring hook + maintenance tool"
```

---

## Task 9: README, CLAUDE.md, rebuild script

**Files:**
- Create: `README.md`, `CLAUDE.md`, `scripts/rebuild-deriva-docker-mcp.sh`

- [ ] **Step 1: Write `README.md`**

````markdown
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
  correct.
- **TTL-gated.** Re-indexing on reconnect is skipped within a
  configurable window (default 24h).
- **Manual reindex.** `deriva_eye_ai_reindex_catalog(hostname,
  catalog_id)` forces a full re-index (bypasses the TTL).

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `EYE_AI_DERIVA_MCP_HOSTS` | `www.eye-ai.org,dev.eye-ai.org` | Hosts that trigger indexing |
| `EYE_AI_DERIVA_MCP_TABLES` | placeholder `EyeAI:Subject,...` | `schema:table` list to index |
| `EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS` | `86400` | Re-index TTL |
| `DERIVA_MCP_RAG_ENABLED` | `false` | Must be `true` for any indexing |

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
````

- [ ] **Step 2: Write `CLAUDE.md`** (mirror deriva-ml-mcp conventions, scaled to this plugin)

```markdown
# CLAUDE.md

Guidance for Claude Code when working with `eye-ai-deriva-mcp-plugin`.

## Project Overview

A `deriva-mcp-core` plugin that RAG-indexes eye-ai catalog domain
tables on connect. No domain query tools (v0.1) — generic catalog tools
come from core, DerivaML tools from the co-located `deriva-ml-mcp`
plugin. The deployable MCP server is `deriva-mcp-core` + this plugin +
`deriva-ml-mcp`.

## Architecture

```
src/eye_ai_deriva_mcp_plugin/
├── plugin.py        # register(ctx): wires the hook + maintenance tool
├── config.py        # host set / table list / TTL (env-overridable)
├── serializers.py   # EyeAIRowSerializer: row -> Markdown
├── indexing.py      # on_catalog_connect hook + background index task
└── maintenance.py   # deriva_eye_ai_reindex_catalog tool
```

## Key design decisions

- **Catalog-public index.** Eye-ai has auth-gating but no row-level
  ACLs, so a single shared index (`eye-ai:` source prefix) is correct.
  The `eye-ai:` prefix bypasses upstream's per-user `data:` filter
  (same trick as deriva-ml-mcp's `vocab:` prefix), serving chunks to
  all authorized users.
- **Background indexing.** The hook submits a `ctx.submit_task` so the
  connect call returns immediately. The background coroutine re-fetches
  the credential from the TaskManager (background tasks lack the
  request contextvar credential).
- **TTL-gated.** `_is_index_fresh` reads `store.source_stats()`
  `indexed_at` timestamps for the catalog's `eye-ai:` sources.

## Conventions (shared workspace rules)

- **`uv` for everything** — `uv run pytest`, `uv run ruff ...`,
  `uv run bump-version`. Never call the tools directly.
- **Google-style docstrings** with `Args:`/`Returns:`/`Raises:`/
  `Example:`.
- **No backwards-compat shims; no over-engineering.**
- **Entry-point name == package name** (`eye-ai-deriva-mcp-plugin`) so
  the deriva-docker `DERIVA_MCP_PLUGIN_ALLOWLIST` value works without
  the name-vs-package confusion that bit deriva-ml-mcp early on.

## Tool / hook rules (from the deriva-mcp-core authoring guide)

- Every tool registers with explicit `mutates=`. The maintenance tool
  is `mutates=False` (writes the vector store, not the catalog).
- Wrap DERIVA I/O in `with deriva_call():`.
- **Wrap every synchronous deriva-py call inside an `async def` in
  `await asyncio.to_thread(...)`** — sync calls block the event loop
  and can starve the host's permission stream (the load-bearing rule
  from deriva-ml-mcp).
- Import `get_catalog` / `deriva_call` inside the function body, not at
  `register()` scope, so test patches resolve.

## Stateless / bounded-resource rule

MCP tools must be stateless and bounded per call. The maintenance tool
returns counts, not data. The indexing runs as a background task into
the shared vector store (legitimate shared RAG infra, not per-user
workspace state). No `~/.deriva-ml/` reads, no local-FS materialization,
no git introspection.

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
```

- [ ] **Step 3: Write `scripts/rebuild-deriva-docker-mcp.sh`** (port from deriva-ml-mcp)

```bash
#!/usr/bin/env bash
# Rebuild + restart the deriva-mcp-test container in a deriva-docker
# deployment, picking up new DERIVA_MCP_EXTRA_PACKAGES versions.
#
# Usage: ./scripts/rebuild-deriva-docker-mcp.sh [env-file]
# Default env file: ~/.deriva-docker/env/localhost.env
# Default deriva-docker compose dir: $DERIVA_DOCKER_DIR, falling back to
#   $HOME/GitHub/deriva-docker/deriva.

set -euo pipefail

ENV_FILE="${1:-$HOME/.deriva-docker/env/localhost.env}"
SERVICE="${DERIVA_MCP_SERVICE:-deriva-mcp-test}"
DERIVA_DOCKER_DIR="${DERIVA_DOCKER_DIR:-$HOME/GitHub/deriva-docker/deriva}"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "Error: env file not found at $ENV_FILE" >&2
    exit 1
fi
if [[ ! -f "$DERIVA_DOCKER_DIR/docker-compose.yml" ]]; then
    echo "Error: docker-compose.yml not found at $DERIVA_DOCKER_DIR" >&2
    echo "Set DERIVA_DOCKER_DIR to your deriva-docker checkout's compose dir." >&2
    exit 1
fi

cd "$DERIVA_DOCKER_DIR"
echo ">>> Working from: $DERIVA_DOCKER_DIR"
echo ">>> Stopping $SERVICE..."
docker-compose --env-file "$ENV_FILE" down "$SERVICE"
echo ">>> Rebuilding $SERVICE (--no-cache)..."
docker-compose --env-file "$ENV_FILE" build "$SERVICE" --no-cache
echo ">>> Starting $SERVICE..."
docker-compose --env-file "$ENV_FILE" up -d "$SERVICE"
echo ">>> Done. Tail logs with:"
echo "    docker-compose --env-file $ENV_FILE logs -f $SERVICE"
```

- [ ] **Step 4: Make the script executable**

Run: `chmod +x scripts/rebuild-deriva-docker-mcp.sh`

- [ ] **Step 5: Commit**

```bash
git add README.md CLAUDE.md scripts/rebuild-deriva-docker-mcp.sh
git commit -m "docs: README, CLAUDE.md, deriva-docker rebuild script"
```

---

## Task 10: Final verification + push

- [ ] **Step 1: Full suite + lint + format check**

Run: `uv run pytest -v && uv run ruff check src tests && uv run ruff format --check src tests`
Expected: all tests PASS; ruff lint + format clean. (If format flags files, run `uv run ruff format src tests` and re-commit.)

- [ ] **Step 2: Create the GitHub repo and push**

```bash
gh repo create informatics-isi-edu/eye-ai-deriva-mcp-plugin --private --source=. --remote=origin --description "Eye-AI domain RAG indexing plugin for deriva-mcp-core"
git push -u origin main
```

(Use `--public` instead of `--private` if the project convention is public repos; confirm with the owner. The other deriva repos are public.)

- [ ] **Step 3: Tag the initial pre-release**

Run: `uv run bump-version` is not needed for the first tag; the version is already `0.1.0`. Create the tag explicitly:
```bash
git tag -a v0.1.0 -m "v0.1.0 -- initial eye-ai RAG indexing plugin"
git push origin v0.1.0
```

---

## Self-review notes

- **Spec coverage:** host-gate (Task 6), table list (Task 2), catalog-public `eye-ai:` source (Task 4), TTL gate (Task 5), background task (Task 6), serializer (Task 3), maintenance tool (Task 7), entry-point-name==package-name (Task 1), CLAUDE.md stateless rule (Task 9), deriva-docker deployment (Task 9). All spec sections map to a task.
- **Deferred item:** the real `EYE_AI_TABLES` list — implemented as a placeholder constant + env override (Task 2), correctable in one line per the user's direction.
- **Dropped from spec:** GitHub doc RAG source (design review), per-user ACL split (no eye-ai ACLs), domain tools (v0.1 non-goal), prompts (v0.1 non-goal). None appear in tasks — correct.
- **Type consistency:** `_index_catalog` returns `{"tables_indexed","tables_failed","rows_indexed"}` in Tasks 5/6/7; the maintenance tool spreads it (Task 7); `_source_name`/`_write_table`/`_fetch_table_rows` signatures match across Tasks 4-7.
- **Open verification risk:** `chunk_markdown`'s yielded object field names (`.text`, `.section_heading`, `.heading_hierarchy`) are assumed from the deriva-ml-mcp `_write_row_chunk` usage. Task 4 Step 4 (running the test) verifies them against the real API; if a name differs, fix in the `_write_table` loop and re-run.
