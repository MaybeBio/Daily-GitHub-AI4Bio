# Reminder Issues for Daily / Weekly Pipelines — Design

> 日期 / Date: 2026-09-07
> 状态 / Status: 已评审通过（brainstorming 决策后定稿）
> 仓库 / Repo: `MaybeBio/Daily-GitHub-AI4Bio`

## 1. 背景与目标 / Background & Goal

daily（`daily.yml`，每日 05:00）与 weekly（`weekly.yml`，周一 08:00）两条 Actions 管线自动采集并提交数据，但目前缺少一个「提醒我该去看产物了」的入口——用户只依赖手动进仓库拉取查看，容易漏。

目标：在每次采集运行完成后，**自动在本仓库开 1 个 reminder issue**，用作通知 + 留档 + 待办（看完手动关）：

- **daily issue**：正文直接贴当天三份日志（`users` / `orgs` / `received`），打开即是当日动态。
- **weekly issue**：CSV 太长不适合贴正文，只提醒**三个 topic 的 CSV 地址链接** + 一句 csv_review.py 引导语，提示去 review。

## 2. 决策记录 / Decisions (from brainstorming)

| 问题 | 决策 |
|---|---|
| daily issue 正文包含哪些日志 | `users` + `orgs` + `received` 三份全部拼接进 1 个 issue |
| issue 生命周期 | **open**（看完手动关），不打日期字面标签 |
| 标签方案 | 固定标签 `daily-reminder` / `weekly-reminder`（建一次），**日期放标题**（`[daily] YYYY-MM-DD` / `[weekly] YYYY-MM-DD`），避免 100 标签上限 |
| 指派 | 不指派（无 assignee） |
| weekly issue 内容 | 每个 topic 的 CSV 链接 + 一句 review 引导语；不加统计/计数 |
| 空日志处理 | **有内容才开**；无事件 / 无 CSV 时跳过，不开空 issue |
| 实现方式 | **方案 B：共享脚本** `scripts/open_reminder.sh`，两个 workflow 各调一行 |

## 3. 新增脚本 / New file: `scripts/open_reminder.sh`

Bash，可执行，`set -euo pipefail`。接口：

```bash
bash scripts/open_reminder.sh daily  2026-09-07               # 在 workflow 仓库根目录执行
bash scripts/open_reminder.sh weekly 2026-09-07
bash scripts/open_reminder.sh daily 2026-09-07 --dry-run       # 只把标题/正文打到 stdout，不调 API
```

### 3.1 通用步骤（两种 kind 共用）

1. **解析参数**：kind ∈ `daily | weekly`，date `YYYY-MM-DD`，可选 `--dry-run`；拆出 `$Y/$M/$D`。
2. **解析仓库**：`git remote get-url origin` → 提取 `owner/repo`（用于生成 blob 链接，仓库改名也不写死）。
3. **定位输入文件**（见 §4/§5）。
4. **内容门禁**（有内容才开）：没有真实可展示内容 → `exit 0`（静默，不开 issue）。
5. **构建正文**，带 60,000 字符保险（issue 上限 65,536）；超限则降级为「仅链接 + 说明」。
6. **去重守卫**：若已存在同 `label` + 同标题的 **open** issue → 跳过（防手动重跑产生重复）。
7. **确保标签存在**：`gh label create <name> --force`（幂等，upsert）。
8. **开 issue**：正文写入临时文件，`gh issue create --title <TITLE> --body-file <tmp> --label <name>`；保持 open，不指派。

## 4. daily 模式正文 / Daily mode body

输入文件：

- `monitor/users/$Y/$M/$D.txt`
- `monitor/orgs/$Y/$M/$D.txt`
- `monitor/received/$Y/$M/$D.txt`

处理规则：

- **去掉工具前缀行**：删除以 `Fetching events for target(s):` 开头的行（ghresearcher 内部元信息，列出 targets；删除≠总结，正文仍是原始日志逐行）。
- **「有内容」判定**：去掉前缀行后，三份文件合计存在 ≥1 行真实事件行（以 `YYYY-MM-DD HH:MM:SS` 时间戳开头的行）才算有内容；否则跳过。
- 正文布局（日志逐行保留原始 emoji/格式）：

  ```
  ## users
  …事件…
  ## orgs
  …事件…
  ## received
  …事件…
  ```

