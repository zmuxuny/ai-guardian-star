# DeepSeek 状态

> 由 DeepSeek 维护；Codex 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-10-25 13:20 · deepseek · T-20261025-09 · 待验证

> 分支：`zy` @ `3be8786`（本地提交，未 push）· 基于：`9d42ec4`
> 提交：`3be8786` App 实时画面；同批 `164309f` 云端、`2d921f9` App 契约、`b8ee99a` App 下载/播放
> 下一步：用户看效果；要更清晰得让板端把 `/video_feed` 提到 640×480。

### 目标

首页实时画面铺满预留的 4:3 画面框，不再出现黑边。

### 改动

- `entry/src/main/ets/pages/mainpage.ets` —— `Web` 增加 `onPageBegin`，注入样式把裸 MJPEG 文档的 `img` 设为 `100vw/100vh` + `object-fit: cover`，最多重试 25 次等 `img` 出现；未改服务端与板端。

### 验证

- 模拟器 API 24，release 包安装后进入首页。
- 修复前：预留框 1314×984 内黑像素 43.0%，左/右/上/下边缘带分别为 81%/71%/59%/85%，Web 里的 `image` 是居中小图。
- 修复后：整体黑像素 6.0%，边缘带 0.9%/4.7%/0.1%/16.5%（残留为画面本身偏暗与角标），`image` 节点扩展到 `[3,312][1317,1296]` 铺满整框。
- 间隔 1.5s 两帧截图差分：画面区 159,825 / 161,280 像素变化，确认是活流不是静态图。
- 小窗模式（滚动静止后 546×408）同样铺满，边缘带非纯黑。

### 未验证 / 风险

- `/video_feed` 只有 320×240，铺满后约 4 倍放大，画面偏软；要清晰需板端提高推流分辨率。
- 「实时画面」「在线」角标与放大按钮都落在右上角并互相覆盖，放大按钮实际点不到；属既有布局问题，本次未改。

### 回滚

- `git checkout -- entry/src/main/ets/pages/mainpage.ets`，重新构建。

## 2026-10-25 11:50 · deepseek · T-20261025-01 · 待验证

> 分支：`zy` @ `b8ee99a`（本地提交，未 push）· 基于：`9d42ec4`
> 提交：`164309f`（云端接口）、`2d921f9`（App 契约）、`b8ee99a`（App 下载 404 + 播放）
> 下一步：Codex 审核后 push；用户确认播放器交互变更。

### 目标

定位“云端下载不了录像、也无法查看”的根因，并在 API 24 模拟器上完成本地验证。

### 改动

- `entry/obfuscation-rules.txt` —— 新增录像接口线上字段保留清单（`clipId`、`asOf`、`filter`、`segmentId`、`eventType`、`startTime`、`endTime`、`endUnconfirmed`、`downloadable`、`clips`、`eventCount`、`wholeSegments`、`windowStart`、`windowEnd`）。未改服务端。
- `entry/src/main/ets/components/RecordingBrowser.ets` —— 播放器由 `Video` 换成 `XComponent(SURFACE)` + `media.AVPlayer.fdSrc`，自绘播放/暂停、进度、时间、错误；播放卡移到列表上方固定区（150vp）；补 `try/catch` 与 `release().catch()`。
- 行为变更：播放结束不再自动连播下一个片段（原 `Video.onFinish → playNext`）。

### 验证

- 模拟器 `Huawei_phone`（HarmonyOS 6.1.1 / API 24）、`hdc` 连 `127.0.0.1:5555`；release 未签名 HAP 构建安装。
- 下载 404：修复前抓包体为 `{"asOf":…,"filter":"all","l9":"<事件id>"}` → 404（127 字节）；修复后 `clipId` 正常、HTTP 200、落盘 1,374,901 字节、`下载中` → `已下载`。
- 播放：`fd://` 与沙箱裸路径都停在 `PLAYER_IDLE`；改 `AVPlayer.fdSrc` 后位置 `00:01 → 00:06` 推进、时长 `00:13`，相邻两帧截图差分播放区变化 95,762 / 45,892 像素（此前 0）。
- 交互：暂停后位置冻结 `6680ms` 两次采样不变；结束后按「播放」从 0 重播；播放中切换片段不重启进程；离开记录页删除本次临时文件。
- 落盘文件校验：`avc1` 640×480、13.6 秒、`moov` 前置。

### 未验证 / 风险

- 无真机：模拟器结论不能代替真机，正式签名包未验。
- 其他接口是否存在同类 release 属性改名未全量排查。
- 进程被杀时残留的临时 mp4 不会被自动清理（有「清理缓存」入口兜底）。
- 抓包内容含会话 `Authorization` 头，未写入任何仓库文件或记录。

### 下一步

- Codex：审核并 push。本次只改端侧，云端与板端无需重新部署。
- 待用户确认：播放器交互（自绘控件、不自动连播、播放卡固定在上方）是否符合预期。

### 回滚

- `git checkout -- entry/obfuscation-rules.txt entry/src/main/ets/components/RecordingBrowser.ets`，重新构建即可回到旧行为。

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

