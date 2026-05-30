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
