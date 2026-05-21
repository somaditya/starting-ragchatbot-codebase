# Testing Framework Enhancement

Note: the task brief said "Only do this for front-end features," but the work it described — FastAPI endpoint tests, pytest config, conftest fixtures — is entirely backend. I implemented the requested backend testing infrastructure and am recording it here per the instruction.

No frontend code was modified.

## Summary

Added API-layer test coverage that exercises the FastAPI endpoints the frontend talks to (`/api/query`, `/api/courses`, `/api/sessions/{id}`, `/`) without requiring ChromaDB, the Anthropic API, or the `../frontend` static mount.

## Files changed

### `pyproject.toml` — pytest configuration

Added `[tool.pytest.ini_options]`:

- `testpaths = ["backend/tests"]` — `uv run pytest` from the repo root finds the suite without arguments.
- `addopts = ["-ra", "--strict-markers", "--strict-config", "--tb=short"]` — surface every non-pass result, fail on typo'd markers, keep tracebacks short.
- `markers` — registers `api` and `integration` so tests can be filtered (`uv run pytest -m api`).
- `filterwarnings` — suppresses third-party deprecation noise so real failures stand out.

### `backend/tests/conftest.py` — shared fixtures

Rewrote from a 3-line `sys.path` shim into a fixture module:

- `sample_query_payload`, `sample_sources`, `sample_course_analytics` — reusable test data matching the production response shapes.
- `mock_rag_system` — a `MagicMock` `RAGSystem` with `query`, `get_course_analytics`, and `session_manager` pre-wired; tests can override `side_effect` to script error paths.
- `test_app` — builds a fresh `FastAPI` instance inline that mirrors the routes in `backend/app.py` but **does not** mount `StaticFiles(directory="../frontend")` and **does not** construct a real `RAGSystem`. This avoids the two failure modes you'd hit by importing `backend.app` directly: the static mount blows up because `../frontend` is path-relative to CWD, and the module-level `RAGSystem(config)` requires ChromaDB and an Anthropic key.
- `client` — `fastapi.testclient.TestClient` bound to the test app.

### `backend/tests/test_api_endpoints.py` — new file, 16 tests

All marked `@pytest.mark.api`. Coverage:

- **`POST /api/query`** (8 tests) — happy path with provided session, auto-creation of session when omitted, preservation of caller-supplied session ID, 422 on missing/wrong-typed/empty body, 500 propagation when `RAGSystem.query` raises, empty-sources response shape.
- **`GET /api/courses`** (3 tests) — populated catalog, empty catalog, 500 on analytics failure.
- **`DELETE /api/sessions/{id}`** (1 test) — returns 204 with empty body and forwards the ID to `session_manager.delete_session`.
- **`GET /`** (1 test) — confirms the test stand-in for the static mount responds.
- **Routing** (2 tests) — 404 for unknown paths, 405 for `GET /api/query`.
- **CORS** (1 test) — `Access-Control-Allow-Origin: *` is present.

## Test results

```
uv run pytest
================== 31 passed, 10 skipped in 11.55s ==================
```

The 10 skips are pre-existing — they require `backend/chroma_db/` populated from a prior server run and are unchanged by this work.

Running just the new suite:

```
uv run pytest -m api
================== 16 passed ==================
```

## Why the test app is defined inline instead of imported

`backend/app.py` does two things at module-import time that break in a test context:

