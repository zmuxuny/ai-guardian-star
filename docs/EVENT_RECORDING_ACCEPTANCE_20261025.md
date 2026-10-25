# 异常行为录像缓存与按需下载验收（2026-10-25）

## 1. 最终产品契约

- 软件端只展示异常行为类型、发生时间和下载按钮。
- 页面打开或刷新列表时只读取事件元数据，不自动下载视频。
- 用户点击下载按钮后，App 才通过云端鉴权代理从开发板获取对应 MP4。
- 视频原文件只保存在开发板受管目录中，每个视频按生成时间精确保留 168 小时；清理调度每 60 秒检查一次到期数据。
- 当前异常类型包括摔倒、久坐和陌生人。
- 不启用 24 小时连续录像，也不在 App 中展示普通时段视频。

## 2. 新增与修改位置

### 开发板

- `/etc/guardian/event-recording.json`：启用事件录像，`retention_hours=168`、8 FPS、0.8 Mbps、5 GiB 配额、至少保留 8 GiB 全局空闲空间。
- `/etc/guardian/recording.env`：只注入事件录像配置路径和历史接口令牌，不设置 `AI_GUARDIAN_CONTINUOUS_CONFIG`。
- `/etc/systemd/system/guardian-board.service.d/recording.conf`：让生产服务读取私有录像环境文件。
- `/var/lib/guardian-recordings/events`：独立受管数据根，包含 SQLite 索引、MP4、临时文件和所有权标记。

板端配置回滚备份：

```text
/root/ai_guardian-backups/recording-enable-20261025T092716
```

### 云端

- `board_recording_bridge.py`：查询 `/api/history/events` 和事件详情，只返回异常摘要及可下载状态；媒体改从 `/api/history/recordings/{id}/video` 按需读取。
- `recording_api.py`：查询窗口改为 7 天，增加陌生人类型，未完成片段返回“正在生成”，不提前下载。

云端回滚备份：

```text
/root/wenxin-backups/event-recording-contract-20261025T093055
```

### HarmonyOS App

- `entry/src/main/ets/components/RecordingBrowser.ets`：页面改为异常类型、时间和显式下载按钮；首次点击才下载到 App 临时缓存，随后显示本地播放器；离开页面清理临时文件。
- `entry/src/main/ets/common/RecordingService.ets`：录像条目增加 `downloadable` 状态。
- `entry/src/main/ets/pages/record.ets`：副标题改为“异常类型、时间与按需下载”。

## 3. 验收证据

| 层级 | 结果 |
| --- | --- |
| 本地测试 | `python -m unittest discover -s tests`：168 项通过、2 项跳过 |
| HAP 构建 | API 24 debug HAP 构建成功；未配置签名 |
| 模拟器安装 | `Huawei_phone`、HarmonyOS 6.1.1（API 24）安装成功 |
| 板端状态 | `/api/history/status` 返回 200，`enabled=true`、`recording_backend_ready=true`、`retention_hours=168` |
| 连续录像边界 | `/api/continuous/status` 返回 404，确认未启用全天录像 |
| 真实事件 | 产生 3 条真实事件（久坐、陌生人），最终有 3 个完成录像和 3 条事件录像关联 |
| 真实媒体 | H.264、640×480、8 FPS、12 秒、1,227,591 字节，`ffprobe` 通过 |
| App 列表 | 显示“久坐”和发生时间，右侧显示“下载”；页面初次加载未请求媒体接口 |
| 按需下载 | 点击后 `/api/recordings/media` 返回 HTTP 200 和 1,227,591 字节，按钮变为“已下载” |
| 生成状态 | 新触发的陌生人事件先显示“生成中”，片段封装完成并刷新后自动变为“下载” |

最终未签名 HAP：

```text
C:\Users\Yang\Documents\ChatGPT\zhihuixing\entry\build\default\outputs\default\entry-default-unsigned.hap
SHA-256: 272362E415435430FCEA65C709B1FB23A3ED5096E2458C5268A56DE24587C093
```

## 4. 当前边界

