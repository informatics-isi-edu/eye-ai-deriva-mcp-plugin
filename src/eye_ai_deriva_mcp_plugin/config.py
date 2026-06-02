"""Configuration for the eye-ai RAG indexer.

All values have a hard-coded default and an env override read from the
merged environment map (``ctx.env``). The plugin reads config through
these functions rather than module-level constants so an operator can
override the eye-ai host set, the indexed table list, and the re-index
TTL without code changes.
"""

from __future__ import annotations

_DEFAULT_HOST = "www.eye-ai.org"

# Clinical-row table list -- empty by default, opt-in via the
# ``EYE_AI_DERIVA_MCP_TABLES`` env override. With no override, the plugin
# registers no ``rag_dataset_indexer`` (no clinical-row indexing); the
# papers ``rag_github_source`` and the domain prompts still register.
# An operator sets the env var to a comma-separated ``schema:table`` list
# (ERMrest case; domain schema is ``eye-ai``, lowercase/hyphenated) to
# turn it on -- e.g. ``eye-ai:Subject,eye-ai:Image,eye-ai:Observation``.
# Each entry is a (schema, table) pair.
_DEFAULT_TABLES: tuple[tuple[str, str], ...] = ()

_DEFAULT_TTL_SECONDS = 86400  # 24h


def eye_ai_host(env: dict[str, str]) -> str:
    """Return the single hostname that scopes eye-ai indexing.

    The server runs against one eye-ai catalog, so the clinical-row
    indexers are scoped to one host. Env override
    ``EYE_AI_DERIVA_MCP_HOST`` sets it (e.g. ``"dev.eye-ai.org"``).

    Args:
        env: The merged environment map (``ctx.env``).

    Returns:
        The eye-ai hostname the indexers are scoped to.

    Example:
        >>> eye_ai_host({})
        'www.eye-ai.org'
        >>> eye_ai_host({"EYE_AI_DERIVA_MCP_HOST": "dev.eye-ai.org"})
        'dev.eye-ai.org'
    """
    return env.get("EYE_AI_DERIVA_MCP_HOST", "").strip() or _DEFAULT_HOST


def eye_ai_tables(env: dict[str, str]) -> list[tuple[str, str]]:
    """Return the ordered list of (schema, table) pairs to index.

    Env override ``EYE_AI_DERIVA_MCP_TABLES`` is a comma-separated list
    of ``schema:table`` tokens.

    Args:
        env: The merged environment map (``ctx.env``).

    Returns:
        Ordered list of ``(schema, table)`` tuples.

    Example:
        >>> eye_ai_tables({"EYE_AI_DERIVA_MCP_TABLES": "eye-ai:Subject"})
        [('eye-ai', 'Subject')]
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
