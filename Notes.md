# GitHub Actions 定时触发指南 / GitHub Actions Scheduled Trigger Guide

> 本文档基于真实项目 MaybeBio/Gh-PSA-Follow 的实践整理。
> This document is compiled from real-world practice on the repo `MaybeBio/Gh-PSA-Follow`.

---

## 0. 背景 / Background

GitHub Actions 的 `schedule` 触发器是 **best-effort（尽力而为）** 的：
- 定时由 GitHub 服务器统一调度，**可能延迟数分钟，甚至完全不触发**（本项目实测：cron 注册满一天 + `*/5` 测试 26 分钟/5 个整点均无触发）。
- 因此提供两套方案：**方案 A（GitHub 自带 schedule）** 适合能容忍延迟/偶尔丢失的场景；**方案 B（外部定时）** 适合需要稳定准点执行的场景。

GitHub Actions `schedule` is **best-effort**:
- Runs are scheduled server-side and **can be delayed by minutes, or never fire at all** (verified in this project: a cron registered for a full day plus a `*/5` test spanning 26 min / 5 boundaries produced zero runs).
- Hence two approaches: **Method A (native GitHub schedule)** for delay-tolerant use; **Method B (external cron)** for reliable, on-time execution.

---

## 1. 方法一：GitHub 自带 schedule / Method 1: Native GitHub `schedule`

### 1.1 原理 / How it works

```yaml
on:
  schedule:
    - cron: '<minute> <hour> <day-of-month> <month> <day-of-week>'
```

- Cron 采用**标准 5 段式**（分 时 日 月 周）。Cron uses the standard 5-field format (minute hour day month weekday).
- **时区固定为 UTC**。Cron 由 GitHub 按 UTC 评估，**与 workflow 内的 `TZ` 环境变量无关**（`TZ` 只影响 job 内 `date` 命令的输出）。
  Timezone is **always UTC**. The `TZ` env var in the workflow only affects `date` output inside the job, NOT the schedule.

### 1.2 北京时间 ↔ UTC 换算 / Beijing time ↔ UTC conversion

| 北京时间 Beijing | UTC | Cron |
|---|---|---|
| 每天 08:00 | 00:00 | `0 0 * * *` |
| 每天 08:10 | 00:10 | `10 0 * * *` |
| 每天 08:42 | 00:42 | `42 0 * * *` |
| 每周一 08:00 | Mon 00:00 | `0 0 * * 1` |
| 每周一 08:10 | Mon 00:10 | `10 0 * * 1` |

> 换算公式：北京时间 = UTC + 8 小时。Conversion: Beijing = UTC + 8h.

### 1.3 完整示例 / Full example

```yaml
name: daily-follow

on:
  schedule:
    # 00:00 UTC = 08:00 北京时间
    - cron: '0 0 * * *'
  workflow_dispatch:   # 保留手动触发，便于测试 / keep manual trigger for testing

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: echo "scheduled job"
```

### 1.4 已知坑 / Known gotchas（本项目实测总结 / learned the hard way）

1. **只在默认分支生效**：schedule 只读取默认分支（如 `main`）上的 workflow 文件。
   Only fires based on the workflow file on the **default branch**.
2. **必须处于 active 状态**：仓库 Actions 未禁用、单个 workflow 未关闭。可查：
   `GET /repos/{owner}/{repo}/actions/workflows` 看 `state` 是否为 `active`。
   Workflow must be `active`; check via the workflows API.
3. **不保证触发**：这是本项目遇到的核心问题——配置全对也不触发，属 GitHub 侧已知不可靠行为。
   **No guarantee of firing** — this was the core issue in this project: fully correct config still produced no runs. This is a known GitHub-side unreliability.
4. **60 天无仓库活动会暂停**：仓库连续 60 天无 push/PR 等，GitHub 会自动暂停 schedule。
   Scheduled workflows pause after **60 days of repo inactivity**.
5. **避开整点/半点（缓解措施）**：社区经验是 `:00`/`:30` 是调度高峰，错峰（如 `:10`、`:13`、`:42`）可减少延迟。属经验性建议，非官方保证。
   Avoid `:00`/`:30` (community tip): those minutes are peak load; off-peak minutes may reduce delay. Anecdotal, not guaranteed.
