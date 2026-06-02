"""Tests for the config module (defaults + env overrides)."""

from __future__ import annotations

from eye_ai_deriva_mcp_plugin import config


def test_default_host():
    assert config.eye_ai_host({}) == "www.eye-ai.org"


def test_host_env_override():
    assert config.eye_ai_host({"EYE_AI_DERIVA_MCP_HOST": "dev.eye-ai.org"}) == "dev.eye-ai.org"


def test_host_env_override_blank_falls_back_to_default():
    assert config.eye_ai_host({"EYE_AI_DERIVA_MCP_HOST": "  "}) == "www.eye-ai.org"


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
