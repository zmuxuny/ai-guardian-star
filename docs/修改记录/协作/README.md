# AI 协作区（Codex / DeepSeek）

> 目标：让两个 AI 在不重复读全库、不互相覆盖的前提下，知道对方做了什么、改了什么、下一步做什么。
> 最后更新：2026-10-25

## 0. 一句话规则

**代码看分支和 SHA；状态只看最新一条；每条不超过 40 行；不把源码贴进记录。**

GitHub 只是运输层，不产生 token；产生 token 的是“读”。所以协作区必须保持“薄”：它是指路牌，不是代码仓库的副本。

## 1. 文件分工

| 文件 | 维护者 | 用途 |
|---|---|---|
| `README.md` | 双方只读 | 协作规则，稳定，不常改 |
| `TASKS.md` | 双方 | 任务、负责人、分支/提交、状态 |
| `STATUS-codex.md` | Codex | Codex 每次会话的状态，最新在上 |
| `STATUS-deepseek.md` | DeepSeek | DeepSeek 每次会话的状态，最新在上 |
| `TEMPLATE.md` | 双方只读 | 单次记录模板 |
| `archive/YYYY-MM/` | 双方 | 旧记录归档，开工不读 |

规则：

- **只改自己的 `STATUS-*.md`**，不要改对方的。
- `TASKS.md` 只改自己负责的行；新增任务追加一行，任务 ID 唯一。
- 不要在本目录放源码、HAP、视频、数据库、日志原文、密钥、手机号、人脸图。
- 需要附件时放 `archive/YYYY-MM/attachments/`，且只放必要的截图或小补丁。

## 2. 开工顺序（每次约 1 分钟）

```powershell
git fetch --all --prune
git status --short --branch
git log --oneline -8
```

然后按顺序只读：

1. `TASKS.md`；
2. 对方 `STATUS` 的**最上面一条**（顶部两行 + “未验证/下一步”）；
3. 自己 `STATUS` 的**最上面一条**。

需要细节时再定向 `git show` / `git diff`，不要一上来全库搜索或整文件通读。读完在 `TASKS.md` 认领，再动手。

## 3. 收工顺序

1. 提交代码：已验证的进 `zy`；未验证的进 `wip/<agent>-<date>`；**当前阶段只做本地提交，由用户统一 push**。
2. 在 `STATUS-<agent>.md` 顶部追加一条（不超过 40 行，格式见 `TEMPLATE.md`）。
3. 更新 `TASKS.md` 的状态和分支/提交。
4. 只提交协作目录：

```powershell
git add docs/修改记录/协作
git commit -m "记录：<一句话说明>"
```

5. 不执行 `git add -A`；不要把对方工作区里的未提交代码带进自己的提交。

## 4. 分支与工作区

| 内容 | 放哪里 | 规则 |
|---|---|---|
| 已验证代码 | `zy` | 跑过测试/验收才合并 |
| 未验证代码 | `wip/<agent>-<date>` | 需要对方接手时 push；可直接看 `git diff` |
| 协作记录 | `zy` 的 `docs/修改记录/协作/` | 只提交文档；提交前 `git pull --rebase` |
| 临时实验 | 各自独立 worktree | 不 push，不交叉提交 |
| 截图/补丁 | `archive/YYYY-MM/attachments/` | 不放密钥、大文件、个人数据 |

- 两个 Agent **不要共用同一个工作区**；当前 `zy` 工作区还有未提交改动，尤其不能用 `git add -A`。
- 未验证代码不要直接改 `zy`。如果确实需要临时放在 `zy`，必须在 `TASKS.md` 标“未验证”，并在合并前改走 WIP 分支。
- 提交信息末尾加一行 `AI-Agent: codex` 或 `AI-Agent: deepseek`，这样 `git log` 本身就是一份谁做了什么的索引。

## 5. Token 预算

- 每条 `STATUS` 不超过 40 行；顶部两行必须能独立读懂。
- 每个 `STATUS` 只保留最近 3 条；更早的 `git mv` 到 `archive/YYYY-MM/`。
- 代码只写 `path:line` + 提交 SHA，不贴全文；对方需要时自己 `git show`。
- 一个信息只写一次：commit message、`TASKS`、`STATUS` 互相引用，不重复长段落。
- 不默认读 `archive/`；只有追历史决策时才读。

量级参考：读一页状态约 600–1000 tokens；全读 3–5 个大文件约 3–6 万 tokens。协作区的价值是**用一页纸代替重新发现**，不是把所有东西都存下来。

## 6. 命名与归档

- 归档文件名：`YYYY-MM-DD-<agent>-<主题>.md`，例如 `2026-10-25-codex-事件录像按需下载.md`。
- `STATUS` 条目标题：`## YYYY-MM-DD HH:mm · <agent> · <任务ID> · <状态>`。
- 任务 ID：`T-YYYYMMDD-NN`，例如 `T-20261025-01`。
- 状态只用：`待认领` / `进行中` / `待验证` / `已完成` / `阻塞`。

## 7. 安全

- 仓库是公开的：不写密钥、token、短信码、管理密码、签名材料、手机号、人脸原图、日志原文。
- 不提交 HAP/APP、模型、视频、数据库、`local.properties`、`.env`。
- 需要引用凭据时只写“见设备上的私有配置”，不写值。

## 8. 冲突处理

- 同一文件被两人认领：后到者先停，发消息或等对方完成；不要并行改同一文件。
- `TASKS.md` 冲突：保留双方行，按 ID 排序。
- 代码冲突：以 `zy` 为基线 rebase；不要 force push 共享分支。
- 记录冲突：各自文件不会冲突；如果 `TASKS.md` 冲突，保留双方任务再合并。

## 9. Codex 直接调用 DeepSeek（headless）

DSH 自带 `headless` CLI，Codex 可以启动一个**一次性**的 DeepSeek 会话。项目提供包装脚本 `tools/dsh-headless.ps1`：

```powershell
# 只读分析/审核（默认）
.\tools\dsh-headless.ps1 -Task "读取 TASKS.md 和 STATUS-deepseek.md，汇报待办；不要改文件。"

# 允许修改当前工作区
.\tools\dsh-headless.ps1 -Mode workspace-write -TaskFile .\task.md

# 机器可读
.\tools\dsh-headless.ps1 -Json -Task "..."

# 续接已存在的会话
.\tools\dsh-headless.ps1 -SessionId <id> -Task "继续..."

# 只预演，不调用模型
.\tools\dsh-headless.ps1 -DryRun -Task "smoke test"
```

规则：

- 默认 `read-only`；要改代码显式 `-Mode workspace-write`；`danger-full-access` 必须再加 `-AllowDangerFullAccess`。
- `-Workdir` 默认当前目录，并成为 DSH 的 workspaceRoot；要让它改哪个 worktree，就先切到那里，或传 `-Workdir`。
- 这是**新的 headless 会话**，不是当前 GUI 对话；上下文靠 `AGENTS.md`、协作区和 git 传递。
- DSH 只做本地提交，不 push；审核和 push 仍由 Codex 做。
- 任务用文件或短句，不要把整段聊天记录塞进 prompt。
- 第一次先跑只读 smoke test，确认凭据和审批行为；无人值守时 `approval=ask` 可能阻塞，优先 `read-only` 或工作区内操作。
- `--json` 输出 NDJSON；会话 ID 从事件或 `~/.dsh/sessions` 取，不要自己编。