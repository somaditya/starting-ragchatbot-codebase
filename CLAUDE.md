# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dependencies are managed by `uv` (Python >= 3.13 required). An `ANTHROPIC_API_KEY` must be set in a root-level `.env` file before the server will function.

**Always use `uv` for everything — running Python files, running the server, adding/removing deps, syncing, and locking. Never invoke `python` or `python3` directly, and never use `pip`, `pip install`, `python -m pip`, or `python -m venv`.**

| Task | Command |
| --- | --- |
| Install / sync from lockfile | `uv sync` |
| Add a dependency | `uv add <pkg>` (updates `pyproject.toml` + `uv.lock`) |
| Remove a dependency | `uv remove <pkg>` |
| Run a Python file | `uv run python <file>.py` |
| Run a Python tool | `uv run <cmd>` — e.g. `uv run pytest` |
| Run the app (preferred) | `./run.sh` — starts uvicorn from `backend/` on port 8000 with reload |
| Run the app (manual) | `cd backend && uv run uvicorn app:app --reload --port 8000` |

Web UI: http://localhost:8000 — API docs: http://localhost:8000/docs.

There is no test suite, linter, or formatter configured. The top-level `main.py` is unused boilerplate (a `print` stub); the real entrypoint is `backend/app.py`.

## Architecture

This is a course-materials RAG chatbot. FastAPI serves both the JSON API under `/api/*` and the static frontend (vanilla JS + HTML) mounted at `/` from `../frontend`. ChromaDB persists locally to `backend/chroma_db/` (gitignored).

### Tool-based RAG (not classic retrieve-then-generate)

`RAGSystem.query` does **not** pre-search and stuff context into the prompt. Instead, `AIGenerator` (`backend/ai_generator.py`) gives Claude a `search_course_content` tool definition and lets the model decide when to call it. The flow:

1. `app.py` → `RAGSystem.query(query, session_id)` builds a prompt and calls `AIGenerator.generate_response` with the tool list from `ToolManager`.
2. Claude either answers directly (general knowledge) or returns `stop_reason == "tool_use"`.
3. On tool use, `AIGenerator._handle_tool_execution` runs every tool block via `ToolManager.execute_tool`, appends results as a user message, and makes a second Claude call **without tools** to produce the final text.
4. `RAGSystem.query` then harvests sources from `CourseSearchTool.last_sources` (mutated as a side-effect of `execute`) via `ToolManager.get_last_sources()`, and calls `reset_sources()` to clear them for the next query.

The system prompt in `AIGenerator.SYSTEM_PROMPT` enforces **at most one search per query** — keep that constraint in mind when modifying tool-use logic.

### Vector store: two collections, not one

`VectorStore` (`backend/vector_store.py`) maintains two ChromaDB collections, both using `all-MiniLM-L6-v2` embeddings:

- `course_catalog` — one document per course (the title), with lessons serialized as a JSON string in metadata. Used for **fuzzy course-name resolution**: when a query specifies `course_name="MCP"`, `_resolve_course_name` semantically matches it to a full title before filtering content.
- `course_content` — the actual chunked text, with `course_title`, `lesson_number`, and `chunk_index` metadata used as ChromaDB `where` filters.

Course title is the unique ID in both collections, so `add_course_folder` dedupes by title and skips re-ingestion.

### Document ingestion format

`DocumentProcessor.process_course_document` expects a strict header format:

```
Course Title: <title>
Course Link: <url>
Course Instructor: <name>

Lesson 0: <lesson title>
Lesson Link: <url>
<lesson content...>

Lesson 1: <lesson title>
...
```

Chunks are sentence-aware (split on sentence boundaries with overlap, sized by `CHUNK_SIZE`/`CHUNK_OVERLAP` from `config.py`) and prefixed with `"Course <title> Lesson <n> content: "` so the embedding captures course/lesson context. If you change chunk text formatting, embeddings shift and previously-indexed data must be re-ingested (delete `backend/chroma_db/` or pass `clear_existing=True`).

### Startup ingestion

`app.py`'s `startup_event` loads everything under `../docs` (relative to `backend/`) on each server start, but `add_course_folder` skips courses whose titles already exist in `course_catalog`. To force a re-ingest, delete `backend/chroma_db/`.

### Session memory

`SessionManager` keeps the last `MAX_HISTORY * 2` messages per `session_id` in-process only (no persistence) and formats them into a string appended to the system prompt. Session IDs are returned to the frontend and echoed back on subsequent `/api/query` calls. Restarting the server drops all sessions.

### Configuration

All tunables live in `backend/config.py` as a `@dataclass` (`ANTHROPIC_MODEL`, `EMBEDDING_MODEL`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `MAX_RESULTS`, `MAX_HISTORY`, `CHROMA_PATH`). The Anthropic model ID is hardcoded here, not in env.

### Adding a new tool

Subclass `Tool` in `backend/search_tools.py` (implement `get_tool_definition` and `execute`), then register it in `RAGSystem.__init__` via `self.tool_manager.register_tool(...)`. If the tool produces sources for the UI, expose them via a `last_sources` attribute — `ToolManager.get_last_sources` picks up the first tool with a non-empty list.
