# 人脸录入契约与部署验收

## 1. 最终调用链

1. HarmonyOS App 使用现有登录会话调用 `POST https://api.aistar.asia/api/face/enroll`。
2. App 只提交 `name` 和 `file`，不提交板端管理员令牌，也不决定 `user_id`。
3. 云端验证 Bearer 会话，并使用 `/etc/wenxin/mqtt-users.json` 的设备账号名单授权。
4. 云端从登录账号生成稳定的板端 `user_id`，再通过 `http://127.0.0.1:6001` 的可信 FRP 回环转发。
5. 只有云端读取 `BOARD_FACE_ADMIN_TOKEN`，并以 `X-Admin-Token` 发送到板端。

手机端不得再直连固定局域网 IP，也不得保存 `AI_GUARDIAN_FACE_ADMIN_TOKEN`。

## 2. App 到云端的请求

- 方法：`POST /api/face/enroll`
- 认证：`Authorization: Bearer <登录 Access Token>`
- 内容类型：`multipart/form-data`
- 字段：
  - `name`：1–64 个字符；不能包含路径分隔符、NUL 或控制字符。
  - `file`：JPG 或 PNG；单文件最大 8 MiB。
- `user_id`：客户端不得提交。云端使用当前登录账号生成，防止替其他账号写入。

主要响应：

- `200`：录入成功，返回 `success`、`recognitionStatus`、`photoCount` 和 `hint`。
- `400`：姓名、文件类型或图片内容无效。
- `401`：登录会话失效；App 只刷新并重试一次。
- `403`：当前账号不在设备授权名单。
- `413`：文件超过 8 MiB。
- `503`：FRP、板端服务或板端管理员配置不可用。

## 3. 云端部署位置与操作

发布包必须包含：

- `/root/wenxin_proxy.py`
- `/root/face_api.py`
- `/root/board_face_bridge.py`
- `/root/mqtt_access.py`
- `/etc/nginx/conf.d/api.aistar.asia.conf` 中 `/api/face/enroll` 的 9 MiB 专用上传入口

在阿里云创建私有环境文件：

```bash
install -m 600 deploy/board-face.env.example /etc/wenxin/board-face.env
vi /etc/wenxin/board-face.env
```

填写：

```text
BOARD_FACE_BASE_URL=http://127.0.0.1:6001
BOARD_FACE_ADMIN_TOKEN=<与板端一致的随机长令牌>
```

然后执行：

```bash
systemctl daemon-reload
systemctl restart wenxin.service
systemctl is-active wenxin.service
curl -fsS http://127.0.0.1:8899/health
```

不要把真实令牌写入命令历史、聊天、日志或仓库。`BOARD_FACE_BASE_URL` 只允许 `http://127.0.0.1:<显式端口>` 或 `localhost`，外部地址会被代码拒绝。

## 4. 板端部署位置与操作

板端启动 `src/ascend_board_server.py` 的环境必须包含：

```text
AI_GUARDIAN_FACE_ADMIN_TOKEN=<与云端一致的随机长令牌>
```

确认 FRP 的云端回环端口 `127.0.0.1:6001` 指向板端 HTTP 端口 5000，再重启 `guardian-board.service`。令牌只存在板端和云端私有环境文件。

## 5. 验收任务

### 本地与模拟器

1. 运行 `python -m unittest tests.test_board_face_bridge tests.test_face_cloud_api -v`。
2. 构建 Release HAP，确认 `BUILD SUCCESSFUL` 并核对产物哈希。
3. 安装到 API 24 模拟器并启动，确认 App 可正常进入个人中心；模拟器无法证明板端录入成功。

### 云端与开发板联调

1. 使用授权账号登录 App，在个人中心拍摄一张不超过 8 MiB 的人脸照片。
2. 预期 App 显示录入成功；板端响应的 `photoCount` 增加，`recognitionStatus` 为 `ready` 或可解释的降级状态。
3. 再上传同一账号另一角度照片，确认追加而非覆盖。
4. 用未授权账号测试，预期 `403`，板端图片和数据库不变化。
5. 临时停止 FRP 或板端服务，预期 App 收到可重试的服务不可用提示，不清除登录态。
6. 恢复服务后再次上传，确认无需重新安装 App 即可成功。
7. 在服务器与 App 日志中检查：不得出现 Access Token、管理员令牌或图片内容。

完成第 2 组检查后，才能宣称人脸录入端到端通过。
