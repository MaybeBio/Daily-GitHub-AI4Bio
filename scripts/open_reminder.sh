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
      # Keep the log verbatim (event headlines + their indented commit-detail lines);
      # drop only the ghresearcher "Fetching events for target(s):" preamble and blanks.
      content="$(grep -vE '^Fetching events for target\(s\):' "$path" | sed '/^[[:space:]]*$/d' || true)"
      body+="## $name"$'\n'
      body+="$content"$'\n'
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
