# Claude 状态

> 由 Claude 维护；只保留最近 3 条，最新在上。格式见 `TEMPLATE.md`。

## 2026-10-27 · claude · T-20261027-c01 · 已完成（已部署）

> 分支：`feature/jyx-home` 提交 `ac48605`（性能），并合入 `origin/ysh@8267c85`（`1fecb55`）。
> 下一步：真机复测记录页；观察 wenxin.service 内存上限是否被触发（`journalctl -u wenxin.service | grep -i oom`）。

### 改动

- 板端 `guardian_history.py` 新增 `list_recordings_for_events()`（一条 SQL）；`guardian_history_api.py` 的 `/api/history/events` 列表附带每个事件的 `recordings`（加字段，旧客户端不受影响）。
- 云端 `board_recording_bridge.py`：事件自带 `recordings` 时不再逐个请求详情；旧版板端没有该字段时自动回退原逻辑。
- 云端 `wenxin.service` 新增 drop-in `/etc/systemd/system/wenxin.service.d/memory.conf`：`MemoryHigh=600M`、`MemoryMax=768M`，超限只重启本服务，不拖垮整机。

### 验证

- 云端测试 39/39；板端历史接口与存储测试 41/41（本机临时 venv 装 fastapi/httpx 跑，含新增批量用例）；ysh 带来的两组 node 测试各 12/12。
- 生产实测：两天 614 个事件查询 0.55 s，访问板端 9 次（原先每个事件一次，约 600+ 次）。
- 合并后签名 Release HAP 装模拟器：主页、记录页正常，当天 14 个事件加载成功。

### 回滚

- 板端：`/root/backup/history-batch-202610261238/` 两个文件拷回 `/root/ai_guardian/` 后 `systemctl restart guardian-board.service`。
- 云端：`/root/backup/history-batch-202610270039/board_recording_bridge.py` 拷回 `/opt/wenxin/app/`；删除 `wenxin.service.d/memory.conf` 后 `systemctl daemon-reload && systemctl restart wenxin.service`。

## 2026-10-26 · claude · T-20261026-13（原 -06，与 codex 撞号后改）· 已验证（模拟器）

> 分支：`feature/jyx-home`，基于 `wip/deepseek-20261026-recording-day-lazy` 合入后的 `e7ebed9`；追加 `2f7a015`（日期卡“正在读取”）。
> 下一步：真机复测一次；关注下方“服务器卡死”一节。

### 目标

记录页按日期折叠展示近 7 天异常；点击片段在线播放（不落地手机），“下载”按钮才保存到手机。

### 改动

- `recording_api.py`：新增 `POST /api/recordings/stream-url`（账号鉴权，签发 10 分钟 HMAC 地址）和 `GET /api/recordings/stream/<id>`（验签后透传开发板视频，转发单段 Range，回 206）；抽出 `requested_clip()` 供 media 与 stream-url 共用。
- `board_recording_bridge.py`：`open_media` 支持单段 Range；新增 `stream_secret()`，签名密钥由板端令牌派生，令牌不出云端。
- `RecordingBrowser.ets` / `RecordingService.ets`：点击片段行走 `AVPlayer.url` 在线播放；“下载”按钮用 `DocumentViewPicker` 选位置后写入；去掉缓存文件与 fdSrc 播放路径。
- `entry/obfuscation-rules.txt`：保留响应字段 `path`、`expires`。

### 验证

- `python -m unittest tests.test_continuous_board_bridge`：38/38 通过（新增 4 条签名/Range 用例）。
- Release HAP 构建成功（无签名配置）。
- 云端已部署：公网 `bytes=0-99` 返回 206、尾段 Range 返回 206、全量 1.34 MB 约 0.7 s；无签名或篡改签名 403；未登录 stream-url 401。

- Pura 90 Pro 模拟器（签名 Release HAP，账号 周防有希）：记录页加载 10-26 共 328 个事件；点片段在线播放 13 s 完整播完（服务端 206 两段，合计 1,361,800 字节）；拖动进度到末尾正确进入完成态；“下载”弹出 DocumentViewPicker，存到 Download 后文件 1,361,800 字节，与 `/api/recordings/media` 一致。
- `2f7a015`：日期卡 ForEach key 只用日期，`patchDay` 换对象后不重建，界面一直“正在读取”；key 加入加载状态后修复，模拟器已验证。

### 运维变更

- `/etc/wenxin/mqtt-users.json` 加入用户本人账号 `周防有希`（用户同意），备份 `mqtt-users.json.bak-20261026T235902`。

### 服务器卡死（10-27 00:01，原因未定）

- 现象：ssh 拿不到 banner、API 全超时；控制台监控显示内存长期约 1.8/1.87 GB，00:01 起磁盘读飙到约 3300 次/s、网络归零，属内存耗尽抖动。用户在控制台重启后恢复，重启后内存仅用 540 MB（有 2 GB swap）。
- 卡死前最后的请求是本次在线播放（2 次 206，均正常完成）；前后 frps `[video]`（6001）每次 `recordings/query` 会扇出约 330 次板端请求（N+1：每个事件取一次详情）。
- 复现：重启后挂每秒内存采样，重复查询 + 两次在线播放 + 一次下载，可用内存最低 1309 MB，无增长，未复现。卡死前占内存的进程已无法追溯。
- 建议：给 `wenxin.service` 加 `MemoryMax`；`snapshot()` 的 N+1 详情请求改为板端批量接口。

### 未验证 / 风险

- 真机未测；服务器卡死原因未定（见上）。
- 宝塔全局 `proxy.conf` 开着 `proxy_cache cache_one`，会剥掉 Range；本次只给 `/api/recordings/stream/` 单独 `proxy_cache off`，其他 API 仍受全局缓存影响。

### 回滚

- 代码：`git revert` 本提交。
- 云端：`/root/backup/recording-stream-202610261122/` 下有旧版两个 py 文件；nginx 备份为 `api.aistar.asia.conf.bak-202610262324-stream`，恢复后 `nginx -t && nginx -s reload`、`systemctl restart wenxin.service`。
