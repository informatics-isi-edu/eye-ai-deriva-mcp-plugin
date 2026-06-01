"""Tests for the eye-ai domain MCP prompts."""

from __future__ import annotations

import pytest

from eye_ai_deriva_mcp_plugin.prompts import register

_EXPECTED = {"eye-ai-assistant", "find-images", "explore-diagnosis"}


def test_three_prompts_registered(ctx):
    register(ctx)
    assert set(ctx._mcp.prompts) == _EXPECTED


def test_assistant_renders_nonempty_with_defaults(ctx):
    register(ctx)
    text = ctx._mcp.prompts["eye-ai-assistant"]()
    assert "www.eye-ai.org" in text
    assert "ophthalmology" in text.lower()
    # No leftover f-string braces in the rendered output.
    assert "{" not in text and "}" not in text


@pytest.mark.parametrize(
    ("name", "arg"),
    [("find-images", "fundus images of glaucoma"), ("explore-diagnosis", "diabetic retinopathy")],
)
def test_task_prompts_take_an_argument_and_name_schema(ctx, name, arg):
    register(ctx)
    text = ctx._mcp.prompts[name](arg)
    assert arg in text  # the user's criteria/diagnosis is woven in
    assert "eye-ai:" in text  # references the real ERMrest schema
    assert "{" not in text and "}" not in text
