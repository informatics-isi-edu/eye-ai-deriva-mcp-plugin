"""Configuration for the eye-ai RAG indexer.

All values have a hard-coded default and an env override read from the
merged environment map (``ctx.env``). The plugin reads config through
these functions rather than module-level constants so an operator can
override the eye-ai host set, the indexed table list, and the re-index
TTL without code changes.
"""

from __future__ import annotations

_DEFAULT_HOSTS = ("www.eye-ai.org", "dev.eye-ai.org")

# Starter table list -- the real curated set is supplied by the project
# owner later and swapped in here (or via the env override). Each entry
# is a (schema, table) pair in ERMrest case. The domain schema is
# ``eye-ai`` (lowercase, hyphenated); the four tables below all exist on
# the live catalog. The sibling deriva-ml-mcp-plugin already indexes all
# vocabularies (including Condition_Label) and the deriva-ml datasets, so
# this plugin's unique contribution is the clinical domain rows.
_DEFAULT_TABLES = (
    ("eye-ai", "Subject"),
    ("eye-ai", "Image"),
    ("eye-ai", "Observation"),
    ("eye-ai", "Condition_Label"),
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
        >>> sorted(eye_ai_hosts({}))
        ['dev.eye-ai.org', 'www.eye-ai.org']
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
