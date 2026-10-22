# 阿里云迁移修复与验收

2026-09-08，生产主机为阿里云 `47.108.167.0`。华为云 `117.78.9.144` 保留回退环境；不要使用旧华为部署脚本更新阿里云，也不要将旧数据库覆盖回当前生产库。

## 当前入口和数据

- 官网：`https://aistar.asia`；API：`https://api.aistar.asia`。
- 设备页：`https://api.aistar.asia/device/`；视频、状态和对讲分别为 `/video_feed`、`/api/stats`、`/ws/intercom`。
- 阿里云 API：`/opt/wenxin/app`，Gunicorn 仅监听 `127.0.0.1:8899`。SQLite 为该目录的 `guardian_users.db`，备份目录为 `/var/backups/wenxin`。
- MQTT 仅使用 TLS 8883；FRP 服务端为阿里云 7000，设备转发端口为 6000、6001、6022。不要重新开放明文 MQTT 或公网 API 8899。
- 开发板项目为 `/root/ai_guardian`，`guardian-board.service` 管理 AI、视频和音频进程；开发板同时保留旧华为 FRP。

原华为库 9 个用户均存在于阿里云库；本次检查阿里云有 11 个用户，两库完整性均为 `ok`。会话表是动态数据，不能用当前两边行数不同推断迁移丢失；本次没有做所有字段逐项比对。华为 Docker 无容器，openGauss 未发现项目业务表；未迁移这些非生产组件。

## 修复与回滚

1. 摄像头：启动缺少摄像头时保留已初始化 NPU，后台重试；断连清除旧帧，重新接入后恢复。状态接口新增 `camera_connected`，失去新画面时 FPS 为 0、视频帧接口返回 204。补丁和幂等应用脚本见 [camera-recovery.md](../deploy/board/camera-recovery.md)。完整板端源码可能包含部署凭据，仓库只维护无凭据的最小补丁。
2. 音频：USB 供电加 3.5mm 音频线的音响使用板载 Ascend MPI AO，不依赖 ALSA 播放设备枚举。USB 麦克风仍由 PyAudio 采集。实现、编译与回滚见 [ascend-audio-output.md](../deploy/board/ascend-audio-output.md)。桥接禁止调用全局 `hi_mpi_sys_exit`。
3. MQTT：使用现有登录会话领取短期、只读凭据。账号必须在服务器 allowlist 中；用户授权账号为 `test`。不能向所有新注册账号开放这块共享开发板。部署、撤销与回滚见 [MQTT_ACCESS.md](../deploy/aliyun/MQTT_ACCESS.md)。

板端本次回滚原件为 `/root/ai_guardian/ascend_main_other.py.camera-before`、`ascend_board_server.py.camera-before`、`ascend_voice_stream.py.audio-before`。恢复相关原件前停止 `guardian-board`，恢复后再启动并验证；不要删除模型、人脸库或其他任务文件。

阿里云 MQTT/API 回滚目录为 `/root/wenxin-rollbacks/mqtt-20260908T102203Z`，含原文件存在性清单与数据库快照。代码回滚恢复原代码、unit、YAML 与 allowlist，重载 systemd、重启 API/broker；新增表可保留，不要为代码回滚覆盖上线后业务数据。

## 本次证据

- 官网、API、管理页、设备页可访问，云端 API/MQTT/FRP/Nginx 运行；备份完整性通过。
- 新 Logitech C270 可读取 640×480 图像。部署后实测仅解绑其视频控制接口，离线时 `camera_connected=false`、FPS 0、JPEG 204；重新绑定后自动恢复约 7.8 FPS，业务 PID 未变。这是驱动断连恢复测试，不等于所有 USB 供电故障均可软件恢复。
- 正式 HTTPS/WSS 链路发送三声低音量提示音，用户确认音响可听；模拟器麦克风授权、发起通话和挂断流程通过。未保存录音。
- Release 混淆曾将接口字段 `expiresIn` 改成 `n4`，导致续期间隔为 NaN、约每 0.4 秒重连。已保留外部 JSON 字段并增加契约回归，最终产物 nameCache 检查通过；模拟器登录显示在线、已连接。
- 模拟器在首次凭据 5 分钟有效期之后仍显示已连接。原生 `OnSubscribe Success` 两次成功相隔 270.446 秒，符合提前 30 秒自动续期；仅从内存日志导出事件时间和次数，不保存原始日志。页面“在线”来自 HTTP 状态接口；板端仅发送事件，没有 MQTT 心跳，不能用此文案代替真实告警到达证据。
- AI 一度由扣子返回 402，错误明确要求充值积分。用户处理后，真实登录鉴权、输入审核、扣子、输出审核整条请求返回 HTTP 200 和测试回复；不记录密码或令牌。
- `certbot renew --dry-run --non-interactive` 对官网（含 www）和 API 均成功；两个现有 deploy hook 实际执行成功，Nginx 语法与平滑 reload 通过。生产证书内容未变：API 到期 2026-10-13，官网到期 2026-10-25。

## 安装包与验证边界

用户选择统一 API 24，App 版本为 1.0.1 / 1010001。HAP 按 [DEVECO_BUILD.md](../DEVECO_BUILD.md) 构建；构建成功必须再检查实际产物、哈希和运行结果。模拟器通过不等于实体手机完整验收。

本次签名 HAP SHA-256：`6981A5EF2826A01F99185D9E07B74CBEDF5C7DD5DC33463B64A33B09D05AEF6A`。最终本机回归 121 项，113 项通过、8 项 broker 测试因缺本机依赖跳过；同一 broker 测试已在服务器隔离环境通过（MQTT 测试共 17 项）。

本次未向实际收件人发送短信或邮件，也未完成实体手机双向语音及真实跌倒告警验收。这些项目不能仅凭服务进程正常宣布端到端通过。

摄像头与音频回归使用项目测试。摄像头测试须提供私有板端源码目录 `BOARD_CAMERA_SOURCE`；缺源码时显示跳过，不能当作通过。MQTT 使用 AMQTT 0.11.3 的真实隔离 broker 测试认证、只读授权、撤销和板端兼容；测试不使用生产告警主题发送伪造事件。
