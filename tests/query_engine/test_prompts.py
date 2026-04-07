"""
Unit tests for query_engine/prompts.py.

These tests are pure in-memory — no database, no network.
"""
from app.query_engine.prompts import build_system_prompt


def test_build_system_prompt_contains_grounding_instruction():
    """LLM must be told to answer using ONLY the provided context."""
    prompt = build_system_prompt("Some context text here.")
    assert "ONLY" in prompt or "only" in prompt


def test_build_system_prompt_contains_no_hallucination_rule():
    """The prompt must instruct the LLM not to make up information."""
    prompt = build_system_prompt("Some context text here.")
    assert "Do not make up" in prompt


def test_build_system_prompt_contains_context_text():
    context = "Paris is the capital of France."
    prompt = build_system_prompt(context)
    assert context in prompt


def test_build_system_prompt_explicit_fallback_instruction():
    """Prompt must tell LLM to say so when context lacks the answer."""
    prompt = build_system_prompt("Irrelevant context.")
    assert "say so" in prompt or "does not contain" in prompt


def test_build_system_prompt_returns_string():
    result = build_system_prompt("Any context.")
    assert isinstance(result, str)
    assert len(result) > 0


def test_build_system_prompt_empty_context():
    """Empty context should not raise — the LLM will acknowledge no content."""
    prompt = build_system_prompt("")
    assert isinstance(prompt, str)
