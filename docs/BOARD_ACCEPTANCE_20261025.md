# 开发板与人脸录入联调验收（2026-10-25）

## 1. 验收对象

- 本地仓库：`C:\Users\Yang\Documents\ChatGPT\zhihuixing`
- 分支基线：`zy`，部署前远端提交 `e4c16fc`
- 开发板：Orange Pi AI Pro，`aarch64`，本次 DHCP 地址 `192.168.137.184`
- 开发板服务：`guardian-board.service`
- 云端服务：`wenxin.service`、`frps.service`、`amqtt.service`
- App：HarmonyOS API 24 模拟器产物此前已构建和安装；本次验收时模拟器未运行，因此没有新增 UI 层证据。

真实令牌、账号凭据、图片内容和已有人员信息均未写入本文或命令输出。

## 2. 部署与回滚点

开发板部署了 `src/ascend_board_server.py`、`src/ascend_main_other.py`、`src/guardian_*.py`，保留原模型、音视频硬件文件和数据库。完整回滚目录：

```text
/root/ai_guardian-backups/full-20261025T090800
```

生产心跳入口修复后的 `ascend_board_server.py` SHA-256：

```text
79309fa0df6053a8e9bf961ad1dbfd3ca95ca4dd98ef9880b412d63d775c006a
```

云端只更新 `wenxin_proxy.py`、`face_api.py`、`board_face_bridge.py`，并向现有 Nginx 配置追加精确路径 `/api/face/enroll`，保留原录像环境文件。回滚目录：

```text
/root/wenxin-backups/face-20261025T090813
```

板端 `/etc/guardian/face.env` 与云端 `/etc/wenxin/board-face.env` 权限均为 `600`。服务通过独立 systemd drop-in 读取配置，令牌没有进入仓库。

## 3. MQTT 心跳证据

初次部署后，真实 MQTT 订阅 35 秒没有收到心跳。根因是心跳仅接入 `ascend_main_other.py` 的独立入口，而生产服务运行 `ascend_board_server.py`。修复后由生产服务创建和停止 `MqttHeartbeatPublisher`。

真实 Broker `47.108.167.0:8883` 上连续收到三条 QoS 1 心跳：

- 事件：`heartbeat`
- 设备：`ascend_board`
- 序号：3、4、5
- 间隔：`10.020s`、`9.999s`
- 首次观测状态：`cameraConnected=false`、`aiRunning=true`

断线恢复探针结果：

- 停止服务前最后一条心跳：序号 7，时间 `1792890709651 ms`
- 停止期间没有新心跳，下一条间隔 `74.711s`
- 服务重新启动请求：`1792890781863 ms`
- 恢复心跳：序号重新从 1 开始，时间 `1792890784362 ms`，恢复耗时约 `2.499s`
- 后续心跳：序号 2，间隔约 `9.360s`，状态恢复为 `cameraConnected=true`、`aiRunning=true`

`systemctl stop` 最终状态为 `inactive/dead`、`Result=success`，再次启动后为 `active/running`，本机 `/api/stats` 可访问。

## 4. 人脸录入契约证据

云端通过 FRP 回环 `127.0.0.1:6001` 取得开发板实时画面，并以短时验收会话调用公网 HTTPS 接口。结果：

| 场景 | 结果 |
| --- | --- |
| 未携带登录会话 | HTTP 401 |
| 授权账号首次录入 | HTTP 200，`success=true`，`recognitionStatus=ready`，`photoCount=1` |
| 同账号追加第二张 | HTTP 200，`photoCount=2` |
| 未在设备名单的账号 | HTTP 403，`success=false` |
| 板端服务停止 | HTTP 503，`success=false` |
| 板端恢复并复用同一会话 | HTTP 200，`recognitionStatus=ready` |

验收结束后已执行：

- 删除所有短时云端会话；
- 删除临时图片和令牌状态文件；
- 通过板端管理接口删除 `test` 验收人脸及其全部样本；
- 确认测试用户不再存在，板端人脸总数恢复到验收前的 1。

## 5. 最终运行状态与边界

- 开发板：`guardian-board.service=active`，`frpc-aliyun.service=active`。
- 相机：`camera_connected=true`，实测约 `7.6 FPS`。
- 云端：`wenxin.service=active`、`frps.service=active`，内网与公网 `/health` 均通过。
- Nginx：`/api/face/enroll` 使用 9 MiB 上限、60 秒上传超时和 45 秒代理超时，配置检查通过。
- 已证明真实板端心跳、断线缺报、恢复重发和云端人脸代理完整链路。
- 本次没有在 HarmonyOS 模拟器界面观察 30 秒后“设备离线”文字变化；该项仍需启动 API 24 模拟器、登录授权账号后补充 UI 层证据。协议解析和 30 秒判断已有本地测试，但不能替代实际界面验收。
