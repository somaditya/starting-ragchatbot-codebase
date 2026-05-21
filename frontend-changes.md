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
