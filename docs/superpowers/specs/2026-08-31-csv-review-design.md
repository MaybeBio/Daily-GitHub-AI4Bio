# CSV Review Tool — Design

Date: 2026-08-31
Status: Approved (user: "ok")

## Problem

Each weekly discovery run produces a CSV with ~100–500 repos (columns:
`fullName, language, stargazersCount, createdAt, pushedAt, url, description, description_zh`).
Manually reviewing them requires horizontal scrolling (wide description column),
and the user wants to record a per-repo decision (keep / later / skip) that
survives across review sessions.

## Goal

A single local tool to quickly screen, read, and mark a weekly CSV:

- No horizontal scrolling — long cells wrap.
- Three-state mark per repo: ✅ 关注 (keep), ⏸ 稍后 (later), ❌ 跳过 (skip).
- Marks persist back into the CSV (a `mark` column), so reopening the file shows
  prior state and re-running `weekly_report.py` won't destroy them.
- One-click export of the ✅ rows.

## Approach

`scripts/csv_review.py` — a stdlib-only Python script that:

1. Reads the target CSV, embeds the data into a self-contained HTML page.
2. Serves the page on a localhost HTTP server and auto-opens the browser.
3. Receives a POST from the page to write marks back to the original CSV.

Rationale: a browser cannot write local files, so the script runs a tiny
`http.server`-based server to receive the mark data and write the CSV in place.
No third-party dependencies; runs on any machine with Python 3.

## Interface

Usage:

```
python3 scripts/csv_review.py discovery/weekly/2026/08/idr_2026-08-31.csv
```

Then `--port` (default 8000) and `--no-browser` (don't auto-open) options.

### Page features

- **Wrapped cells** — every column wraps; the page scrolls vertically only.
- **Search box** — filters rows by substring across all visible text fields.
- **Mark filter** — chips: 全部 / 未标 / ✅ / ⏸ / ❌.
- **Column toggles** — checkboxes to hide/show columns (default: all shown).
- **Sort** — clickable sort by stargazersCount / pushedAt / createdAt / fullName
  (toggle asc/desc).
- **Per-row marks** — a three-button control (✅ / ⏸ / ❌); click to set, click
  again or "清除" to unset. Row tinted by its mark.
- **保存标注** button — POSTs all current marks back to the server.
- **导出关注清单** button — copies the ✅ rows (fullName + url + description_zh,
  one per line) to the clipboard.

### Data flow

- Page load: GET / returns the HTML with the CSV rows embedded as JSON.
- Save: POST /save with `{"marks": {"<fullName>": "yes|later|no"}}`. Server
  rewrites the CSV in place: header row keeps its original columns plus a
  trailing `mark` column (added if missing); each row's mark updated.
- Marks are keyed by `fullName` (unique per CSV).

## CSV write-back rules

- Preserve original column order; append `mark` as the last column.
- Only rewrite `mark` for rows whose fullName appears in the POST payload.
- Keep all existing cells byte-identical (no re-encoding drift).
- Write atomically: write to a temp file then `os.replace` over the original.
- If the CSV is read-only (e.g. in a git checkout before being pulled),
  the save fails with a clear message shown in the page, and existing data
  is left untouched.

## Out of scope

- No notes/comment field per row (may be a follow-up).
- One CSV at a time (no multi-file mode).
- No editing of repo data beyond the mark column.
- No remote/shared storage — marks live only in the local CSV (which is
  committed, so marks travel with the repo).

## Testing

Manual checks:

1. Open the sample `discovery/weekly/2026/08/idr_2026-08-31.csv`, set several
   marks, save, confirm the file gains a `mark` column with correct values and
   no other cells changed.
2. Reopen the same CSV — marks are preloaded.
3. Save again (idempotent); export ✅ list; verify clipboard content.
4. `weekly_report.py` on the marked CSV does not clobber the `mark` column
   (its header is `columns + ["description_zh"]`; a trailing `mark` column is
   preserved because the script only rewrites the leading columns).

## Files

- New: `scripts/csv_review.py` (the only code).
- Docs: this spec.
