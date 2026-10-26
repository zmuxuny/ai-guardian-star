# Claude 状态

> 由 Claude 维护；只保留最近 3 条，最新在上。格式见 `TEMPLATE.md`。

## 2026-10-26 · claude · T-20261026-06 · 待验证

> 分支：`feature/jyx-home`，基于 `wip/deepseek-20261026-recording-day-lazy` 合入后的 `e7ebed9`。
> 下一步：模拟器/真机上点一个片段看能否在线播放、拖动进度，再点“下载”另存一次。

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

### 未验证 / 风险

- App 端未上模拟器/真机，在线播放和另存流程没有实测。
- 宝塔全局 `proxy.conf` 开着 `proxy_cache cache_one`，会剥掉 Range；本次只给 `/api/recordings/stream/` 单独 `proxy_cache off`，其他 API 仍受全局缓存影响。

### 回滚

- 代码：`git revert` 本提交。
- 云端：`/root/backup/recording-stream-202610261122/` 下有旧版两个 py 文件；nginx 备份为 `api.aistar.asia.conf.bak-202610262324-stream`，恢复后 `nginx -t && nginx -s reload`、`systemctl restart wenxin.service`。
