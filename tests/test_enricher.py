"""Tests for the eye-ai row enricher."""

from __future__ import annotations

from eye_ai_deriva_mcp_plugin.enricher import make_enricher


async def test_enrich_renders_header_and_fields():
    enrich = make_enricher("Subject")
    md = await enrich({"RID": "1-AAAA", "Subject_Gender": "Female", "Notes": "healthy"}, None)
    assert "## Subject: 1-AAAA" in md
    assert "**Subject_Gender:** Female" in md
    assert "**Notes:** healthy" in md


async def test_enrich_omits_empty_and_system_fields():
    enrich = make_enricher("Image")
    md = await enrich(
        {"RID": "2-BBBB", "URL": "/hatrac/x", "Empty": "", "Null": None, "RCT": "2020"},
        None,
    )
    assert "**URL:** /hatrac/x" in md
    assert "Empty" not in md  # empty string omitted
    assert "Null" not in md  # None omitted
    assert "RCT" not in md  # system column omitted


async def test_enrich_returns_empty_for_rid_less_row():
    enrich = make_enricher("Subject")
    assert await enrich({"Subject_Gender": "no rid"}, None) == ""


async def test_enricher_binds_its_own_table_name():
    # Two enrichers built for different tables render their own header.
    subj = make_enricher("Subject")
    img = make_enricher("Image")
    assert "## Subject: 1-A" in await subj({"RID": "1-A"}, None)
    assert "## Image: 1-A" in await img({"RID": "1-A"}, None)
