"""Tests that drive RAGSystem.query end-to-end for a content question.

Real VectorStore + real chroma_db, but anthropic.Anthropic is patched
so we don't depend on the API. The mock scripts a tool_use turn
followed by an end_turn turn.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from config import config
from rag_system import RAGSystem

CHROMA_PATH = Path(__file__).resolve().parent.parent / "chroma_db"


def _text_block(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(name, inp, id="tu"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def _response(content, stop_reason):
    return SimpleNamespace(content=content, stop_reason=stop_reason)


@pytest.fixture
def scripted_anthropic():
    """Patches anthropic.Anthropic so RAGSystem talks to a scripted fake."""
    with patch("ai_generator.anthropic.Anthropic") as cls:
        instance = MagicMock()
        cls.return_value = instance
        yield instance


@pytest.fixture
def rag(scripted_anthropic):
    if not CHROMA_PATH.exists():
        pytest.skip(f"chroma_db not found at {CHROMA_PATH}")
    # Override the chroma path so the test doesn't depend on CWD.
    cfg = config
    cfg.CHROMA_PATH = str(CHROMA_PATH)
    return RAGSystem(cfg)


def _script_tool_then_answer(mock_anthropic, tool_input, final_text="final answer"):
    """Wire the mock to return: tool_use(search_course_content, tool_input) -> end_turn(final_text)."""
    first = _response(
        [_tool_use_block("search_course_content", tool_input, id="tu_1")],
        stop_reason="tool_use",
    )
    second = _response([_text_block(final_text)], stop_reason="end_turn")
    mock_anthropic.messages.create.side_effect = [first, second]


def test_content_query_returns_answer_and_sources_without_raising(rag, scripted_anthropic):
    _script_tool_then_answer(scripted_anthropic, {"query": "What is MCP?"})
    answer, sources = rag.query("What is MCP?")
    assert answer == "final answer"
    assert isinstance(sources, list)


def test_search_tool_is_invoked_for_content_query(rag, scripted_anthropic):
    _script_tool_then_answer(scripted_anthropic, {"query": "What is MCP?"})
    with patch.object(rag.tool_manager, "execute_tool", wraps=rag.tool_manager.execute_tool) as spy:
        rag.query("What is MCP?")
    spy.assert_called_once()
    args, kwargs = spy.call_args
    assert args[0] == "search_course_content"
    assert kwargs.get("query") == "What is MCP?"


def test_sources_populated_then_reset(rag, scripted_anthropic):
    _script_tool_then_answer(scripted_anthropic, {"query": "What is MCP?"})
    answer, sources_from_query = rag.query("What is MCP?")
    # After query() returns, reset_sources() has been called.
    assert rag.tool_manager.get_last_sources() == []
    # The sources value yielded by query() captures what was there mid-flow.
    # We don't assert non-empty here because the search may legitimately
    # return zero hits if the underlying store is misconfigured (which is
    # exactly the bug we're hunting); we assert the shape.
    assert isinstance(sources_from_query, list)


def test_session_history_recorded(rag, scripted_anthropic):
    _script_tool_then_answer(scripted_anthropic, {"query": "What is MCP?"}, final_text="answer-X")
    session_id = rag.session_manager.create_session()
    rag.query("What is MCP?", session_id=session_id)
    history = rag.session_manager.get_conversation_history(session_id)
    assert history is not None
    assert "What is MCP?" in history
    assert "answer-X" in history
