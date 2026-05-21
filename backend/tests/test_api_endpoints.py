"""End-to-end tests for the FastAPI endpoints.

These tests run against the test-only app in conftest.py (which mocks
out RAGSystem). They cover request/response shape, status codes, error
paths, and session handling — none of it depends on ChromaDB or Anthropic.
"""

import pytest


# ---------------------------------------------------------------------------
# POST /api/query
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_query_returns_answer_sources_and_session(client, sample_query_payload, mock_rag_system):
    response = client.post("/api/query", json=sample_query_payload)

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "This is a mocked answer about MCP."
    assert body["session_id"] == "test-session-123"
    assert isinstance(body["sources"], list) and len(body["sources"]) == 2
    assert body["sources"][0] == {
        "text": "MCP Course - Lesson 1",
        "link": "https://example.com/mcp/lesson-1",
    }
    # Second source has link=None — the response model should preserve that.
    assert body["sources"][1]["link"] is None

    mock_rag_system.query.assert_called_once_with("What is MCP?", "test-session-123")


@pytest.mark.api
def test_query_creates_session_when_omitted(client, mock_rag_system):
    response = client.post("/api/query", json={"query": "hello"})

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "new-session-id"
    mock_rag_system.session_manager.create_session.assert_called_once()
    mock_rag_system.query.assert_called_once_with("hello", "new-session-id")


@pytest.mark.api
def test_query_uses_provided_session_id(client, mock_rag_system):
    response = client.post(
        "/api/query", json={"query": "hi", "session_id": "preset-session"}
    )

    assert response.status_code == 200
    assert response.json()["session_id"] == "preset-session"
    mock_rag_system.session_manager.create_session.assert_not_called()


@pytest.mark.api
def test_query_missing_query_field_returns_422(client):
    response = client.post("/api/query", json={"session_id": "s1"})
    assert response.status_code == 422


@pytest.mark.api
def test_query_wrong_type_returns_422(client):
    response = client.post("/api/query", json={"query": 123})
    assert response.status_code == 422


@pytest.mark.api
def test_query_empty_body_returns_422(client):
    response = client.post("/api/query", json={})
    assert response.status_code == 422


@pytest.mark.api
def test_query_rag_failure_returns_500(client, mock_rag_system):
    mock_rag_system.query.side_effect = RuntimeError("vector store offline")

    response = client.post("/api/query", json={"query": "anything"})

    assert response.status_code == 500
    assert "vector store offline" in response.json()["detail"]


@pytest.mark.api
def test_query_empty_sources_list_is_allowed(client, mock_rag_system):
    mock_rag_system.query.return_value = ("direct answer", [])

    response = client.post(
        "/api/query", json={"query": "general knowledge", "session_id": "s2"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "direct answer"
    assert body["sources"] == []


# ---------------------------------------------------------------------------
# GET /api/courses
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_courses_returns_stats(client, mock_rag_system):
    response = client.get("/api/courses")

    assert response.status_code == 200
    body = response.json()
    assert body["total_courses"] == 2
    assert body["course_titles"] == ["MCP Course", "Advanced Retrieval"]
    mock_rag_system.get_course_analytics.assert_called_once()


@pytest.mark.api
def test_courses_with_empty_catalog(client, mock_rag_system):
    mock_rag_system.get_course_analytics.return_value = {
        "total_courses": 0,
        "course_titles": [],
    }

    response = client.get("/api/courses")

    assert response.status_code == 200
    assert response.json() == {"total_courses": 0, "course_titles": []}


@pytest.mark.api
def test_courses_failure_returns_500(client, mock_rag_system):
    mock_rag_system.get_course_analytics.side_effect = RuntimeError("chroma down")

    response = client.get("/api/courses")

    assert response.status_code == 500
    assert "chroma down" in response.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/sessions/{session_id}
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_delete_session_returns_204(client, mock_rag_system):
    response = client.delete("/api/sessions/abc-123")

    assert response.status_code == 204
    assert response.content == b""
    mock_rag_system.session_manager.delete_session.assert_called_once_with("abc-123")


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_root_endpoint_responds(client):
    """In production this is the static frontend; in tests it's a JSON probe."""
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# Unknown routes / method mismatches
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_unknown_endpoint_returns_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404


@pytest.mark.api
def test_get_on_query_endpoint_returns_405(client):
    response = client.get("/api/query")
    assert response.status_code == 405


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------


@pytest.mark.api
def test_cors_headers_present_on_query(client, sample_query_payload):
    response = client.post(
        "/api/query",
        json=sample_query_payload,
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "*"
