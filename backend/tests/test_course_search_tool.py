"""Tests for CourseSearchTool.execute and its formatting helpers.

These tests exercise the search path end-to-end against the real ChromaDB
under backend/chroma_db/ — the bug we're hunting lives at that boundary,
so mocking the store would hide it.
"""

from pathlib import Path

import pytest

from config import config
from search_tools import CourseSearchTool
from vector_store import VectorStore, SearchResults

CHROMA_PATH = Path(__file__).resolve().parent.parent / "chroma_db"


@pytest.fixture(scope="module")
def vector_store():
    if not CHROMA_PATH.exists():
        pytest.skip(f"chroma_db not found at {CHROMA_PATH} — run the server once to ingest.")
    # Use whatever max_results config currently advertises, so the tests see
    # the configured value (the whole point of this suite is to surface
    # config-layer bugs).
    return VectorStore(
        chroma_path=str(CHROMA_PATH),
        embedding_model=config.EMBEDDING_MODEL,
        max_results=config.MAX_RESULTS,
    )


@pytest.fixture
def search_tool(vector_store):
    return CourseSearchTool(vector_store)


def test_config_max_results_is_positive():
    """The most direct symptom check: MAX_RESULTS must be > 0 for content search."""
    assert (
        config.MAX_RESULTS > 0
    ), f"config.MAX_RESULTS={config.MAX_RESULTS}; ChromaDB's query() rejects n_results=0"


def test_execute_returns_content_for_known_query(search_tool):
    """A plain content query against the indexed MCP docs should return real content."""
    result = search_tool.execute(query="What is MCP?")
    assert isinstance(result, str) and result
    assert not result.startswith("Search error"), result
    assert not result.startswith("No relevant content found"), result
    # Real results carry a "[<Course Title> - Lesson N]" header.
    assert "[" in result and "]" in result, result


def test_execute_with_course_name_filter(search_tool):
    result = search_tool.execute(query="protocol", course_name="MCP")
    assert not result.startswith("Search error"), result
    assert not result.startswith("No relevant content found"), result
    # Course filter resolves "MCP" -> the full MCP course title.
    assert "MCP" in result, result


def test_execute_with_lesson_filter(search_tool):
    result = search_tool.execute(query="introduction", course_name="MCP", lesson_number=0)
    assert not result.startswith("Search error"), result
    # Every chunk header for a lesson-filtered search must reference Lesson 0.
    for line in result.splitlines():
        if line.startswith("[") and line.endswith("]"):
            assert "Lesson 0" in line, line


def test_execute_with_unknown_course_does_not_raise(search_tool):
    """An unrecognised course must produce a string, not a stack trace.

    Note: _resolve_course_name has no distance gate today, so an unknown
    string may map to the nearest-neighbour course title. We don't assert
    the "no course" wording — only that the call is safe.
    """
    result = search_tool.execute(query="anything", course_name="ZZZ_does_not_exist_ZZZ")
    assert isinstance(result, str) and result


def test_last_sources_populated_after_successful_execute(search_tool):
    result = search_tool.execute(query="What is MCP?")
    if result.startswith("Search error") or result.startswith("No relevant content"):
        pytest.skip(f"search did not return content; cannot assert on sources: {result!r}")
    assert search_tool.last_sources, "last_sources should be non-empty after a hit"
    for s in search_tool.last_sources:
        assert isinstance(s, dict) and "text" in s and "link" in s, s


def test_format_results_unit(vector_store):
    """Pure-unit: feed _format_results synthetic data, assert shape + sources."""
    tool = CourseSearchTool(vector_store)
    fake = SearchResults(
        documents=["chunk one body", "chunk two body"],
        metadata=[
            {"course_title": "Test Course", "lesson_number": 1, "chunk_index": 0},
            {"course_title": "Test Course", "lesson_number": 2, "chunk_index": 1},
        ],
        distances=[0.1, 0.2],
    )
    out = tool._format_results(fake)
    assert "[Test Course - Lesson 1]" in out
    assert "[Test Course - Lesson 2]" in out
    assert "chunk one body" in out and "chunk two body" in out
    assert len(tool.last_sources) == 2
    assert tool.last_sources[0]["text"] == "Test Course - Lesson 1"
    assert tool.last_sources[1]["text"] == "Test Course - Lesson 2"
