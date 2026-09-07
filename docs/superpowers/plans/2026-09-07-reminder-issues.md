# Reminder Issues for Daily/Weekly Pipelines — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After each daily/weekly Actions run commits its outputs, automatically open one reminder issue in the same repo (daily = inline user/org/received logs; weekly = topic CSV links + review guidance).

**Architecture:** One shared bash script `scripts/open_reminder.sh <daily|weekly> <YYYY-MM-DD> [--dry-run]` is called as the last step of both workflows. It locates that date's log/CSV files, decides "is there content?" (skip silently if none), builds the issue body, dedupes against an already-open matching issue, ensures the repo label exists, and opens the issue via `gh`. Workflows only add `issues: write` to `permissions:` and one invocation line each.

**Tech Stack:** Bash (`set -euo pipefail`), coreutils, GitHub CLI `gh` (preinstalled on `ubuntu-latest` runners), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-07-reminder-issues-design.md` — the plan argues from this spec; executors read both.

## Global Constraints

- Issue repo = the workflow's own `origin`; owner/repo derived from `git remote get-url origin` (never hardcode).
- Blob links use default branch `main`.
- Daily body = the three log files' **event lines only** (drop ghresearcher `Fetching events for target(s):` preamble lines), labeled `## users` / `## orgs` / `## received`. Empty day (0 event lines total) → exit 0, no issue.
- Daily title `[daily] YYYY-MM-DD`, label `daily-reminder`; weekly title `[weekly] YYYY-MM-DD`, label `weekly-reminder`.
- Weekly body copy (verbatim from spec §5): intro line `本周新周报 CSV 已生成，请用 csv_review.py 逐条 review（本地 git pull 拿文件后执行）：`, one `- [<topic> CSV](<blob url>)` bullet per existing CSV, then `本地命令：python3 scripts/csv_review.py discovery/weekly/<Y>/<M>/<topic>_<DATE>.csv --port 8000` and `逐行标 ✅/⏸/❌ → 保存标注 → git add discovery/weekly/ → git commit -m "review <topic> <DATE>" → git push`.
- Weekly issue: no counts/analysis; only bullets for CSVs that exist; none exist → exit 0, no issue.
- Body cap: if a daily body would exceed 60,000 chars, replace it with links to the three raw files + a note (issue limit 65,536).
- Issues stay **open**, no assignee. Fixed labels created idempotently (create-and-ignore-existing), never per-date labels.
- `--dry-run` prints `REPO:` / `TITLE:` / `LABEL:` / `--- body ---` then exits without any network call; skip cases print `SKIP: ...` and exit 0.

---

### Task 1: Create `scripts/open_reminder.sh`

**Files:**
- Create: `scripts/open_reminder.sh`

**Interfaces:**
- Consumes: repository files produced by the daily/weekly runs under `monitor/` and `discovery/`; an `origin` git remote; `gh` authenticated as `GH_TOKEN`.
- Produces: `open_reminder.sh daily|weekly <YYYY-MM-DD> [--dry-run]` — exit 0 (issue opened or intentionally skipped), exit 2 (usage error). Later tasks invoke this exact interface.

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
#
# Open a reminder issue in the origin repository after a daily monitor run or a
# weekly discovery run. See docs/superpowers/specs/2026-09-07-reminder-issues-design.md
#
# Usage:
#   open_reminder.sh <daily|weekly> <YYYY-MM-DD> [--dry-run]
set -euo pipefail

KIND="${1:-}"
DATE="${2:-}"
MODE="${3:-}"