6. **修改 cron 后当天可能不触发**：首次注册/更新后第一个周期常被跳过，从下一个周期开始生效（社区普遍报告）。
   The first cycle after adding/editing a cron is often skipped; it starts firing from the next cycle (widely reported).

---

## 2. 方法二：外部定时触发 / Method 2: External cron → `workflow_dispatch`

> 推荐：当 schedule 不触发或需要准点执行时使用。
> Recommended when native schedule fails or when on-time execution is required.

### 2.1 整体流程 / Overall flow

```
Cron-job.org (外部定时)  ──POST──▶  GitHub REST API  ──▶  触发 workflow_dispatch  ──▶  GitHub Actions 运行
```

### 2.2 修改 workflow / Modify the workflow

**去掉 `schedule`，只保留 `workflow_dispatch`**（避免未来双触发 / remove `schedule` to prevent double-triggering）：

```yaml
name: daily-follow

# 由外部定时器触发（Cron-job.org），替代 GitHub schedule
# Triggered by external cron (Cron-job.org), replacing GitHub schedule
on:
  workflow_dispatch:

jobs:
  collect:
    runs-on: ubuntu-latest
    steps:
      - run: echo "triggered by external cron"
```

### 2.3 创建 PAT（访问令牌）/ Create a PAT

**细粒度 token（推荐）/ Fine-grained token (recommended):**
1. GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token
2. **Repository access**: Only select repositories → 勾选目标仓库
3. **Permissions → Repository permissions → Actions → Read and write**（关键，必须有 / required）
4. 保存后复制（只显示一次）

**经典 token / Classic token（备选）:**
- 需勾选 `workflow` scope（同时要求 `repo`）。
- Requires the `workflow` scope (which also requires `repo`).

> 触发器需要写入权限。触发 API 必须用 PAT（内置 `GITHUB_TOKEN` 不能触发）。
> Dispatching requires write permission; the built-in `GITHUB_TOKEN` cannot trigger dispatch — a PAT is required.

### 2.4 用 curl 验证 / Verify with curl

```bash
curl -X POST \
  -H "Authorization: Bearer <你的PAT / your PAT>" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  -H "Content-Type: application/json" \
  -d '{"ref":"main"}' \
  https://api.github.com/repos/MaybeBio/Gh-PSA-Follow/actions/workflows/daily.yml/dispatches
```

- **无输出 = 204 成功**（GitHub 侧立即出现一次 `workflow_dispatch` 运行）。
  Empty output = 204 success; a run appears in GitHub Actions immediately.
- 带 `"Authorization: Bearer <token>"` 头即可，无需其它认证。
- URL 中的 `daily.yml` 是 workflow 文件名；换成 `weekly.yml` 即可触发另一个 workflow。
  The `daily.yml` in the URL is the workflow filename; swap it to trigger another workflow.

### 2.5 在 Cron-job.org 创建 job / Create the job on Cron-job.org

1. 注册 https://cron-job.org（免费 / free）→ Sign Up → 邮箱验证
2. 首页 **Create cron job**，逐项填写：

| 字段 Field | 值 Value |
|---|---|
| Title | `Gh-PSA-Follow daily` |
| URL | `https://api.github.com/repos/MaybeBio/Gh-PSA-Follow/actions/workflows/daily.yml/dispatches` |
| Time zone | **`Asia/Shanghai`**（必须选对 / must be correct） |
| Execution schedule | 每天 `08:10`（Cron 表达式：`10 8 * * *`） |
| Request method | **`POST`**（默认是 GET，必须改 / default GET, must change） |
| Headers | 3 行：<br>`Authorization` = `Bearer 你的PAT`<br>`Accept` = `application/vnd.github+json`<br>`Content-Type` = `application/json` |
| Request body | `{"ref":"main"}` |

3. 保存后点 **Run now** 验证 → cron-job.org 显示 `204 No Content` 即成功。

**注意 / Important:**
- **`Content-Type: application/json` 是必须的**。缺失时 cron-job.org 不会以 JSON 格式发送 body，GitHub 报 **422**。
  `Content-Type: application/json` is **mandatory**; without it the body isn't sent as JSON and GitHub returns **422**.
- **`Request method` 必须是 POST**，否则报 404。
  Request method must be **POST**, otherwise 404.
