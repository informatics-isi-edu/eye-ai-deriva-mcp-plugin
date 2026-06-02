"""Tests for the config module (defaults + env overrides)."""

from __future__ import annotations

from eye_ai_deriva_mcp_plugin import config


def test_default_hosts():
    assert config.eye_ai_hosts({}) == {"www.eye-ai.org", "dev.eye-ai.org"}


def test_hosts_env_override():
    env = {"EYE_AI_DERIVA_MCP_HOSTS": "a.eye-ai.org, b.eye-ai.org"}
    assert config.eye_ai_hosts(env) == {"a.eye-ai.org", "b.eye-ai.org"}


def test_default_tables_empty():
    # Clinical-row indexing is opt-in: no tables by default.
    assert config.eye_ai_tables({}) == []


def test_tables_env_override():
    env = {"EYE_AI_DERIVA_MCP_TABLES": "eye-ai:Subject, eye-ai:Image"}
    assert config.eye_ai_tables(env) == [("eye-ai", "Subject"), ("eye-ai", "Image")]


def test_default_ttl():
    assert config.index_ttl_seconds({}) == 86400


def test_ttl_env_override():
    assert config.index_ttl_seconds({"EYE_AI_DERIVA_MCP_INDEX_TTL_SECONDS": "3600"}) == 3600
