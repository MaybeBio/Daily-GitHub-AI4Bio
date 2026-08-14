#!/usr/bin/env python3
"""Analyze ghresearcher `monitor` logs.

Reports:
  1. Top-starred repos (3 columns: repo | stars | starrers)
  2. Repos starred by 2+ distinct people (cross-signal)
  3. Most active repos by pushes / forks / issues / merged PRs

Usage:
    python3 scripts/analyze_logs.py monitor/users/*/*/*.txt
    python3 scripts/analyze_logs.py --top 15 monitor/orgs/*/*/*.txt
    python3 scripts/analyze_logs.py --top 10 monitor/users/2026/08/13.txt
"""
import argparse
import re
import sys
from collections import defaultdict

REPO = r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+"
STAR = re.compile(rf"⭐️\s+(\S+)\s+starred\s+({REPO})\s*$")
FORK = re.compile(rf"🍴\s+(\S+)\s+forked\s+({REPO})\s*$")
PUSH = re.compile(rf"🚀\s+(\S+)\s+pushed to\s+({REPO})\s*$")
ISSUE_CREATED = re.compile(rf"💬\s+(\S+)\s+created issue\b.*?\bin\s+({REPO})\s*$")
ISSUE_OPENED = re.compile(rf"🐛\s+(\S+)\s+(?:opened|closed)\s+issue\b.*?\bin\s+({REPO})(?=\s*:|$)")
PR_MERGED = re.compile(rf"🔀\s+(\S+)\s+merged\s+PR\b.*?\bin\s+({REPO})\s*$")


def analyze(paths):
    stars = defaultdict(set)
    forks = defaultdict(set)
    pushes = defaultdict(int)
    issues = defaultdict(int)
    prs = defaultdict(int)

    for path in paths:
        try:
            fh = open(path, encoding="utf-8")
        except OSError as e:
            print(f"skip {path}: {e}", file=sys.stderr)
            continue
        with fh:
            for line in fh:
                m = STAR.search(line)
                if m:
                    stars[m.group(2)].add(m.group(1))
                    continue
                m = FORK.search(line)
                if m:
                    forks[m.group(2)].add(m.group(1))
                    continue
                m = PUSH.search(line)
                if m:
                    pushes[m.group(2)] += 1
                    continue
                m = ISSUE_CREATED.search(line)
                if m:
                    issues[m.group(2)] += 1
                    continue
                m = ISSUE_OPENED.search(line)
                if m:
                    issues[m.group(2)] += 1
                    continue
                m = PR_MERGED.search(line)
                if m:
                    prs[m.group(2)] += 1
    return stars, forks, pushes, issues, prs


def counts(d):
    return {k: len(v) if isinstance(v, (set, list)) else v for k, v in d.items()}


def print_top(title, table, top):
    print(f"\n== {title} ==")
    for repo, n in sorted(table.items(), key=lambda kv: -kv[1])[:top]:
        print(f"  {repo:<42}{n:>6}")


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("files", nargs="+", help="log file(s) or glob")
    ap.add_argument("--top", type=int, default=15, help="max rows per section (default 15)")
    ap.add_argument("--min-stars", type=int, default=1, help="only repos starred at least N times")
    args = ap.parse_args()

    stars, forks, pushes, issues, prs = analyze(args.files)

    print("\n== Top starred repos (3-column) ==")
    print(f"{'repo':<42}{'stars':>7}  starrers")
    ranked = sorted(stars.items(), key=lambda kv: -len(kv[1]))
    shown = 0
    for repo, who in ranked:
        if len(who) < args.min_stars:
            continue
        print(f"{repo:<42}{len(who):>7}  {', '.join(sorted(who))}")
        shown += 1
        if shown >= args.top:
            break

    cross = [(r, w) for r, w in ranked if len(w) >= 2]
    if cross:
        print("\n== Repos starred by 2+ distinct people (cross-signal) ==")
        for repo, who in cross[: args.top]:
            print(f"  {repo}  ({len(who)}: {', '.join(sorted(who))})")

    print_top("Most pushed repos", counts(pushes), args.top)
    print_top("Most forked repos", counts(forks), args.top)
    print_top("Most issue activity", counts(issues), args.top)
    print_top("Most merged PRs", counts(prs), args.top)


if __name__ == "__main__":
    main()
