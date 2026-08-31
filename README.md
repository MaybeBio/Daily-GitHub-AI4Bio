# P-S-A — Community Activity Archive

A living record of what's moving in the world where **structural biology meets machine learning** 

## About

Protein structure prediction, representation learning, generative protein design, conformational dynamics and sampling, and AI-driven structural biology.

The protein-AI space evolves fast, and the signal is scattered across many individual repos, teams, and people. This repository aggregates that movement into a single, human-readable archive.

It maintains a **hand-curated watchlist** of influential accounts — prominent researchers, active labs, and key open-source organizations working at the intersection of P-S-A (Protein-Struct‑AI). The public GitHub activity : who shipped what, when, and with whom.

The goal is simple: a high-signal, at-a-glance view of where the community is heading.

## How it works

- **ghresearcher** — a small companion CLI designed by me. It runs locally and, since this repo is hooked up to [GitHub Actions](.github/workflows/), refreshes automatically on a schedule.
- Every run is written out as a **plain-text `.txt` activity log**, organized by date, easy to read, search, or diff.
- A weekly **discovery** pass searches the topic of interest (YOUR-TOPIC) and snapshots ranked repositories, so promising new code doesn't slip by.
- The logs accumulate into a durable timeline, useful both for staying current, for retrospective analysis, and as input to the [analysis scripts](scripts/).

## Repository layout

```
.
├── README.md                       # this file
├── monitor/                        # daily activity tracking (via `monitor`)
│   ├── lists/                      #   the curated watchlist (one target per line)
│   │   ├── users.txt               #     full list — the whole community
│   │   ├── users_core.txt          #     core subset, drives the `received` feed only
│   │   └── orgs.txt                #     labs, universities & open-source orgs
│   ├── users/YYYY/MM/DD.txt        #   daily activity of followed users
│   ├── orgs/YYYY/MM/DD.txt         #   daily activity of followed orgs / labs
│   └── received/YYYY/MM/DD.txt     #   daily feed of what core users watch
├── discovery/                      # weekly topic discovery (via `search`)
│   ├── queries/topic.yaml          #   topic search template (edit query keywords)
│   └── weekly/YYYY/YYYY-MM-DD.txt  #   weekly ranked repo snapshots
├── scripts/                        # local analysis utilities
│   └── analyze_logs.py             #   turn activity logs into frequency tables
└── .github/workflows/
    ├── daily.yml                   #   daily automation, 05:00 Beijing time
    └── weekly.yml                  #   weekly discovery, Monday 08:00 Beijing time
```

## Watchlist design (two layers)

The lists are split into two scopes on purpose:

| Scope | List | Used by | Signal |
|---|---|---|---|
| **Broad** | `users.txt` · `orgs.txt` | `monitor/users` · `monitor/orgs` | the whole P-S-A community — what is everyone doing |
| **Narrow** | `users_core.txt` | `monitor/received` only | people whose work is closely related to your own topic — what are they looking at |

Constraints:

- **`users_core.txt` must be a strict subset of `users.txt`.** Everyone in the core list is already monitored through the broad pass; the core list only narrows the (noisier) `received` feed.
- The `received` feed grows with each entry, so keep the core list small (≈10 people) and focused on researchers working near your own topic.

## Adding targets

Edit the files under `monitor/lists/`, one target per line:

```bash
# e.g. monitor/lists/users.txt
someoneinspiring
anotherlabmember

# e.g. monitor/lists/users_core.txt  (must be a subset of users.txt)
ATrueResearcher

# e.g. monitor/lists/orgs.txt
someorg
anotherorg
```

The daily run picks up new targets automatically: `monitor/users|orgs` runs on the full lists; `monitor/received` runs on `users_core.txt` only.

## Notes on the data (`--limit` & GitHub's 300 cap)

- `ghresearcher monitor --limit` is **per target** (per user / per org), default 30. Raising it pulls more events for each target.
- GitHub's Events API returns at most **300 events per target** (30 per page × 10 pages). Setting `--limit` above 300 has no effect; this is a GitHub-side ceiling, not a tool setting.
- `--since` / `--until` filter client-side, but only within those most-recent 300 events — a very active account can overflow the window.
- `--expand-commits` issues one extra API call per push event (the Events API omits commit messages), so it meaningfully increases API usage.
- API rate limits: the automatic `GITHUB_TOKEN` allows ~1,000 requests/hour per repository; a fine-grained PAT raises this to 5,000. The daily run currently stays well within the token's limit.

## Analyzing the logs

[`scripts/analyze_logs.py`](scripts/analyze_logs.py) parses the `.txt` logs and reports:

- **Top-starred repos** — a 3-column table: `repo | stars | starrers`
- **Cross-signal** — repos starred by ≥2 distinct people from your point-of-view
- **Most active repos** — by pushes / forks / issues / merged PRs

```bash
python3 scripts/analyze_logs.py monitor/users/*/*/*/*.txt            # across all days
python3 scripts/analyze_logs.py --top 15 monitor/orgs/*/*/*/*.txt
python3 scripts/analyze_logs.py --top 10 monitor/users/2026/08/13.txt  # single day
```

Note: GitHub exposes no public "repo follow" event — `star` is the public proxy for attention, so frequency tables are star-based.

## Tuning discovery

The weekly snapshot reads `discovery/queries/topic.yaml`. Change the topic keywords there:

```yaml
query: "YOUR-TOPIC"
language: Python
limit: 20
sort: stars
order: desc
```

You can adjust `limit`, `sort`, `stars`, or add `topic` / other qualifiers. Repos that look interesting can be explored further with `ghresearcher parse`.

## Automation

Two [GitHub Actions](.github/workflows/) workflows run on the GitHub-hosted runner, using the built-in `gh` CLI and the automatic `GITHUB_TOKEN` (no personal login needed):

- **daily-follow** (every day, 05:00 Beijing time): collects the previous day's activity into `monitor/users|orgs|received/`, then commits and pushes.
- **weekly-discovery** (every Monday, 08:00 Beijing time): snapshots the topic search into `discovery/weekly/`, then commits and pushes.

You can trigger either manually via the **Actions** tab → the workflow → **Run workflow**.

## Notes

### Trigger & schedule

- Both workflows are triggered by an **external timer (Cron-job.org)** via `workflow_dispatch` — GitHub's built-in `schedule` does not fire on this repo.
- **daily-follow**: every day at **05:00** (Beijing time).
- **weekly-discovery**: tentatively every Monday at **08:00** (Beijing time); the three topics (`idr` / `protein_struct_ai` / `protein_dna`) run together in one pass, and a **failure in one topic only warns without interrupting the others** (successful topics still commit their CSVs).

### Consuming the results

- **daily (monitor logs)**: meant for manual review; the repo can be collected into star collections and fed into our **template/ontology skill** for further processing.
- **weekly (CSV)**: each run produces `discovery/weekly/YYYY/MM/<topic>_YYYY-MM-DD.csv`; we can pull it down and compile/add a new column per repo, checking and digesting each repo one by one like ✅/❌.

The full post-processing workflow — screening, starring, studying, and feeding the results into our skill, for both pipelines — is documented in [docs/post-processing.md](docs/post-processing.md) (bilingual).

## Why this exists

- **Stay current** — a single place to see what the people driving the field are building.
- **Spot trends** — trace collaborations and shipping cadence over time to notice emerging directions early.
- **Open research log** — a transparent, reproducible trail of community activity, useful for retrospective analysis and personal research.