- **时区必须选 Asia/Shanghai**，否则执行时间按 cron-job.org 服务器时区计算。
  Timezone must be set to Asia/Shanghai, or the time is computed in the server's timezone.
- 免费版最小间隔通常为 10 分钟（本项目仅需每天一次，无影响）。
  The free plan's minimum interval is typically 10 minutes (irrelevant for daily runs).
- **weekly job**：建第二个 job，URL 换成 `weekly.yml`，时间每周一 `08:10`（`10 8 * * 1`），其余相同。
  For a weekly job: create a second job, URL = `weekly.yml`, Monday `08:10` (`10 8 * * 1`), everything else identical.

### 2.6 错误码对照 / HTTP error reference

| 状态码 Status | 含义 Meaning | 处理 Fix |
|---|---|---|
| **204** | 成功（空响应） | ✅ 触发成功，去 GitHub Actions 看运行 |
| **401** | Authorization 头缺失/错误（如少 `Bearer ` 前缀） | 检查 Header 值格式 |
| **403** | token 权限不足（缺 Actions: Read and write / 仓库未授权） | 检查 token 权限 |
| **404** | URL 错误，或方法不是 POST（GET 访问 dispatch 地址会 404） | 核对 URL，方法改 POST |
| **422** | body 未按 JSON 解析（最常见：缺 `Content-Type: application/json`，或 body 为空/格式错） | 加 Content-Type 头，核对 body=`{"ref":"main"}` |

> 浏览器直接打开 dispatch 地址返回 404 是**正常现象**——该接口只接受 POST。浏览器用 GET 访问自然 404，不影响外部定时。
> Opening the dispatch URL in a browser returns 404 **by design** — the endpoint only accepts POST. This does not affect the external cron.

### 2.7 安全 / Security

- **PAT 会明文存储在 cron-job.org 的 header 里**：建议只授权单个仓库、设较短有效期。
  The PAT is stored in plaintext in cron-job.org's headers: authorize only the target repo and use a short expiry.
- **token 一旦在聊天/日志中暴露，立即 revoke 重建**，新 token 只粘贴到 cron-job.org。
  If a token is ever shared in chat/logs, revoke and recreate it immediately; paste the new one only into cron-job.org.
- 触发后可在 GitHub → Settings → Security → Active sessions / Tokens 审计使用记录。

---

## 3. 快速验收清单 / Quick acceptance checklist

- [ ] workflow 改为 `on: workflow_dispatch`（无 `schedule`）并推送到默认分支 main
      Workflow changed to `on: workflow_dispatch` (no `schedule`) and pushed to default branch `main`.
- [ ] PAT 已创建且具有 Actions: Read and write 权限
      PAT created with Actions: Read and write.
- [ ] `curl -X POST .../dispatches -d '{"ref":"main"}'` 返回 204（空输出）
      curl POST returns 204 (empty output).
- [ ] Cron-job.org job：URL 正确、时区 Asia/Shanghai、方法 POST、3 个 headers、body `{"ref":"main"}`
      Cron-job.org job: correct URL, Asia/Shanghai timezone, POST method, 3 headers, body `{"ref":"main"}`.
- [ ] Run now 后 cron-job.org 显示 204，GitHub Actions 出现成功运行
      After Run now: cron-job.org shows 204 and a successful run appears in GitHub Actions.
- [ ] 到期后检查 cron-job.org 的 **Last execution**（应为 200/204）与 GitHub Actions 运行
      At fire time, check **Last execution** on cron-job.org (should be 200/204) and the GitHub Actions run.

---

## 4. 本项目当前状态 / Current state of this project

- `MaybeBio/Gh-PSA-Follow` 的 GitHub schedule **确认不生效**（详见记忆/排查记录）。
  The GitHub `schedule` on this repo was **confirmed non-functional**.
- 两个 workflow（`daily-follow` / `weekly-discovery`）已切换为 `workflow_dispatch`，由 Cron-job.org 外部触发。
  Both workflows switched to `workflow_dispatch`, triggered externally via Cron-job.org.
- 输出文件按 `YYYY/MM/DD.txt` 划分：
  Outputs are organized as `YYYY/MM/DD.txt`:
  - daily: `monitor/users/2026/08/15.txt`、`monitor/orgs/...`、`monitor/received/...`
  - weekly: `discovery/weekly/2026/08/15.txt`
