# Claude 状态

> 由 Claude 维护；只保留最近 3 条，最新在上。格式见 `TEMPLATE.md`。

## 2026-11-05 · claude · 文档清理与架构图 · 已完成（仅本地提交，未推送）

> 分支：`feature/jyx-home`。下一步：由 Codex 推送。

### 改动

- 删除过时文档、旧截图、测试视频和 ATC 杂项（51 个文件）；板端模型文件（best*.om、model.om、oldbest.onnx）未动。
- README 截图换成 10-28 新界面（首页实时画面已打码，新增个人中心）；版本改为 6.1.1 / API 24。
- 交接、运维、数据库、内容审核文档改正：华为云已关停、官网纯静态、证书到期日、生产 IP。
- 新增 `docs/architecture/` 系统架构图与功能架构图（SVG + PNG），替换旧的 guardian_system_architecture.svg。

### 验证

- 架构图由 archify 生成，自动检查与浏览器检查通过，导出图已人工查看。

## 2026-10-27 · claude · T-20261027-c02 · 已完成（已部署板端，模拟器验证）

> 分支：`feature/jyx-home`。下一步：真机看首页/全屏画面；关注手机热点上行带宽（每路约 3 Mbps）。

### 改动

- 摄像头关闭曝光优先、防闪烁改 50 Hz（`ascend_main_other.py` 开流后调 `v4l2-ctl`，环境变量可改）；该摄像头实际出帧约为设定值一半，设 30 实测 15。
- 推流 320×240 质量 35 → 640×480 质量 65（`ascend_video_stream.py`，`AI_GUARDIAN_STREAM_SIZE/QUALITY` 可调）。
- 实时画面改为摄像头线程直接出帧并叠加最近一次（1 s 内）推理框；推理、告警、事件录像仍用原推理帧，未改阈值（告警均按秒计时）。
- App `CameraStreamView` 与板端网页改用 fetch 逐帧读 MJPEG，6 s 无新帧自动断开重连；之前流断后停在黑屏/最后一帧不恢复，且模拟器首页预览一直黑屏。

### 验证

- 公网 `/video_feed`：7.4 → 14.1 fps，每帧约 6 KB → 27 KB；推理仍 7.3～7.8 次/s。
- 模拟器（签名 Release HAP）首页出画面带框；重启板端服务后约 12 s 自动恢复。网页 `/device/` 重启后约 9 s 自动恢复。
- `tests/` 下人脸/运行时测试 36 项通过（heartbeat 需在仓库根目录跑）。

### 回滚

- 板端：`/root/backup/stream-quality-202610271718/` 三个文件拷回 `/root/ai_guardian/` 后重启 `guardian-board.service`。

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

