# 开发板 24 小时连续录像与七天异常片段

当前 `zy` 适配把两类录像放在不同的受管目录。原有 `AI_GUARDIAN_RECORDING_CONFIG` 控制七天异常片段；新增 `AI_GUARDIAN_CONTINUOUS_CONFIG` 控制 24 小时连续录像。两者共用一次 USB 摄像头采集，但各自拥有 SQLite 索引、空间配额、最低空闲空间和清理调度。两个目录不能相同。配置文件默认关闭；未验证开发板实际码率、编码负载和磁盘占用前，不启用长期服务。

连续录像样例在 [`config/continuous-recording.example.json`](../config/continuous-recording.example.json)。上板时复制为板端私有配置，设置 `enabled: true`、绝对 `data_root`、`storage_quota_bytes` 和 `min_free_bytes`。先确认目录父级位于预期 SD 文件系统，父级已存在且目标目录为空。启动时受管目录创建所有权标记，后续每次写入与清理都会验证标记及设备身份。建议初始参数为 640 像素宽、8 FPS、0.6 Mbps、60 秒分段；10 GiB 连续录像配额及 8 GiB 全局最低空闲空间只是候选值，需根据实测调整。七天异常片段的配额另行设置，不能把两个配额之和超过可用空间。512 kbps 理论上约 5.5 GB/24 小时；实际文件大小以真实场景为准。

云端 API 可设置 `BOARD_RECORDING_BASE_URL=http://127.0.0.1:6001` 和 `BOARD_RECORDING_TOKEN`，通过已有 FRP 回环端口读取板端 `/api/continuous`，向已授权 App 用户继续提供原 `/api/recordings/query`、`/api/recordings/media` 接口。云端只转发查询和按需播放的字节；不要把板端历史令牌放到手机。切换到板端模式后停止旧 `guardian-recording.service` 云端录制进程，避免重复录像。板端两个历史接口使用 `AI_GUARDIAN_HISTORY_TOKEN`；云端的 `BOARD_RECORDING_TOKEN` 应与之匹配，并只保存在服务器私有环境配置中。云端回环端口必须对应可信 FRP 板端连接，绝不将板端历史端口直接公开。

板端连续录像只查询已完成的分段。跨越最近 24 小时起点的完整分段不提供给手机，因此窗口边缘最多缺少一个分段。筛选摔倒/久坐时返回与事件前后约一分钟范围重叠的**完整分段**，手机页面据此明确标注；这与原云端精确裁切模式不同。当前板端编码器使用固定名义帧率，摄像头或编码器丢帧时文件播放时长可能与墙上时钟有偏差；必须在真实摄像头、真实场景、长时间运行中测量后再宣称满足连续 24 小时覆盖。

上板验收要记录：`/api/continuous/status` 是否运行、实时输入/写入/丢帧计数、FFmpeg 及 ffprobe 可用性、每段可播放性、单段实测大小、CPU/温度、SD 剩余空间，以及七天异常片段是否仍能触发和下载。用真实画面运行足够长时间后推算 24 小时空间；再通过隔离测试目录模拟超过 24 小时清理，确认未触碰七天目录和其他文件。时间未同步时清理会拒绝删除；时钟回拨也会停止清理。任何板端部署均先备份现有服务与配置，失败后恢复原状态并保留录像数据。

## 板端实测记录（2026-10-22 21:00–21:20，候选目录）

环境：Orange Pi Ai Pro / Ascend 310B4，3 核可用，内存充足，SD 可用 35 GB；ffmpeg 4.4.2（libx264）；摄像头 640×480。候选目录 `/root/guardian_candidates/20261022T2015-zy-ysh-continuous`，事件片段沿用旧候选目录的七天库。

**配置**：24 小时保留、60 秒分段、8 fps、0.6 Mbps、配额 10 GiB、最低空闲 8 GiB。