- 标题：`[daily] 2026-09-07`；标签：`daily-reminder`。

## 5. weekly 模式正文 / Weekly mode body

输入文件（按 topic 探测）：

- `discovery/weekly/$Y/$M/idr_$DATE.csv`
- `discovery/weekly/$Y/$M/protein_struct_ai_$DATE.csv`
- `discovery/weekly/$Y/$M/protein_dna_$DATE.csv`

处理规则：

- 每个**存在**的 CSV 输出一行 markdown 链接：
  `- [<topic> CSV](https://github.com/<owner>/<repo>/blob/main/discovery/weekly/$Y/$M/<topic>_$DATE.csv)`
  （GitHub 内联渲染 CSV 表格，可直接看到 ✅/❌ `mark` 列）
- 顶部一句引导语（文案定稿）：说明本周新周报 CSV、用 `csv_review.py` 逐条 review、本地 `python3 scripts/csv_review.py <csv路径> --port <port>`、标注后 commit & push 回。
- 不加计数 / 不加分析；某个 topic 失败无 CSV 就不列该项；全部失败 → 跳过 issue。
- 标题：`[weekly] 2026-09-07`；标签：`weekly-reminder`。

## 6. workflow 修改 / Workflow changes

`daily.yml` 与 `weekly.yml` 各自：

1. `permissions:` 增加 `issues: write`（现状只有 `contents: write`，无 issues 权限无法开 issue）。
2. 在既有的 `Commit and push` step 之后新增一个 step：
   - `daily.yml`: `bash scripts/open_reminder.sh daily "$(date +%F)"`
   - `weekly.yml`: `bash scripts/open_reminder.sh weekly "$(date +%F)"`

认证沿用已有 env `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}`，`gh` 自动读取。

## 7. 边界 / Boundaries & Notes

- **去重**：重复触发（同一天手动重跑）通过 §3.1-6 的 open issue 标题+标签守卫避免。
- **空跑**：`git diff` 无变化 / 无内容时不开 issue（daily 文件总是新写，几乎必然有内容；weekly 全 topic 失败才为空）。
- **正文长度**：真实日志量很小（KB 级），60,000 保险几乎不触发；降级逻辑仅作防御。
- **不改采集逻辑**：本设计只在提交后追加「开 issue」步骤，不动 ghresearcher 采集与文件产出结构。
- **标签为仓库级固定标签**：`daily-reminder`、`weekly-reminder` 首次由脚本 `--force` 创建。

## 8. 测试计划 / Test Plan

1. 本地对历史真实数据 `--dry-run`：
   - `bash scripts/open_reminder.sh daily 2026-09-07 --dry-run`
   - `bash scripts/open_reminder.sh weekly 2026-09-07 --dry-run`
   检查生成的标题/正文是否符合预期。
2. 空样例（找一个无事件的日期）`--dry-run` 验证跳过逻辑。
3. Live 验证：push 到 `main` 后从 Actions 页手动触发两个 workflow 各一次，确认各开出 1 个带标签的 open issue；再次触发确认不重复开。

## 9. 变更文件清单 / Files touched

| 文件 | 动作 |
|---|---|
| `scripts/open_reminder.sh` | 新增 |
| `.github/workflows/daily.yml` | 加 `issues: write` + 追加 step |
| `.github/workflows/weekly.yml` | 加 `issues: write` + 追加 step |
| `README.md`（可选） | 补充说明两管线会自动开 reminder issue |
| `docs/post-processing.md`（可选） | 同步「消化流程」中的提醒入口 |

## 10. Out of scope

- 采集内容 / 频率 / topic 本身不变。
- 不引入第三方通知（issue 仅作为 GitHub 内入口）。
- 不做 open issue 的自动关闭/清扫（由用户看完手动关）。
