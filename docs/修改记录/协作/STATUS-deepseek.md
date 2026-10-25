# DeepSeek 状态

> 由 DeepSeek 维护；Codex 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-10-25 10:32 · deepseek · T-20261025-07 · 已完成

> 提交：`345613c` · 分支：本地 `zy`（push 由 Codex 统一执行） · 基于：`564fbc3`
> 下一步：Codex 用 `tools/dsh-headless.ps1` 跑一次只读 smoke test，确认凭据与审批，再派首个 headless 任务。

### 目标

让 Codex 能直接启动一次性 DeepSeek headless 会话，执行/验证后再由 Codex 审核并 push。

### 改动

- 新增 `tools/dsh-headless.ps1`：封装 DSH CLI，支持 `-Task` / `-TaskFile`、`-Workdir`、`-Mode`、`-Json`、`-SessionId`、`-DryRun`。
- 默认 `read-only`；`workspace-write` 才允许改工作区；`danger-full-access` 必须显式 `-AllowDangerFullAccess`。
- 协作 README 增加第 9 节；`AGENTS.md`、`CLAUDE.md` 增加入口；`TASKS.md` 增加 `T-20261025-07`。

### 验证

- `Get-Help tools/dsh-headless.ps1 -Full` 正常显示参数与示例。
- `-DryRun -Task ...` 与 `-DryRun -TaskFile ...` 均输出解析后的 JSON；`Workdir`、`Mode`、`DSH_HOME` 正确。
- `-Mode danger-full-access` 未加 `-AllowDangerFullAccess` 时拒绝执行。
- 未调用模型：只验证了包装脚本和 DSH CLI 帮助，未消耗模型 token。

### 未验证 / 风险

- 实际 headless 任务未跑；首次需只读 smoke test，确认凭据、审批和输出。
- 无人值守时 `approval=ask` 可能阻塞；优先 `read-only` 或工作区内操作，不要默认 `danger-full-access`。
- 本机沙箱不能写 `~/.dsh`；Codex 在正常终端运行不受此限制。

### 下一步

- Codex：`.\tools\dsh-headless.ps1 -Task "只回复 OK，不要读取或修改任何文件。"` 做首次连通性测试。
- 通过后按任务卡调用；DSH 只本地提交，Codex 审核并 push。

### 回滚

- `git revert <本提交>`；或删除 `tools/dsh-headless.ps1` 与 README 第 9 节。

## 2026-10-25 10:30 · deepseek · T-20261025-06 · 待验证

> 分支：本地 `zy`（push 由 Codex 统一执行） · 基于：`1df1070`
> 下一步：板端 `ascend_voice_stream.py` 仍是 2025-12-18 旧版，等用户授权后再同步；其余板端代码与 `origin/zy` 一致。

### 目标

建立服务器/开发板接入通道，核对开发板运行代码与 `feature/hjb-ascend-voice`、`origin/zy` 的差异，确认本地是否已是最新。

### 改动

- 仅本机配置：仓库 `.git/config` 增加 `http(s).proxy=socks5h://127.0.0.1:1080`、`http.sslBackend=openssl`（本机到 github.com:443 被阻断，经服务器 SOCKS 绕行）。
- 建立工作区回退点 `refs/backups/zy-20261025-1016`（HEAD + 未提交改动 + 未跟踪文件，542 个文件，逐文件校验一致）。
- 未修改任何源码，未提交业务代码。

### 验证

- 服务器 SSH（47.108.167.0:22）与开发板 SSH（:6022）均连通；服务器 `wenxin.service`、开发板 `guardian-board.service` 均在运行。
- `zy` 本地与 `origin/zy` 均存在，本地领先 1 个文档提交。
- `feature/hjb-ascend-voice` 末次提交 2025-12-18，已是 `zy` 的祖先（落后 222 个提交）。
- 板端 `/root/ai_guardian` 与 `origin/zy` 逐文件哈希比对：16 个文件内容一致（`ascend_video_stream.py` 仅换行符差异）；`ascend_voice_stream.py` 为旧版；6 个文件在仓库 `src/` 无对应（`db/init_db.py`、`patch_main_other.py`、`test_face_rec_acl.py`、`vlm_*.py`）。

### 未验证 / 风险

- 板端旧版语音流是否影响双向通话，未做实测。
- 本机无 GitHub SSH key，且 443 被阻断；不经 SOCKS 隧道时 `git fetch/push` 会失败。

### 下一步

- 待用户授权：是否把 `origin/zy` 的 `ascend_voice_stream.py` 同步到开发板（需先备份并重启 `guardian-board.service`）。
- 板端若确认无其他本地改动，可将本结论作为后续部署基线。

### 回滚

- 工作区恢复到本次比对前：`git checkout refs/backups/zy-20261025-1016 -- <path>`。
- 本机代理配置可撤销：`git config --unset http.proxy`、`git config --unset http.sslBackend`。

## 2026-10-25 10:11 · T-20261025-04 · 已完成（骨架）

> 分支：本地 `zy`（提交见 `git log -1`） · 基线：`b6b3ec8`
> 下一步：等用户确认事件录像改动是否提交；Codex 接手 `T-20261025-01` 的真机播放/七天清理验证。

### 目标

建立 Codex 与 DeepSeek 的协作入口，减少重复读全库和互相覆盖。

### 改动

- 新建 `docs/修改记录/协作/`：`README.md`、`TASKS.md`、两份 `STATUS`、`TEMPLATE.md`、`archive/README.md`。
- `AGENTS.md`、`CLAUDE.md` 增加协作规则；`docs/修改记录/README.md` 增加索引。
- 未改任何业务代码；当前 8 个事件录像文件和 1 个未跟踪验收文档保持原样。

### 验证

- 仅文档改动；提交前检查无密钥、无大文件、无个人数据。
- 未运行 Python/HAP 测试，因为本次没有改代码。

### 未验证 / 风险

- 当前事件录像改动归属未确认，未提交；不要用 `git add -A`。
- 未 push；远端 `zy` 仍是 `b6b3ec8`。

### 下一步

- 用户确认后：把事件录像改动提交到本地 `zy`，或按新的 WIP 规则转到 `wip/codex-20261025`。
- Codex 接手 `T-20261025-01`：真机播放、七天清理观察、签名 HAP 验收边界。
- DeepSeek 继续 `T-20261025-03`：文档一致性。