| 项目 | 实测 |
| --- | --- |
| 连续录像状态 | `/api/continuous/status` → `state=running`、`capture_integrated=true`、`recording_backend_ready=true` |
| 分段可播放性 | `ffmpeg -v error -i … -f null -` 全部通过；h264 640×480 |
| 分段衔接 | 每段墙钟 59.9 s，相邻缺口 0.13–0.14 s，墙钟覆盖比 0.999 |
| 实际码率 | 静止画面 0.22 Mbps；画面有变化时 0.99 Mbps（目标 0.6 Mbps） |
| 空间折算 | 93 MB/小时 → 24 小时约 2.2 GB（静止画面）；按 0.6 Mbps 上限约 6.5 GB，配额 10 GiB 可容纳 |
| CPU | 用户态约 15%（`python` 22% + `ffmpeg` 9% 单核口径），系统 85% 空闲 |
| 负载均值 | 17.9，**但 18 个 D 状态进程全部是昇腾驱动内核线程**（`bbox_*`、`lpm_proxy`、`ts_proxy` 等），不代表业务过载；勿用 loadavg 判断健康度 |
| 温度 | 无 thermal zone，`hwmon` 仅充电管理，**本机无法读取 CPU 温度** |
| 完整分段数 | 3 分钟产出 3 段（每段 60 s），无 gaps 记录 |

### 发现并修复的缺陷：编码时长比 0.919

初版采样器按回调逐帧转发：实际交付 7.35 fps，而编码器按名义 8 fps 写入，导致**60 秒分段编码后只有 55.00 秒，播放比现实快约 8.1%**，24 小时会缩水成约 22 小时。

修复（`src/guardian_continuous.py`）：引入虚拟采样时钟，落后墙钟时补帧，补帧上限 4 帧；重复帧必须使用**递增**时间戳。第一版补帧复用了同一时间戳，被 `RecordingManager` 判为时钟不连续，把视频切成 0.25 秒碎片（实测产生 463 个碎片段），已修正并补回归测试。

修复后实测：每段 **480 帧 / 编码 60.00 s / 墙钟 59.94 s，时长比 1.001–1.003**。

### 清理边界（隔离目录验证，未触碰真实录像）

- 24 小时目录中 26 小时前的段被删除、2 小时前的保留；
- 同一时间点七天事件目录中 26 小时前的片段**未被删除**；
- 时钟不可信（NTP 未同步）时清理返回 `skipped=untrusted_time`，不删除任何文件；
- 下载租约生效：租约未到期的片段不被清理。

### 云端转发验证

- 板端回环 `http://127.0.0.1:6001` 从阿里云访问返回 200，确认 FRP 转发到可信板端 HTTP 服务；
- `/etc/wenxin/board-recording.env`（600 权限）写入 `BOARD_RECORDING_BASE_URL` 与 `BOARD_RECORDING_TOKEN`，令牌与板端 `AI_GUARDIAN_HISTORY_TOKEN` 一致，**未进入 App 或 Git**；
- `wenxin.service` 加入该 EnvironmentFile 并重启，进程环境已注入；桥接实测：`snapshot` 返回 `status=recording`、5 个完整分段、`wholeSegments=true`，`open_media` 取到合法 MP4（`ftyp`）；
- 鉴权：POST `/api/recordings/query` 无令牌 401「未认证」，错误令牌 401「会话无效」；
- 旧云端 `guardian-recording.service` 已 `stop` 并 `disable`，无 `recording_worker` 进程，避免与板端重复录像。回退：`systemctl enable --now guardian-recording.service`。

### 尚未完成的验收

- **未跑满 24 小时**：以上为约 20 分钟实测 + 线性折算，不能宣称满足完整 24 小时覆盖与稳定性。
- **真实事件触发未复测**：本轮画面无人，`detections=0`；七天片段的"新建触发"需真人入镜后复测（已有的历史事件片段下载与关联已验证正常）。
- **手机端真实登录与播放未验证**：缺少可用账号令牌，仅验证了未授权被拒（401）与桥接/媒体字节通路。