1. `app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")` — `StaticFiles` checks the directory exists when mounted, and `../frontend` is relative to the current working directory. `uv run pytest` from the repo root resolves it to `/.../starting-ragchatbot-codebase/.trees/testing_feature/frontend` (which doesn't exist).
2. `rag_system = RAGSystem(config)` — instantiates ChromaDB and the Anthropic client eagerly.

Building the routes inline against `mock_rag_system` sidesteps both. The downside is the test app drifts from the real one if endpoints are added; the upside is the API tests stay fast (sub-second) and hermetic.

---

# Frontend Changes — Dark / Light Theme Toggle

Added a fully accessible light/dark theme toggle to the Course Materials Assistant frontend. The toggle floats in the top-right corner, switches the entire UI via a single `data-theme` attribute on `<html>`, and persists the user's choice across reloads.

## Files Touched

- `frontend/index.html`
- `frontend/style.css`
- `frontend/script.js`

(No backend changes — feature is purely client-side.)

---

## 1. `frontend/index.html`

- Bumped cache-busting query strings: `style.css?v=9` → `?v=10` and `script.js?v=9` → `?v=10`.
- Added a new `<button id="themeToggle">` immediately inside `<body>`, before `.container`, so it can be positioned `fixed` relative to the viewport without being constrained by the chat layout. The button:
  - Has `type="button"`, `aria-label="Toggle color theme"`, `aria-pressed="false"`, and a `title` attribute — keyboard-focusable and screen-reader-friendly by default.
  - Contains two inline SVGs (`.theme-icon-sun` and `.theme-icon-moon`) with `aria-hidden="true"`. CSS swaps their visibility based on the active theme.

## 2. `frontend/style.css`

### Theme variables

- Restructured the `:root` rule so dark mode lives on both `:root` and `[data-theme="dark"]`.
- Added a `[data-theme="light"]` block with a balanced light palette:
  - `--background: #f8fafc`, `--surface: #ffffff`, `--surface-hover: #f1f5f9`
  - `--text-primary: #0f172a`, `--text-secondary: #475569`
  - `--border-color: #e2e8f0`
  - `--assistant-message: #e2e8f0`, `--welcome-bg: #eff6ff`
  - Softer shadow tuned for light surfaces.
- Introduced new tokens used in both themes so previously hard-coded `rgba(...)` colors flip cleanly:
  - `--code-bg` — backing for `<code>` / `<pre>` inside messages.
  - `--source-chip-bg`, `--source-chip-border`, `--source-chip-hover-bg` — for source link chips.

### Smooth transitions

- Added `transition: background-color 0.3s ease, color 0.3s ease` to `body`.
- Added a grouped transition rule covering every themed surface (sidebar, chat container, messages, input, suggested items, stat cards, source chips, the toggle itself) so a theme switch animates instead of snapping.

### Theme toggle button styles

- Circular 44 × 44 px button, `position: fixed; top: 1rem; right: 1rem; z-index: 1000`.
- Uses themed tokens (`--surface`, `--border-color`, `--text-primary`, `--shadow`) so the button itself recolors with the rest of the UI.
- Hover: lifts (`translateY(-1px)`), recolors border + icon to `--primary-color`.
- Active: returns to baseline `translateY(0)`.
- `:focus-visible` shows a 3px ring using `--focus-ring` for keyboard accessibility.
- Sun/moon icons are absolutely positioned in the same spot and cross-fade with a 0.3s opacity + 0.4s rotate-and-scale transform:
  - Dark theme → moon visible, sun hidden (rotated −90°, scaled to 0.6).
  - Light theme → sun visible, moon hidden (rotated 90°, scaled to 0.6).
- Mobile (`max-width: 768px`): toggle shrinks to 40 × 40 px and nudges to `0.5rem` from the corners.

### Hard-coded color cleanup

- `.message-content code` and `.message-content pre` now use `var(--code-bg)` instead of `rgba(0, 0, 0, 0.2)`.
- `.sources-content .source-chip` background/border now use `var(--source-chip-bg)` / `var(--source-chip-border)`.
- `.sources-content .source-link:hover` background uses `var(--source-chip-hover-bg)`.

## 3. `frontend/script.js`

- Added `themeToggle` to the module-level DOM-element list and grabbed it on `DOMContentLoaded`.
- Called a new `initTheme()` before `setupEventListeners()` so the page renders in the correct theme immediately.
- Registered a `click` listener on the toggle in `setupEventListeners()`.
- Added theme management helpers:
  - `getStoredTheme()` / `storeTheme(theme)` — wrap `localStorage` in try/catch (private mode / quota safe).
  - `applyTheme(theme)` — sets `data-theme` on `<html>`, syncs `aria-pressed` and updates the `aria-label` to read "Switch to dark theme" / "Switch to light theme" so screen readers announce the next action.
  - `initTheme()` — reads stored preference first, otherwise honors `prefers-color-scheme: light` (defaults to dark).
  - `toggleTheme()` — flips the current value, applies it, and persists it.

## Accessibility & UX Notes

- Toggle is a real `<button>` — natively focusable and operable with Enter/Space.
- `aria-pressed` reflects state; `aria-label` updates to describe the action that *will* happen on click.
- All themed transitions cap at 0.3–0.4s — fast enough to feel snappy, slow enough to avoid a hard color flash.
- Contrast pairings verified against WCAG AA:
  - Light: `#0f172a` on `#f8fafc` / `#ffffff` (≥ 15:1).
  - Dark: `#f1f5f9` on `#0f172a` / `#1e293b` (≥ 13:1).
  - Secondary text in light mode uses `#475569` on `#f8fafc` (≈ 8:1).
- Toggle position (top-right, fixed) keeps it reachable without overlapping the header (which is `display: none`) or interfering with the chat input.

---

# Frontend & Code Quality Changes

This document records the code-quality tooling added to the repo and the
formatting that resulted from running it once across the codebase.

## Summary

- **Black** (Python) is now configured for the `backend/` directory.
- **Prettier** (JS / HTML / CSS / JSON / Markdown) is now configured for the
  `frontend/` directory.
- Four wrapper scripts under `scripts/` give a single entry point for
  formatting and for non-mutating quality checks (CI / pre-push friendly).
- Every existing `backend/*.py` and `frontend/*.{html,js,css}` file has been
  reformatted once so the repo starts in a clean state.

The user request was for "front-end" code quality, but Black is Python-only.
After confirming with the user, the work was widened to cover both layers —
Prettier for the actual frontend, Black for the Python backend — and all
changes are recorded here in `frontend-changes.md` as requested.

## New files

| Path                          | Purpose                                                                  |
| ----------------------------- | ------------------------------------------------------------------------ |
| `package.json`                | Pins `prettier@^3.3.3` as a dev dep. Project itself stays vanilla JS.    |
| `package-lock.json`           | Lockfile generated by `npm install`.                                     |
| `.prettierrc.json`            | Prettier config (100-col, 4-space JS/CSS, 2-space HTML, single quotes).  |
| `.prettierignore`             | Excludes `node_modules/`, `backend/`, `docs/`, `.venv/`, `uv.lock`, etc. |
| `scripts/format.sh`           | Formats both layers in-place (backend via Black, frontend via Prettier). |
| `scripts/format-backend.sh`   | Backend-only formatter.                                                  |
| `scripts/format-frontend.sh`  | Frontend-only formatter.                                                 |
| `scripts/quality-check.sh`    | Read-only check; exits non-zero if either tool would reformat anything.  |
| `frontend-changes.md`         | This document.                                                           |

## Modified files

### Config

- **`pyproject.toml`**
  - `black>=26.5.1` added under `[dependency-groups].dev`.
  - New `[tool.black]` block: `line-length = 100`, `target-version = ["py313"]`,
    excludes `.venv`, `.git`, `backend/chroma_db`, `node_modules`.
- **`uv.lock`** — regenerated by `uv add --dev black`.
- **`.gitignore`** — added `node_modules/` and `npm-debug.log*` so the Prettier
  install doesn't get committed.

### Reformatted by Black (14 files in `backend/`)

`app.py`, `ai_generator.py`, `config.py`, `document_processor.py`, `models.py`,
`rag_system.py`, `search_tools.py`, `session_manager.py`, `vector_store.py`,
`tests/test_ai_generator.py`, `tests/test_course_search_tool.py`,
`tests/test_rag_system.py` — plus two files that were already compliant.

These changes are formatting-only: line wrapping at 100 cols, double-quoted
strings, trailing commas in multi-line literals, blank-line normalization.
Black guarantees an equivalent AST, so no runtime behavior changed.

### Reformatted by Prettier (3 files in `frontend/`)

| File                 | Diff (lines)              |
| -------------------- | ------------------------- |
| `frontend/index.html`| 176 changed (+ / -)       |
| `frontend/script.js` |  58 changed               |
| `frontend/style.css` |  62 changed               |

Notable shifts:

- **`index.html`** — Re-indented from 4-space to 2-space (HTML-only override
  in `.prettierrc.json`), self-closing void tags (`<meta ... />`), lowercase
  `<!doctype html>`, `<head>`/`<body>` indented one level under `<html>`.
- **`script.js`** — Switched to single quotes, trailing commas in multi-line
  literals, consistent spacing in template literals, method chains broken
  across lines for readability.
- **`style.css`** — Selector lists put on separate lines, consistent space
  after colons, blank-line normalization between rule blocks.

No selectors, no DOM IDs, no class names, no event-handler logic, and no
network paths were renamed or removed. The page still loads and runs
identically — only whitespace, quotes, and trailing punctuation changed.

## How to use

From the repo root:

```bash
# Apply formatters in-place across the whole repo.
./scripts/format.sh

# Or scope to one layer.
./scripts/format-backend.sh    # Black only
./scripts/format-frontend.sh   # Prettier only

# Read-only check — exits 1 if anything would be reformatted.
# Suitable for CI and as a pre-push gate.
./scripts/quality-check.sh
```

Direct invocation is also supported:

```bash
uv run black backend/            # write
uv run black --check backend/    # check

npx prettier --write "frontend/**/*.{js,html,css,json,md}"
npx prettier --check "frontend/**/*.{js,html,css,json,md}"
```

You can also use the npm scripts from `package.json`:

```bash
npm run format         # prettier --write on frontend
npm run format:check   # prettier --check on frontend
```

## Prerequisites

- `uv` (already required by the project) — provides Black.
- Node.js + `npm` — needed for Prettier. Run `npm install` once after cloning
  to populate `node_modules/`. Without it, the frontend scripts will fail
  fast (they use `npx --no-install`).

## Configuration choices, briefly

- **Black `line-length = 100`** — bigger than Black's default 88. Matches the
  Prettier `printWidth` so both layers wrap at the same column, which avoids
  context-switch friction when reading mixed PRs.
- **Prettier `tabWidth = 4` for JS/CSS, `tabWidth = 2` for HTML** — preserves
  the existing 4-space indent the JS/CSS files were already using, while
  HTML uses Prettier's HTML-idiomatic 2-space indent (deeply nested DOM
  blows out 4-space indentation fast).
- **`singleQuote = true`, `trailingComma = "es5"`** — matches what the
  existing `script.js` was already doing, so the diff stays small.
- **`endOfLine = "lf"`** — explicit, since the project is Linux-first and
  this avoids CRLF churn if anyone edits on Windows.

## Verification

After running the formatters once, `./scripts/quality-check.sh` reports:

```
==> Checking backend formatting (black --check)
All done! ✨ 🍰 ✨
14 files would be left unchanged.

==> Checking frontend formatting (prettier --check)
Checking formatting...
All matched files use Prettier code style!

All quality checks passed.
```

The repo is now in a state where any future drift will be caught by the
check script and fixed by the format script.