- 已证明事件触发、硬件落盘、事件与录像关联、云端列表、点击后下载、App 本地落盘、模拟器内播放（画面推进、暂停、重播、拖拽进度）链路。
- 2026-10-25 11:20 之后的回归见第 5、6 节：默认分支上的 release 包曾整体下载失败，修复后才重新可用。
- 168 小时到期判断和清理逻辑已通过自动化测试，生产配置及清理调度已启用；真实等待七天后的自动删除尚未按自然时间观察。
- 当前是未签名 HAP 的 API 24 模拟器验收，不等同于正式签名包或 HarmonyOS 真机验收；本机没有真机，真机结论仍缺。

## 5. 2026-10-25 11:20 回归：Release 属性混淆导致下载 404（已修复）

同一份代码打成 **release** 包后，点击下载全部失败；**debug** 包此前可正常下载。根因在构建侧，与云端、板端数据无关。

- 现象：App 提示「录像已过期，请刷新列表」，服务端 `POST /api/recordings/media` 返回 404（响应体 127 字节）。
- 服务端侧证据：`board_recording_bridge.snapshot()` 连续两次调用返回 81 条、`id` 稳定、`downloadable=true`，说明不是数据漂移或保留期问题。
- 抓包证据（云端回环，nginx 之后的明文段）：

  ```text
  修复前：{"asOf":1792898224688,"filter":"all","l9":"470eb196c390469ba1bf9684b6e8f769"}
  修复后：{"asOf":1792898408901,"filter":"all","clipId":"530c9d7610784d6b881ce65f61c23016"}
  ```

- 根因：`entry/build-profile.json5` 对 release 开启混淆，`entry/obfuscation-rules.txt` 维护线上字段保留清单但漏了 `clipId`，属性混淆把它改名为 `l9`；服务端 `recording_media()` 读 `data['clipId']` 抛 `KeyError`，落入「找不到该片段」的 404 分支。
- 修复：把录像接口线上字段加入保留清单（`clipId`、`asOf`、`filter`、`segmentId`、`eventType`、`startTime`、`endTime`、`endUnconfirmed`、`downloadable`、`clips`、`eventCount`、`wholeSegments`、`windowStart`、`windowEnd`），重新构建 release 包。
- 修复后验收：请求返回 `200 OK`，App 落盘 1,374,901 字节；按钮 `下载中` → `已下载`；离开记录页后临时文件被删除；列表首屏仍不自动下载。

## 6. 2026-10-25 11:50 回归：`Video` 不接受沙箱文件，改为 `AVPlayer.fdSrc`（已修复）

下载修好后，模拟器里播放仍停在 `00:00`，不放任何画面。

- 判别实验：同一个 `Video` 组件换成打包在 HAP 里的 `$rawfile('probe_video.mp4')` 后正常播放（`00:01 / 00:02`，画面推进），证明**组件与解码没问题**，问题在视频源类型。
- 源类型对照：
  - `$rawfile(...)` → 正常播放；
  - `fd://<fd>` → `PlayerServer ... Can not Play, currentState is PLAYER_IDLE`，probe 不结束；
  - 沙箱绝对路径 → 同上。
- 根因：`Video` 的 `src` 不消费应用沙箱文件描述符（`fd://` 是 `Image` 的用法），播放器始终停在 IDLE，所以 `00:00`、黑屏。
- 修复：`RecordingBrowser.ets` 改用 `XComponent( SURFACE )` + `media.AVPlayer`，通过 `fdSrc = { fd, offset, length }` 喂本地文件，并自绘播放/暂停、进度条、时间与错误提示；播放卡从 `List` 内部移到列表上方固定区域（高 150vp），避免列表回收销毁播放表面。
- 修复后验收（模拟器 API 24）：
  - 下载完成后自动开始播放，位置 `00:01 → 00:03 → 00:06` 递增，时长 `00:13` 与文件一致；
  - 连续两帧截图差分在播放区有 95,762 / 45,892 个像素变化（此前为 0），画面确实在推进；
  - 暂停后位置冻结在 `6680ms` 两次采样不变；播放结束后按「播放」从 0 重播；
  - 播放中再点另一条下载，文件被替换为新片段、旧临时文件删除、进程未重启（此前该操作会因未捕获的 Promise 拒绝把应用杀掉，已加 `try/catch` 与 `release().catch()`）；
  - 离开记录页后本次临时文件被删除。
