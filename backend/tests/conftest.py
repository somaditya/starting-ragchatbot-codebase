"""Shared fixtures for the backend test suite.

Two responsibilities:

1. Make `backend/` importable so tests can `from app import …` without
   touching `sys.path` themselves.
2. Provide a *test-only* FastAPI app that mirrors the real endpoints in
   `backend/app.py` but skips the `StaticFiles` mount (the `../frontend`
   directory is path-relative to the CWD the server is launched from, so
   importing `app.py` inside the test runner crashes on the mount). The
   handlers are defined inline against a mocked `RAGSystem`, so the tests
   exercise request/response wiring without ChromaDB or Anthropic.
"""

import sys
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock

import pytest

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------


@pytest.fixture
def sample_query_payload():
    """A typical POST body for /api/query."""
    return {"query": "What is MCP?", "session_id": "test-session-123"}


@pytest.fixture
def sample_sources():
    """Source citations as the search tool would surface them."""
    return [
        {"text": "MCP Course - Lesson 1", "link": "https://example.com/mcp/lesson-1"},
        {"text": "MCP Course - Lesson 2", "link": None},
    ]


@pytest.fixture
def sample_course_analytics():
    """Shape returned by `RAGSystem.get_course_analytics`."""
    return {
        "total_courses": 2,
        "course_titles": ["MCP Course", "Advanced Retrieval"],
    }


# ---------------------------------------------------------------------------
# Mock RAG system
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_rag_system(sample_sources, sample_course_analytics):
    """A MagicMock standing in for `RAGSystem`.

    Pre-wired so the common endpoint paths return useful values; tests can
    override any attribute (e.g. `mock_rag_system.query.side_effect = ...`)
    to script error paths.
    """
    rag = MagicMock()
    rag.query.return_value = ("This is a mocked answer about MCP.", sample_sources)
    rag.get_course_analytics.return_value = sample_course_analytics
    rag.session_manager = MagicMock()
    rag.session_manager.create_session.return_value = "new-session-id"
    rag.session_manager.delete_session.return_value = None
    return rag


# ---------------------------------------------------------------------------
# Test-only FastAPI app
# ---------------------------------------------------------------------------


@pytest.fixture
def test_app(mock_rag_system):
    """Build a FastAPI app that mirrors `backend/app.py`'s routes.

    We don't import `backend.app` because it eagerly:
      - constructs a real `RAGSystem` (ChromaDB + Anthropic)
      - mounts `StaticFiles(directory="../frontend")`, which fails if the
        CWD at import time isn't `backend/`.

    Instead, define the same routes here against `mock_rag_system`.
    """
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel

    class QueryRequest(BaseModel):
        query: str
        session_id: Optional[str] = None

    class SourceCitation(BaseModel):
        text: str
        link: Optional[str] = None

    class QueryResponse(BaseModel):
        answer: str
        sources: List[SourceCitation]
        session_id: str

    class CourseStats(BaseModel):
        total_courses: int
        course_titles: List[str]

    app = FastAPI(title="Course Materials RAG System (test)")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()
            answer, sources = mock_rag_system.query(request.query, session_id)
            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/api/sessions/{session_id}", status_code=204)
    async def delete_session(session_id: str):
        mock_rag_system.session_manager.delete_session(session_id)
        return None

    @app.get("/")
    async def root():
        # The real app mounts StaticFiles at "/"; the test stand-in just
        # confirms the route exists so frontend code paths can be probed
        # without bringing in `../frontend`.
        return {"status": "ok", "service": "course-materials-rag"}

    return app


@pytest.fixture
def client(test_app):
    """Synchronous TestClient bound to the test app."""
    from fastapi.testclient import TestClient

    return TestClient(test_app)