if [[ -z "$KIND" || -z "$DATE" || ! "$KIND" =~ ^(daily|weekly)$ || ! "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "usage: $0 <daily|weekly> <YYYY-MM-DD> [--dry-run]" >&2
  exit 2
fi

DRY=0
[[ "$MODE" == "--dry-run" ]] && DRY=1

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

Y="${DATE:0:4}"
M="${DATE:5:2}"
D="${DATE:8:2}"

ORIGIN="$(git remote get-url origin 2>/dev/null || true)"
ORIGIN="${ORIGIN%.git}"
if [[ "$ORIGIN" == git@* ]]; then
  GH_REPO="${ORIGIN#*:}"
elif [[ "$ORIGIN" == http* ]]; then
  GH_REPO="${ORIGIN#*github.com/}"
else
  GH_REPO=""
fi
GH_REPO="${GH_REPO%/}"

DAILY_LABEL="daily-reminder"
DAILY_COLOR="1f6feb"
DAILY_DESC="Daily monitor reminder (auto-opened; read the log then close)"
WEEKLY_LABEL="weekly-reminder"
WEEKLY_COLOR="d4a72c"
WEEKLY_DESC="Weekly discovery reminder (auto-opened; review the topic CSVs then close)"

BLOB() { echo "https://github.com/$GH_REPO/blob/main/$1"; }

if [[ "$KIND" == "daily" ]]; then
  LABEL="$DAILY_LABEL"; COLOR="$DAILY_COLOR"; DESC="$DAILY_DESC"
  TITLE="[daily] $DATE"

  body=""
  total=0
  for name_path in \
      "users:monitor/users/$Y/$M/$D.txt" \
      "orgs:monitor/orgs/$Y/$M/$D.txt" \
      "received:monitor/received/$Y/$M/$D.txt"; do
    name="${name_path%%:*}"
    path="${name_path#*:}"
    [[ -f "$path" ]] || continue
    events="$(grep -E '^[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' "$path" || true)"
    n="$(printf '%s\n' "$events" | sed '/^$/d' | wc -l | tr -d ' ')"
    (( total += n )) || true
    if [[ "$n" -gt 0 ]]; then
      body+="## $name"$'\n'
      body+="$events"$'\n'
      body+=$'\n'
    fi
  done

  if [[ "$total" -eq 0 ]]; then
    (( DRY )) && echo "SKIP: no events for $DATE"
    exit 0
  fi

  if (( ${#body} > 60000 )); then
    body="当日日志过大，未内嵌正文，请直接查看原文件："$'\n'
    body+="- [users]($(BLOB "monitor/users/$Y/$M/$D.txt"))"$'\n'
    body+="- [orgs]($(BLOB "monitor/orgs/$Y/$M/$D.txt"))"$'\n'
    body+="- [received]($(BLOB "monitor/received/$Y/$M/$D.txt"))"$'\n'
  fi
else
  LABEL="$WEEKLY_LABEL"; COLOR="$WEEKLY_COLOR"; DESC="$WEEKLY_DESC"
  TITLE="[weekly] $DATE"

  links=()
  for t in idr protein_struct_ai protein_dna; do
    f="discovery/weekly/$Y/$M/${t}_$DATE.csv"
    [[ -f "$f" ]] && links+=("- [$t CSV]($(BLOB "$f"))")
  done

  if [[ "${#links[@]}" -eq 0 ]]; then
    (( DRY )) && echo "SKIP: no weekly CSV for $DATE"
    exit 0
  fi

  body="本周新周报 CSV 已生成，请用 csv_review.py 逐条 review（本地 git pull 拿文件后执行）："$'\n\n'
  for l in "${links[@]}"; do
    body+="$l"$'\n'
  done
  body+=$'\n'
  body+="本地命令：python3 scripts/csv_review.py discovery/weekly/$Y/$M/<topic>_$DATE.csv --port 8000"$'\n'
  body+="逐行标 ✅/⏸/❌ → 保存标注 → git add discovery/weekly/ → git commit -m \"review <topic> $DATE\" → git push"
fi

if (( DRY )); then
  echo "REPO: $GH_REPO"
  echo "TITLE: $TITLE"
  echo "LABEL: $LABEL"
  echo "--- body ---"
  printf '%s\n' "$body"
  exit 0
fi

# Dedupe: skip if an open issue with this label + exact title already exists.
existing="$(gh issue list --repo "$GH_REPO" --label "$LABEL" --state open --search "\"$TITLE\"" --json number --jq 'length' 2>/dev/null || true)"
if [[ -n "$existing" && "$existing" -gt 0 ]]; then
  echo "open_reminder: issue already open for $TITLE, skip"
  exit 0
fi

# Ensure the repo-level label exists (idempotent; ignore "already exists" error).
gh label create "$LABEL" --repo "$GH_REPO" --description "$DESC" --color "$COLOR" >/dev/null 2>&1 || true

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
printf '%s\n' "$body" > "$tmp"
gh issue create --repo "$GH_REPO" --title "$TITLE" --body-file "$tmp" --label "$LABEL"
```

- [ ] **Step 2: Syntax check + chmod**

Run: `chmod +x scripts/open_reminder.sh && bash -n scripts/open_reminder.sh`
Expected: no output, exit 0 (script parses).

- [ ] **Step 3: Usage/arg guards**

Run: `bash scripts/open_reminder.sh; echo "exit=$?"`
Expected: usage line on stderr, `exit=2`.

Run: `bash scripts/open_reminder.sh daily 2026-9-7; echo "exit=$?"`
Expected: usage line on stderr, `exit=2` (date must be `YYYY-MM-DD`).

- [ ] **Step 4: Daily dry-run on a real day**

Run: `bash scripts/open_reminder.sh daily 2026-09-07 --dry-run`
Expected: `REPO: MaybeBio/Daily-GitHub-AI4Bio`, `TITLE: [daily] 2026-09-07`, `LABEL: daily-reminder`, body containing `## users`, `## orgs`, `## received`, and event lines starting with `2026-09-` / `2026-08-` timestamps (logs may include late events from the prior day — that is the tool's own window, keep as-is). No `SKIP:`.

- [ ] **Step 5: Weekly dry-run on a real day**

Run: `bash scripts/open_reminder.sh weekly 2026-09-07 --dry-run`
Expected: `REPO: MaybeBio/Daily-GitHub-AI4Bio`, `TITLE: [weekly] 2026-09-07`, `LABEL: weekly-reminder`, body with the intro line, exactly three bullets:
- `- [idr CSV](https://github.com/MaybeBio/Daily-GitHub-AI4Bio/blob/main/discovery/weekly/2026/09/idr_2026-09-07.csv)`
- `- [protein_struct_ai CSV](https://github.com/MaybeBio/Daily-GitHub-AI4Bio/blob/main/discovery/weekly/2026/09/protein_struct_ai_2026-09-07.csv)`
- `- [protein_dna CSV](https://github.com/MaybeBio/Daily-GitHub-AI4Bio/blob/main/discovery/weekly/2026/09/protein_dna_2026-09-07.csv)`

followed by the `本地命令：python3 scripts/csv_review.py discovery/weekly/2026/09/<topic>_2026-09-07.csv --port 8000` and `逐行标 …` lines. No `SKIP:`.

- [ ] **Step 6: Empty-date skip for both kinds**

Run: `bash scripts/open_reminder.sh daily 2099-01-01 --dry-run; echo "exit=$?"`
Expected: `SKIP: no events for 2099-01-01`, `exit=0`.

Run: `bash scripts/open_reminder.sh weekly 2099-01-01 --dry-run; echo "exit=$?"`
Expected: `SKIP: no weekly CSV for 2099-01-01`, `exit=0`.

- [ ] **Step 7: Commit**

```bash
git add scripts/open_reminder.sh
git commit -m "feat: add open_reminder.sh for auto reminder issues"
```

---

### Task 2: Wire the reminder into both workflows

**Files:**
- Modify: `.github/workflows/daily.yml` (add `issues: write`; append a step after `Commit and push`)
- Modify: `.github/workflows/weekly.yml` (same two edits)

**Interfaces:**
- Consumes: `scripts/open_reminder.sh` from Task 1.
- Produces: both workflows now run the reminder as their final step on every trigger. Nothing else consumes this.

- [ ] **Step 1: daily.yml — add `issues: write`**

Current block (lines 11-13):
```yaml
permissions:
  contents: write
```
Change to:
```yaml
permissions:
  contents: write
  issues: write
```

- [ ] **Step 2: daily.yml — append the reminder step**

Append at the end of the `collect` job, after the `Commit and push` step (same indentation, 6 spaces under `steps:`):
```yaml
      - name: Open daily reminder issue
        run: |
          bash scripts/open_reminder.sh daily "$(date +%F)"
```

- [ ] **Step 3: weekly.yml — add `issues: write`**

Current block (lines 11-13):
```yaml
permissions:
  contents: write
```
Change to:
```yaml
permissions:
  contents: write
  issues: write
```

- [ ] **Step 4: weekly.yml — append the reminder step**

Append at the end of the `report` job, after the `Commit and push` step:
```yaml
      - name: Open weekly reminder issue
        run: |
          bash scripts/open_reminder.sh weekly "$(date +%F)"
```

- [ ] **Step 5: Validate YAML parses**

Run: `python3 -c "import yaml,sys; [yaml.safe_load(open(p)) for p in ['.github/workflows/daily.yml','.github/workflows/weekly.yml']]; print('yaml ok')"`

If `PyYAML` is not installed locally, fall back to: `python3 -m json.tool` is not valid for YAML — instead re-read both files and eyeball indentation (6 spaces for step list items, 8 for `run:` body), then note in the commit that a workflow-syntax check will run on push.
Expected: prints `yaml ok`.

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/daily.yml .github/workflows/weekly.yml
git commit -m "ci: open reminder issues after daily & weekly runs"
```

---

### Task 3: Document the reminder entry point

**Files:**
- Modify: `README.md` (Automation section, lines ~118-123)
- Modify: `docs/post-processing.md` (section 1, both language halves)

**Interfaces:**
- Consumes: nothing new.
- Produces: docs that describe the new auto-opened issues, so the manual-consumption flow stays accurate.

- [ ] **Step 1: README — note auto reminder issues**

In the `## Automation` bullet list (`.github/workflows/` block), extend each workflow's line to mention it now also opens a labeled reminder issue, e.g.:
```markdown
- **daily-follow** (every day, 05:00 Beijing time): collects the previous day's activity into `monitor/users|orgs|received/`, commits and pushes, then opens a `daily-reminder` issue whose body is the day's logs (label + open, read then close).
- **weekly-discovery** (every Monday, 08:00 Beijing time): snapshots the topic search into `discovery/weekly/`, commits and pushes, then opens a `weekly-reminder` issue linking the week's topic CSVs.
```

- [ ] **Step 2: post-processing.md — mention the reminder as an entry point**

In the section-1 input tables (one Chinese, one English), add a one-line note under each pipeline that the run auto-opens the corresponding reminder issue (`daily-reminder` / `weekly-reminder`) as the entry point to pull the outputs.

- [ ] **Step 3: Commit**

```bash
git add README.md docs/post-processing.md
git commit -m "docs: describe auto reminder issues entry point"
```

---

## Self-Review

**1. Spec coverage:**
- §4 daily body (users/orgs/received, strip preamble, ≥1 event gate, 60k fallback) → Task 1 daily branch. ✓
- §5 weekly body (link bullets only + exact guidance copy, per-existing-CSV, none→skip) → Task 1 weekly branch. ✓
- §3.1 generic steps (repo derive, content gate, dedupe, label ensure, open) → Task 1 live path. ✓
- §6 workflow changes (`issues: write` + one appended step each) → Task 2. ✓
- §9 optional docs → Task 3. ✓
- Spec §8 test plan (dry-run on real days + skip case) → Task 1 Steps 4-6; live trigger verification left to the user after push (documented in spec §8 step 3). ✓

**2. Placeholder scan:** No TBD/TODO. Weekly copy uses `<topic>`/`<DATE>` as literal template placeholders matching the spec's agreed copy, not unresolved code placeholders. Date examples are concrete (`2026-09-07`). ✓

**3. Type consistency:** Interface `open_reminder.sh daily|weekly <YYYY-MM-DD> [--dry-run]` is used identically in Task 1 Step 1 and Task 2 invocations. Labels/titles match spec exactly. ✓

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-07-reminder-issues.md`. Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
