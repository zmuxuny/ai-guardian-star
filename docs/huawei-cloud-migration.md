# 后端迁移华为云（RDS for MySQL + DCS Redis）改造清单

> 基线：分支 `feature/jyx-home`，提交 `f4dd5e5`（2026-11-12）
> 范围：只做现状梳理与改造评估，本文不包含任何代码改动。
> 结论先行：这不是“把 SQLite 连接字符串换掉”的工作。后端有 7 张业务表 + 1 套录像索引表，SQL 中大量使用 `BEGIN IMMEDIATE`、`PRAGMA`、`ON CONFLICT`、部分唯一索引和触发器；MQTT broker 的鉴权插件直接读写同一个 SQLite 文件。迁到 RDS + DCS 必须重写数据访问层、DDL 和 broker 鉴权链路。

---

## 1. 现状架构与数据落点

### 1.1 部署拓扑

| 角色 | 部署位置 | 关键配置 |
|---|---|---|
| Flask 账号/AI/录像代理服务 | 云服务器 `/opt/wenxin/app`，`wenxin.service`（gunicorn 2 worker × 4 thread，监听 127.0.0.1:8899） | `deploy/aliyun/wenxin.service` |
| MQTT broker | 同机 AMQTT 0.11.3，TLS 8883 | `deploy/aliyun/amqtt.yaml` |
| Nginx | 同机，443 → 8899 / 6001 / 6000 / 6011 | `deploy/aliyun/api.aistar.asia.conf` |
| 开发板（Ascend） | 经 frp 反向隧道接入云端 | `deploy/aliyun/frps.service`、`deploy/board/frpc-recovery.toml` |
| App | HarmonyOS，硬编码 `api.aistar.asia` 与服务器公网地址 | `entry/src/main/ets/config.ets:7,14,18` |

### 1.2 数据落点（三处，不要混为一谈）

| 存储 | 位置 | 内容 | 是否本次迁移 |
|---|---|---|---|
| `guardian_users.db` | 应用目录（`wenxin_proxy.py:98`） | 账号、会话、验证码、MQTT 授权、常用地址、AI 权限 | **是，迁 RDS** |
| `index.sqlite` | `RECORDING_ROOT`，默认 `/var/lib/guardian-recordings`（`recording_store.py:13,21`） | 本地录像片段索引 `segments/events/state` | **视部署形态**，见 6.4 |
| `guardian.db` | 开发板 `/root/ai_guardian/db/guardian.db`（`src/ascend_board_server.py:1168`） | 板端人脸特征 `t_face_feature` | 否，留在边缘 |
| `history.db` | 开发板录像数据目录（`src/guardian_history.py:75-100`） | 板端事件/录像/缺口记录 | 否，留在边缘 |

> 关键耦合：`deploy/aliyun/amqtt.yaml:14,18` 让 broker 的鉴权/主题插件直接打开 `guardian_users.db`。数据库一换，**broker 也必须改**，否则 App 领到凭据也连不上。

---

## 2. SQLite 表、字段与读写位置

### 2.1 账号库 `guardian_users.db`

建表入口统一在 `wenxin_proxy.py:103-186` 的 `get_db()`，它每个请求都会执行一次建表 + `PRAGMA table_info` + 可能的 `ALTER TABLE`（`wenxin_proxy.py:107-185`）。子模块通过 `create_*_schema(conn)` 追加自己的表。

#### t_user — 用户主表

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| username | TEXT PK | 手机号或管理员创建的用户名 |
| nickname | TEXT | 昵称，默认“用户+手机号后 4 位” |
| phone | TEXT | 手机号，可为空 |
| password_hash | TEXT NOT NULL | scrypt 格式，见 `security_utils.py:17-27` |
| avatar_path | TEXT | 历史字段，现恒为空串 |
| email | TEXT | 邮箱 |
| address | TEXT | 兼容旧版的单个地址，与 `t_saved_address` 默认项同步 |
| create_time | INTEGER NOT NULL | **毫秒**时间戳 |
| avatar_data | BLOB | 头像 JPEG 原始字节，上限 750 KB（`wenxin_proxy.py:95`） |
| avatar_mime | TEXT | 目前只允许 `image/jpeg` |
| avatar_updated_at | INTEGER | 毫秒时间戳，前端用它做缓存版本 |
| is_frozen | INTEGER NOT NULL DEFAULT 0 | 0/1 冻结标记 |

读写位置：

| 位置 | 操作 |
|---|---|
| `wenxin_proxy.py:382-412` `bearer_required` | 读：token 哈希 JOIN 会话，校验 `is_frozen` |
| `wenxin_proxy.py:221-231` `_user_json` | 读：组装返回体 |
| `wenxin_proxy.py:447-550` `/api/otp/send` | 读：手机号是否已注册 |
| `wenxin_proxy.py:599-660` `/api/password/otp/send` | 读：手机号是否存在 |
| `wenxin_proxy.py:750-819` `/api/password/reset` | 读 + 写：校验旧密码、更新 `password_hash` |
| `wenxin_proxy.py:822-944` `/api/contact/otp/send` | 读：手机号/邮箱是否被他人占用 |
| `wenxin_proxy.py:947-1044` `/api/contact/update` | 读 + 写：更新 `phone`/`email` |
| `wenxin_proxy.py:1047-1177` `/api/register` | 写：插入新用户 |
| `wenxin_proxy.py:1180-1229` `/api/login` | 读 + 写：按 username/phone/email 查人，必要时重算密码哈希 |
| `wenxin_proxy.py:1270-1283` `/api/me` | 读 |
| `wenxin_proxy.py:1286-1344` `/api/avatar` | 读 + 写：`avatar_data/mime/updated_at` |
| `wenxin_proxy.py:1363-1448` `/api/deleteUser` | 读 + 删 |
| `wenxin_proxy.py:1451-1492` `/api/updateUser` | 写：nickname / avatar_path / address |
| `wenxin_proxy.py:1495-1530` `/api/changePassword` | 读 + 写 |
| `wenxin_proxy.py:1907-2154` 管理后台 | 读/写/删：列表、创建、改名、改资料、冻结、删除 |
| `address_service.py:53-57,87` | 读 `address`、写回默认地址 |
| `ai_permissions.py:27` | 读：仅做账号存在性检查 |
| `mqtt_access.py:59-65` | 读：`valid_grant` 中 JOIN 校验冻结/存在 |
| `deploy/ops_monitor.py:129-146` | 读：短信计数（只读连接） |

#### t_session — 登录会话

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| access_token_hash | TEXT PK | access token 的 SHA-256 hex（64 字符） |
| refresh_token_hash | TEXT NOT NULL UNIQUE | refresh token 的 SHA-256 hex |
| username | TEXT NOT NULL | 归属用户 |
| access_expires_at | INTEGER NOT NULL | **秒**时间戳，TTL 15 分钟 |
| refresh_expires_at | INTEGER NOT NULL | **秒**时间戳，TTL 30 天 |
| create_time | INTEGER NOT NULL | **秒**时间戳 |

读写位置：

| 位置 | 操作 |
|---|---|
| `wenxin_proxy.py:193-218` `_new_session` | 写：登录/注册/刷新时插入 |
| `wenxin_proxy.py:382-412` | 读：每次 Bearer 鉴权 |
| `wenxin_proxy.py:424-445` `/api/mqtt/credentials` | 读：取 access 过期时间，限制 MQTT 凭据 TTL |
| `wenxin_proxy.py:750-819` 重置密码 | 删：踢掉该用户全部会话 |
| `wenxin_proxy.py:947-1044` 改联系方式 | 删：踢掉当前设备以外的会话 |
| `wenxin_proxy.py:1232-1267` `/api/refresh` | 删旧 + 插新；同时把 `t_mqtt_grant` 挂到新 token 哈希 |
| `wenxin_proxy.py:1347-1360` `/api/logout` | 删单条 |
| `wenxin_proxy.py:1363-1448` 注销、`1495-1530` 改密、`2043-2154` 管理后台 | 删：按 username 批量删 |
| `mqtt_access.py:59-65` | 读：JOIN 校验会话未过期 |

#### t_sms_challenge — 注册/找回密码短信挑战

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| challenge_hash | TEXT PK | challengeId 的 SHA-256 hex |
| phone | TEXT NOT NULL | 手机号 |
| purpose | TEXT NOT NULL | `register` / `reset` / `reset_verified` / `blocked` |
| requester_ip | TEXT NOT NULL | 频控用 |
| sent_at | INTEGER NOT NULL | **秒** |
| expires_at | INTEGER NOT NULL | **秒**，5 分钟 |
| failed_attempts | INTEGER NOT NULL DEFAULT 0 | 最大 5 次 |
| checking_at | INTEGER | 校验中的租约时间戳（防并发重复校验） |
| consumed_at | INTEGER | 已消费时间戳 |

索引：`idx_sms_challenge_phone_sent(phone, sent_at)`、`idx_sms_challenge_ip_sent(requester_ip, sent_at)`（`wenxin_proxy.py:151-158`）。

读写位置：`wenxin_proxy.py:447-550`（发送、频控、写 blocked）、`553-596`（频控检查）、`599-660`（找回密码发送）、`663-747`（校验）、`750-819`（重置）、`1047-1177`（注册校验与消费）。清理是每次发送前 `DELETE ... WHERE sent_at < now-40d`（`wenxin_proxy.py:468,615`）。

#### t_contact_challenge — 换绑手机号/邮箱挑战

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| challenge_hash | TEXT PK | challengeId 的 SHA-256 hex |
| username | TEXT NOT NULL | 发起人 |
| kind | TEXT NOT NULL | `phone` / `email` |
| value | TEXT NOT NULL | 目标联系方式 |
| code_hash | TEXT | 邮箱验证码哈希（`sha256(challengeId + ':' + code)`） |
| requester_ip | TEXT NOT NULL | 频控 |
| sent_at | INTEGER NOT NULL | **秒** |
| expires_at | INTEGER NOT NULL | **秒**，5 分钟 |
| failed_attempts | INTEGER NOT NULL DEFAULT 0 | |
| checking_at | INTEGER | 校验租约 |
| consumed_at | INTEGER | 已消费 |

索引：`idx_contact_value_sent(kind, value, sent_at)`、`idx_contact_ip_sent(requester_ip, sent_at)`（`wenxin_proxy.py:174-181`）。

读写位置：`wenxin_proxy.py:822-944`（发送 + 频控 + 预算）、`947-1044`（换绑校验）、`1363-1448`（注销时校验）、`447-550` / `599-660`（全局短信预算统计 `WHERE kind='phone'`）。

#### t_mqtt_grant — App 短期 MQTT 凭据

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| client_id | TEXT PK | `guardian_app_<24hex>` |
| password_hash | TEXT NOT NULL | 随机密码的 SHA-256 hex |
| access_token_hash | TEXT NOT NULL UNIQUE | 绑定的登录会话 |
| expires_at | INTEGER NOT NULL | **秒**，最长 300 秒 |

定义：`mqtt_access.py:26-32`；签发 `mqtt_access.py:35-45`（先删同会话旧凭据）；校验 `mqtt_access.py:48-70`（每次 MQTT 投递都调用）。刷新会话时改写绑定：`wenxin_proxy.py:1259-1260`。

#### t_saved_address — 常用住处

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| id | INTEGER PK AUTOINCREMENT | 前端用它做 ID |
| username | TEXT NOT NULL | 归属 |
| label | TEXT NOT NULL | 1–24 字 |
| detail | TEXT NOT NULL | 5–300 字 |
| latitude / longitude | REAL | 可空，成对出现 |
| is_default | INTEGER NOT NULL DEFAULT 0 | 每用户最多一个 |
| version | INTEGER NOT NULL DEFAULT 1 | 乐观锁 |
| created_at / updated_at | INTEGER NOT NULL | **毫秒** |

约束：普通索引 `idx_saved_address_owner`；**部分唯一索引** `idx_saved_address_default ON t_saved_address(username) WHERE is_default=1`；触发器 `saved_address_delete_user`（`address_service.py:10-22`）。上限 20 条（`address_service.py:7,115-117`）。

读写位置：全部在 `address_service.py` —— `_bootstrap` 49-57、`_owned` 60-69、`_default` 72-76、`_snapshot` 79-88、路由 91-169。

#### t_ai_permission — AI 数据权限

| 字段 | SQLite 类型 | 说明 |
|---|---|---|
| username | TEXT PK | 归属 |
| enabled | INTEGER NOT NULL DEFAULT 0 | 是否开启 AI |
| access_level | TEXT NOT NULL DEFAULT 'privacy' | `basic` / `privacy` / `full` |
| version | INTEGER NOT NULL DEFAULT 1 | 乐观锁，AI 请求必须带对 |

触发器：`ai_permission_delete_user`、`ai_permission_rename_user`（`ai_permissions.py:14-23`）。

读写位置：`ai_permissions.py:26-41`（读）、`97-138`（读写，含 `ON CONFLICT` upsert）；`wenxin_proxy.py:1569-1574` `/ai/chat` 前后各校验一次权限版本。

### 2.2 录像索引库 `index.sqlite`（`recording_store.py`）

| 表 | 字段 | 说明 |
|---|---|---|
| segments | id TEXT PK、start_ms、end_ms、filename TEXT UNIQUE、size | 已落盘的 MP4 片段 |
| events | id INTEGER PK、kind、start_ms、end_ms、last_seen_ms | 由 MQTT 告警推导的事件区间 |
| state | key TEXT PK、value TEXT | 目前只有 `recorder` 一条 JSON 状态 |

- 建表：`recording_store.py:23-32`
- 写入：`set_state` 43-46（`INSERT OR REPLACE`）、`ingest_alert` 49-80（MQTT 告警入索引）、`prune` 128-145
- 读取：`snapshot` 83-125；`recording_api.py:219-220` 本地回退模式读 `segments`

### 2.3 板端数据库（不迁，但会影响接口行为）

- `src/ascend_board_server.py:1216-1222`：`t_face_feature(user_id PK, name, feature_blob BLOB, create_time)`，板端人脸库。
- `src/guardian_history.py:74-100`：`recordings / events / gaps / event_recordings / history_meta`，板端录像库。

---

## 3. HTTP 接口清单

### 3.1 云端 Flask（`wenxin_proxy.py` + 子模块注册）

认证图例：`Bearer` = `bearer_required`（access token 查 `t_session`）；`Admin` = Flask session cookie；`无` = 公开；`签名` = URL HMAC 签名。

| 方法 | 路径 | 认证 | 用途 |
|---|---|---|---|
| POST | `/api/mqtt/credentials` | Bearer + 白名单 | 为当前登录会话签发 300 秒内只订阅 `ai_guardian/alerts/#` 的 MQTT 账号密码（`wenxin_proxy.py:424`） |
| POST | `/api/otp/send` | 无 | 注册第一步：给未注册手机号发短信验证码，含多层频控与全局预算（`447`） |
| POST | `/api/password/otp/send` | 无 | 忘记密码第一步：给已注册手机号发验证码（`599`） |
| POST | `/api/password/otp/verify` | 无 | 忘记密码第二步：校验验证码，通过后 challenge 变为 `reset_verified`（`663`） |
| POST | `/api/password/reset` | 无 | 忘记密码第三步：设置新密码并踢掉该账号全部会话（`750`） |
| POST | `/api/contact/otp/send` | Bearer | 换绑手机号/邮箱第一步：发短信或邮件验证码，含频控与预算（`822`） |
| POST | `/api/contact/update` | Bearer | 换绑第二步：校验验证码并更新 `phone`/`email`，踢掉其他设备会话（`947`） |
| POST | `/api/register` | 无 | 注册：校验短信 challenge，创建用户并直接下发 token（`1047`） |
| POST | `/api/login` | 无 | 账号密码登录，支持 username/phone/email 三选一（`1180`） |
| POST | `/api/refresh` | 无（凭 refreshToken） | 轮换 access/refresh token，并迁移 MQTT 凭据绑定（`1232`） |
| GET | `/api/me` | Bearer | 读取当前用户资料（`1270`） |
| GET | `/api/avatar` | Bearer | 读取头像，返回 base64（`1286`） |
| POST | `/api/avatar` | Bearer | 上传 JPEG 头像，存进 `t_user.avatar_data`（`1286`） |
| POST | `/api/logout` | Bearer | 删除当前会话（`1347`） |
| POST | `/api/deleteUser` | Bearer | 注销账号：凭联系方式验证码校验后删除用户及其会话（`1363`） |
| POST | `/api/updateUser` | Bearer | 更新昵称/头像路径/地址（`1451`） |
| POST | `/api/changePassword` | Bearer | 旧密码换新密码，踢掉全部会话（`1495`） |
| POST | `/api/addresses/list` | Bearer | 列出常用住处，并把默认地址同步回 `t_user.address`（`address_service.py:151`） |
| POST | `/api/addresses/save` | Bearer | 新增/编辑地址，带乐观锁与 20 条上限（`156`） |
| POST | `/api/addresses/default` | Bearer | 切换默认地址（`161`） |
| POST | `/api/addresses/delete` | Bearer | 删除地址，默认地址被删后自动补位（`166`） |
| POST | `/api/ai/settings/read` | Bearer | 读取 AI 开关/权限级别/版本（`ai_permissions.py:98`） |
| POST | `/api/ai/settings/save` | Bearer | 保存 AI 设置，版本冲突返回 409（`109`） |
| POST | `/ai/chat` | Bearer | AI 对话：权限校验 → 脱敏 → 阿里云内容安全 → 扣子流式接口 → 输出审核（`wenxin_proxy.py:1630`） |
| POST | `/api/recordings/query` | Bearer + 白名单 | 查询近 7 天异常录像片段（`recording_api.py:73`） |
| POST | `/api/recordings/stream-url` | Bearer + 白名单 | 签发 10 分钟有效的播放 URL（`135`） |
| GET | `/api/recordings/stream/<id>` | 签名 | 按 Range 透传板端 MP4，供播放器拖动（`154`） |
| POST | `/api/recordings/media` | Bearer + 白名单 | 下载/播放指定片段；本地模式会用 ffmpeg 裁剪（`194`） |
| POST | `/api/face/enroll` | Bearer + 白名单 | 上传人脸照片，转发到板端登记（`face_api.py:36`） |
| GET | `/health` | 无 | 健康检查，返回 `status/service/time`（`wenxin_proxy.py:1533`） |
| GET | `/favicon.ico` | 无 | 返回 204（`1538`） |
| GET / POST | `/admin/login` | 无 | 管理后台登录页/提交（`1844`） |
| GET | `/admin/logout` | 无 | 退出管理后台（`1859`） |
| GET | `/admin` | Admin | 管理后台单页（`1899`） |
| GET | `/admin/api/users` | Admin | 用户列表，含会话数、最后登录、哈希方案（`1907`） |
| POST | `/admin/api/users` | Admin | 创建用户（`2007`） |
| GET / POST / DELETE | `/admin/api/users/<username>/avatar` | Admin | 读取/上传/删除任意用户头像（`1944`） |
| PUT | `/admin/api/users/<username>` | Admin | 修改资料或改用户名（改名会清会话）（`2043`） |
| DELETE | `/admin/api/users/<username>` | Admin | 删除用户（`2138`） |
| POST | `/admin/api/users/<username>/reset-password` | Admin | 重置为固定初始密码并踢会话（`2080`） |
| POST | `/admin/api/users/<username>/freeze` | Admin | 冻结/解冻账号（`2106`） |

### 3.2 板端 FastAPI（`src/ascend_board_server.py`，经 Nginx/frp 对外或由云端 bridge 调用）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/` | 板端调试首页 |
| GET | `/api/stats` | 板端实时统计（FPS、摔倒/久坐/陌生人计数、人脸、语音状态） |
| GET | `/video_feed` | MJPEG 连续视频流 |
| GET | `/video_frame` | 单帧 JPEG |
| WS | `/ws/intercom` | 语音对讲 |
| GET | `/api/history/status` | 录像机状态（云端 `board_recording_bridge.py:170` 调用） |
| GET | `/api/history/events` | 事件分页查询（云端 `_pages` 调用） |
| GET | `/api/history/events/{id}` | 事件详情（含关联录像） |
| GET | `/api/history/recordings` | 录像分页查询 |
| GET | `/api/history/recordings/{id}/video` | MP4 下载/Range 播放（云端 `open_media` 调用） |
| GET | `/api/history/events/{id}/snapshot` | 预留，当前返回 503 |
| GET | `/api/continuous/*` | 24 小时连续录像查询，同一套 router（前缀 `/api/continuous`，`ascend_board_server.py:896-899`） |
| POST | `/api/face/enroll` | 板端人脸登记（`X-Admin-Token`） |
| DELETE | `/api/face/{user_id}` | 板端人脸删除 |
| GET | `/api/face/list` | 板端人脸列表 |

### 3.3 Nginx 额外暴露的路径（不经过 Flask）

`/device/` → 板端 6001；`/video_feed`、`/video_frame`、`/api/stats`、`/video_preview`、`/video_preview_full` → 板端/相机中继；`/ws/intercom` → 6000（`deploy/aliyun/api.aistar.asia.conf:60-108`）。这些接口的限流、HTTPS 证书迁移到华为云时要一并重建。

---

## 4. MQTT 主题与消息格式

### 4.1 鉴权与授权模型

- Broker：AMQTT 0.11.3，TLS 8883，配置 `deploy/aliyun/amqtt.yaml`。
- 开发板身份：用户名 `ascend_board`，密码来自 `/etc/amqtt/passwd`（FileAuthPlugin），只允许发布。
- App 身份：`guardian_app_*`，密码为服务端签发的随机串，凭据存在 `t_mqtt_grant`，只允许订阅 `ai_guardian/alerts/#`，禁止发布、遗嘱、持久会话（`guardian_mqtt_plugin.py:23-39`、`mqtt_access.py:73-81`）。
- 每次投递都会调用 `valid_grant()` 重新校验（`guardian_mqtt_plugin.py:59-61`），即**每条消息一次数据库查询**。

### 4.2 主题与载荷

| 主题 | 发布者 | 频率限制 | 消息体 |
|---|---|---|---|
| `ai_guardian/alerts/fall` | 开发板 | 5 秒 | `{"event":"fall_detected","timestamp":"<str(datetime.now())>"}` |
| `ai_guardian/alerts/stranger` | 开发板 | 5 秒 | `{"event":"stranger_detected","timestamp":"...","person_id":<id|null>,"score":<float|null>}` |
| `ai_guardian/alerts/sit` | 开发板 | 30 秒 | `{"event":"sit_detected","timestamp":"...","duration_seconds":<float>,"person_id":<id|null>}` |
| `ai_guardian/alerts/face` | 开发板 | 10 秒 | `{"event":"face_recognized","timestamp":"...","name":<姓名|null>,"score":<float|null>,"person_id":<id|null>}` |
| `ai_guardian/alerts/heartbeat` | 开发板 | 10 秒（可配 5–60） | `{"event":"heartbeat","deviceId":"ascend_board","timestamp":<epoch ms 整数>,"sequence":<int>,"cameraConnected":<bool>,"aiRunning":<bool>}`，QoS 1，retain=false |
| `ai_guardian/recordings/ready` | 开发板 | 事件驱动 | `{"event":"recording_ready","timestamp":"...","recording_id":"...","event_ids":[...],"download_path":"/api/history/recordings/<id>/video"}` |

来源：`src/ascend_main_other.py:93-98,1609-1666`、`src/guardian_heartbeat.py:23-34,58-63`。

### 4.3 需要注意的现状

1. **时间戳格式不统一**：告警类用本地时间字符串（无时区），心跳用 UTC 毫秒整数。迁云后如果跨时区部署，告警时间会歧义。
2. **QoS 不一致**：告警默认 QoS 0，心跳显式 QoS 1；断线时告警会丢。
3. **`recordings/ready` 不在 App 订阅范围内**：App 只订阅 `ai_guardian/alerts/#`，所以这个主题目前只有 broker 插件和录像服务在用。
4. **云端仅消费 `alerts/#` 建索引**：`recording_store.ingest_alert` 靠 `event/alert_type/type` 字段关键词判断 `fall`/`sedentary`（`recording_store.py:61-70`）。
5. **broker 直接读账号库**：`amqtt.yaml:14,18` 与 `guardian_mqtt_plugin.py:14` 都把数据库路径写死为 `/opt/wenxin/app/guardian_users.db`。

---

## 5. 华为云目标架构

| 组件 | 华为云产品 | 说明 |
|---|---|---|
| 关系型数据库 | RDS for MySQL 8.0 | 承载 `t_user / t_session / t_sms_challenge / t_contact_challenge / t_mqtt_grant / t_saved_address / t_ai_permission` |
| 缓存 | DCS Redis 5.0/6.0 | 会话、MQTT 凭据、验证码挑战、频控计数 |
| 应用服务器 | ECS | Flask + AMQTT + Nginx（或 ELB + Nginx） |
| 网络 | VPC + 安全组 | RDS/DCS 只开内网，ECS 内网访问 |
| 证书 | SCM 或沿用现有 Let's Encrypt | App 内置 CA 校验，域名变更需同步 |
| 对象存储（可选） | OBS | 头像、录像片段外置 |

---

## 6. 改造清单（按优先级）

### P0 — 不做就无法启动或直接数据事故

#### P0-1 抽象数据访问层，替换 `sqlite3` 直连

- 现状：`wenxin_proxy.py:105` 每个请求 `sqlite3.connect(DB_PATH)`；`mqtt_access.py:57` 用 SQLite URI 只读打开；`address_service.py`、`ai_permissions.py`、`recording_store.py` 各自持连接。
- 改造：
  - 新增 `db.py`（连接池 + `get_db()` 上下文 + 事务封装 + `dict` 游标），全项目只保留一个入口。
  - 占位符 `?` → `%s`；`conn.execute(...).fetchone()` 的 `sqlite3.Row` 访问方式改为 `DictCursor` 或自定义 Row。
  - 异常 `sqlite3.Error` → `pymysql.MySQLError`（`address_service.py:144`、`ai_permissions.py:133`、`mqtt_access.py:69`）。
  - `conn.executescript()`（`address_service.py:11`、`ai_permissions.py:15`、`recording_store.py:23`）不能用，要拆成多条 `execute` 或交给迁移脚本。
  - 连接池大小与 gunicorn 配置匹配：2 worker × 4 thread，建议池 8–16，并设置 `connect_timeout`、`read_timeout`、`wait_timeout`。
- 验收：全项目 `grep sqlite3` 仅剩录像本地回退与板端代码。

#### P0-2 建表/DDL 改成 MySQL 方言

现状 `get_db()` 每请求执行建表，迁 MySQL 后必须改成**启动时一次性迁移**（或独立 `migrate.py`），否则每请求打一次 DDL。

逐条差异：

| 现状 | 位置 | MySQL 写法 |
|---|---|---|
| `TEXT PRIMARY KEY` | `wenxin_proxy.py:108-137` | `VARCHAR(64) PRIMARY KEY`（token 哈希固定 64 字符）；`username`/`phone`/`email` 用 `VARCHAR(64/20/254)` |
| `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` | `wenxin_proxy.py:119-127` | 启动迁移脚本读取 `information_schema.columns`，或直接一次性建全列 |
| `INTEGER PRIMARY KEY AUTOINCREMENT` | `address_service.py:13` | `BIGINT AUTO_INCREMENT PRIMARY KEY` |
| 部分唯一索引 `... WHERE is_default=1` | `address_service.py:18-19` | MySQL 不支持部分索引。改用生成列 `is_default_active TINYINT GENERATED ALWAYS AS (IF(is_default=1,1,NULL)) STORED` + `UNIQUE(username, is_default_active)` |
| 三个触发器 | `address_service.py:20-21`、`ai_permissions.py:19-22` | MySQL 触发器必须 `FOR EACH ROW BEGIN ... END`；`AFTER UPDATE OF username` 不支持列级触发，要改成 `AFTER UPDATE ON t_user` + `IF OLD.username <> NEW.username THEN`。更推荐改用外键 `ON DELETE CASCADE` / `ON UPDATE CASCADE` |
| `INSERT OR REPLACE INTO state` | `recording_store.py:45` | MySQL `REPLACE INTO`（会删行重插）或 `INSERT ... ON DUPLICATE KEY UPDATE` |
| `ON CONFLICT(username) DO UPDATE SET ... excluded.x` | `ai_permissions.py:123-126` | `INSERT ... ON DUPLICATE KEY UPDATE enabled=VALUES(enabled), access_level=VALUES(access_level), version=VALUES(version)`（8.0.20+ 用行别名 `AS new`） |
| `BLOB` 头像 | `wenxin_proxy.py:121` | `MEDIUMBLOB`（上限 750 KB），并确认 RDS 的 `max_allowed_packet` ≥ 4 MB |
| `REAL` 经纬度 | `address_service.py:13-16` | `DOUBLE` |
| `INTEGER` 布尔位 | `is_default` / `is_frozen` / `enabled` | `TINYINT(1)` |
| 默认字符集/排序 | 全部表 | **显式 `utf8mb4` + `utf8mb4_bin`（或 `utf8mb4_0900_as_cs`）**。SQLite TEXT 是二进制比较，MySQL 8 默认 `utf8mb4_0900_ai_ci` 不区分大小写，会让 `username` 唯一约束与登录匹配行为变化 |

补充：`t_user` 的 `phone`、`email` 当前没有索引，但登录会按它们查询（`wenxin_proxy.py:1190`），迁移时补 `INDEX(phone)`、`INDEX(email)`。

#### P0-3 配置与凭据注入

- 现状：`DB_PATH` 写死为应用目录（`wenxin_proxy.py:98`），broker 配置写死绝对路径（`deploy/aliyun/amqtt.yaml:14,18`）。
- 改造：新增环境文件（权限 0600，只放服务器，不进仓库），经 `EnvironmentFile` 注入：
  - `DB_HOST / DB_PORT / DB_NAME / DB_USER / DB_PASSWORD / DB_CHARSET`
  - `REDIS_HOST / REDIS_PORT / REDIS_PASSWORD / REDIS_DB / REDIS_SSL`
- 新增依赖：`pymysql`（或 `mysqlclient`）+ 连接池（`DBUtils` 或 `SQLAlchemy`）+ `redis`。写入 `requirements-production.txt`（当前只有 Flask/flask-cors/requests/gunicorn）。
- 安全：RDS/DCS 只开 VPC 内网，安全组只放行应用 ECS；InnoDB 走内网加密或至少不回显密码；`brew` 不要读取控制台打印的连接串。

#### P0-4 MQTT broker 鉴权改 Redis（否则每条消息打一次 MySQL）

- 现状：`guardian_mqtt_plugin.py:27` → `mqtt_access.valid_grant()`（`mqtt_access.py:48-70`）每次投递都打开 SQLite 做三表 JOIN。板端每 10 秒心跳 + 高频告警，直接迁成 MySQL 会产生持续小查询。
- 改造：
  - `t_mqtt_grant` → Redis：`mqtt:grant:<client_id>` → `{password_hash, access_token_hash, expires_at}`，TTL = 剩余有效期（≤300 秒）。
  - 会话校验 → `sess:access:<hash>`（见 P0-5），`valid_grant` 只做两次 Redis 读 + 一次冻结标记读。
  - `guardian_mqtt_plugin.py` 的 `Config.database` 改成 Redis 连接参数；`amqtt.yaml` 同步改。
  - 保留 `permitted_topic` 的纯函数逻辑（`mqtt_access.py:73-81`），不动语义。
- 验收：MQTT 发布/订阅压测时 MySQL QPS 不随消息量线性增长；退出登录、冻结、删除账号后 1 秒内停止投递（当前语义要保持）。

#### P0-5 登录会话迁 Redis

- 现状：`t_session` 同时承担“access token 是否有效”“refresh token 是否有效”“冻结用户是否还能用”三个职责。
- 改造：
  - `sess:access:<sha256>` → `{username, expires_at}`，TTL 15 分钟。
  - `sess:refresh:<sha256>` → `{username, access_hash}`，TTL 30 天。
  - `sess:user:<username>` → Set，保存该用户所有 access_hash，用于“改密/重置/注销/冻结/换绑”时批量失效（对应 `wenxin_proxy.py:806,1033,1521,2072,2125,2149`）。
  - 冻结状态要**即时生效**：维护 `user:frozen:<username>` 标记，冻结/解冻时写/删（`wenxin_proxy.py:2106-2135`），`bearer_required` 先查标记，未命中再回源 MySQL 并回填短 TTL。
- 验收：并发登录/刷新/登出后旧 token 立即失效；冻结后 1 次请求内生效。

### P1 — 功能正确性与运维必需

#### P1-1 验证码挑战与短信频控迁 Redis

- 现状：`t_sms_challenge` / `t_contact_challenge` 用“插入行 + 时间窗口 SUM”实现频控（`wenxin_proxy.py:469-507,560-596,870-908`），并用 `BEGIN IMMEDIATE` 串行化。
- 改造：
  - challenge 本体 → Redis：`sms:ch:<hash>` / `contact:ch:<hash>`，TTL 5 分钟，含 `attempts/checking_at/consumed_at`，用 Lua 或 `WATCH/MULTI` 原子更新。
  - 频控 → 计数器：`rate:sms:phone:<phone>:1m/1h/1d`、`rate:sms:ip:<ip>:1h`、`counter:sms:day:<YYYYMMDD>`、`counter:sms:month:<YYYYMM>`，`INCR` + `EXPIRE`。
  - `purpose='blocked'` 的行目前用于“消耗额度但不发短信”，Redis 方案直接 `INCR` 即可，不再落库。
  - 注意跨月口径：现状按 UTC+8 自然月（`wenxin_proxy.py:463-467,555-559`），Redis key 必须用同一个时区生成月份。
- 验收：与现状同口径的 1 分钟/1 小时/1 天/1 月限流与 100/200 全局预算；并发 10 个请求只放行 1 条。

#### P1-2 并发正确性重写

`BEGIN IMMEDIATE` 共 22 处（`wenxin_proxy.py` 20 处、`address_service.py:99`、`ai_permissions.py:118`）。SQLite 用它提前拿写锁，MySQL 没有等价语义，需要逐个改写：

| 场景 | 位置 | MySQL 方案 |
|---|---|---|
| 频控“先查后插” | `wenxin_proxy.py:462-535` | Redis 原子 `INCR`（推荐），或对 phone 建唯一计数器行 `SELECT ... FOR UPDATE` |
| 注册用户名唯一 | `wenxin_proxy.py:1128-1145` | 捕获 `Duplicate entry`（errno 1062）转 409 |
| 地址默认唯一 | `address_service.py:122-135` | 生成列唯一索引 + 捕获 1062 |
| 地址乐观锁 | `address_service.py:67-68` | 保留 `version` 条件更新，检查 `rowcount` |
| AI 权限版本 | `ai_permissions.py:119-127` | 保留 version 比较；upsert 用 `ON DUPLICATE KEY UPDATE` |
| 会话轮换 | `wenxin_proxy.py:1241-1261` | 删除旧 refresh + 插入新会话放在同一事务，Redis 下用 `MULTI` |

#### P1-3 数据迁移脚本

- 从 `guardian_users.db` 读、写 RDS：
  - `t_user`、`t_saved_address`、`t_ai_permission` 必须逐行迁；`avatar_data` 按二进制迁。
  - `create_time` 是毫秒、`t_session.create_time` 是秒、`t_sms_challenge.sent_at` 是秒——**原样保留整数，不要转 DATETIME**。
  - 密码哈希 `scrypt$...` 原样迁，`security_utils.py:30-35` 支持旧明文，不要做二次哈希。
  - `t_session`、`t_mqtt_grant` 建议不迁（短生命周期，强制重新登录更安全）。
  - `t_sms_challenge`、`t_contact_challenge` 可不迁（40 天后自然清空）。
  - 迁完后校验收件：行数、`MAX(id)`、`AUTO_INCREMENT` 要大于已迁最大 id。
- 迁移期间停写窗口：先停 `wenxin.service` 与 `amqtt.service`，再跑脚本，最后切配置。

#### P1-4 运维脚本与服务替换

| 现有 | 位置 | 处理 |
|---|---|---|
| SQLite 在线备份 timer | `deploy/wenxin-sqlite-backup.service/.timer`、`deploy/sqlite_maintenance.py` | 停用；改用 RDS 自动备份 + 时间点恢复 |
| 监控读取 SQLite 备份 | `deploy/ops_monitor.py:118-126` `_backup_metrics` | 删除或改为调用 RDS 备份 API |
| 监控读取短信计数 | `deploy/ops_monitor.py:129-146` `_sms_counts` | 改读 Redis 计数器（见 P1-1） |
| 监控 systemd/nginx/journald | `deploy/ops_monitor.py:90-107,149-165` | 迁云后保留，但证书路径、服务名要按新拓扑改 |
| 部署脚本必备文件清单 | `deploy/deploy-production.sh:18-37` | 当前**缺少** `address_service.py`、`ai_permissions.py`、`recording_api.py`、`recording_store.py`、`board_recording_bridge.py`、`guardian_mqtt_plugin.py`；迁移前必须补齐，否则部署即失败 |
| 回滚逻辑 | `deploy/deploy-production.sh:92-135` | 只回滚文件与服务，迁移后要加“数据库切换回滚开关”（读环境变量决定用 SQLite 还是 MySQL） |

#### P1-5 网络拓扑：两个 bridge 强制 localhost

- `board_recording_bridge.py:42` 与 `board_face_bridge.py:38` 都要求 base URL 的 host 是 `127.0.0.1`/`localhost`，说明云端依赖 frp 把板端端口映射到本机回环。
- 迁到华为云后必须重建 `frps`（`deploy/aliyun/frps.service`，配置在服务器 `/etc/frp/frps.toml`，仓库未含）与板端 `frpc`（`deploy/board/frpc-aliyun.service`）。
- 同时：开发板 MQTT 地址写死为旧服务器 IP（`src/ascend_main_other.py:88`），换云要改板端配置并重启；App 端 `entry/src/main/ets/config.ets:7,14,18` 同样写死，域名/证书不变则可不动。
- 安全组要放通：443（ELB/Nginx）、8883（板端 MQTT）、6000/6001/6011 仅内网。

### P2 — 可延后，但建议同期做

#### P2-1 头像二进制外置到 OBS

- 现状：`avatar_data MEDIUMBLOB` 存在 `t_user`（`wenxin_proxy.py:1293-1330`）。RDS 存 750 KB 二进制会让备份变大、主从复制变慢。
- 改造：头像上传到 OBS，`t_user.avatar_path` 存对象 key（该字段已存在但恒为空），`avatar_data` 改空或删列；`/api/avatar` 与 `/admin/api/users/<username>/avatar` 改读写 OBS。
- 注意：nginx 当前 `client_max_body_size 1m`（`api.aistar.asia.conf:44,169`），base64 后可能超限，外置后可放宽。

#### P2-2 录像索引与文件存储

- 云端 `recording_store.py` 的 `index.sqlite` 只在不配置 `BOARD_RECORDING_BASE_URL` 的“本地回退模式”下使用（`recording_api.py:41-66,218-247`）。
- 只要继续用板端录像（当前生产形态），**不需要把 `segments/events/state` 迁去 RDS**；但要确认新环境 `RECORDING_ROOT` 不存在或明确禁用本地回退，避免误建本地库。
- 如果未来要把录像文件上 OBS，则要重写 `recording_api.py` 的 Range 透传与 `board_recording_bridge.open_media`。

#### P2-3 测试改造

| 测试 | 依赖点 | 改造 |
|---|---|---|
| `test_wenxin_proxy.py:158,412,1088` | 直接改 `proxy.DB_PATH` 并用 `proxy.sqlite3.connect` 查库 | 改为注入测试用 MySQL 库，或抽象 DAO 后 mock |
| `test_saved_addresses.py:20-23` | 临时 SQLite + 手建 `t_user` | 同上 |
| `test_ai_permissions.py:39,210` | 临时 SQLite + 合成触发器模拟失败 | 改为合成 MySQL 错误码 |
| `test_mqtt_access.py:28,43,85` | `mock.patch.multiple(proxy, DB_PATH=...)` | 改为 mock Redis 客户端 |
| `test_sqlite_maintenance.py` | 直接测备份脚本 | 迁移后删除，或改为验证 RDS 备份通道 |
| `test_ops_monitor.py` | 只测 `evaluate_metrics` 纯函数，不直接读 SQLite | 短信/备份指标的断言要随 P1-4 调整 |
| `tests/test_face_policy.py`、`test_history_storage.py` | 板端 SQLite | 不受影响 |

#### P2-4 文档与配置同步

- `deploy/aliyun/amqtt.yaml`、`deploy/aliyun/wenxin-sqlite-backup.*`、`docs/database-admin-access.md`（通篇按 SQLite 文件描述）、`docs/production-operations.md`、`README` 中的数据库说明都要同步。
- `docs/opengauss-migration-assessment.md` 是上一轮评估，可作为历史参考，不要把结论直接套到 MySQL 上。

---

## 7. 建议的实施顺序

1. **建立迁移分支与备份**：SQLite 快照（`sqlite_maintenance.py backup`）+ 代码回退点。
2. **P0-1 / P0-2**：先做 DAO 抽象和 MySQL DDL，在本地用 Docker MySQL 跑通全部单元测试。
3. **P0-3**：环境变量与连接池，先在测试 ECS 验证内网连通、SSL、时区。
4. **P0-5 → P0-4**：先会话后 MQTT，避免 broker 先改导致 App 全掉线。
5. **P1-1 → P1-2**：验证码与并发重写，重点做限流压测。
6. **P1-3**：停写窗口内迁移数据，校验行数与哈希。
7. **P1-4 / P1-5**：运维脚本、frp、安全组、证书。
8. **P2**：头像、测试、文档收尾。
9. **灰度**：先切内网测试域名，App 保持旧域名；验收通过后切 DNS，保留旧环境 7 天只读。

---

## 8. 验收清单

- [ ] 注册 → 登录 → 刷新 → 登出 → 改密 → 找回密码 → 注销全链路通过
- [ ] 同一手机号并发注册只成功 1 个，错误码为 409 而非 500
- [ ] 短信频控：1 分钟 1 条、1 小时 5 条、1 天 10 条、IP 1 小时 20 条、全局日 100/月 200 口径与现状一致
- [ ] 地址：新增/编辑/设默认/删除；默认地址唯一约束在并发下仍成立（409）
- [ ] AI 权限：旧版本号保存返回 409；关闭 AI 后 `/ai/chat` 返回 403
- [ ] MQTT：App 领取凭据后只订阅 `ai_guardian/alerts/#`，发布被拒；登出/冻结后停止投递
- [ ] 头像：读取、上传、管理后台删除；750 KB 边界
- [ ] 录像：查询、播放（Range）、下载、人脸登记（依赖 frp 隧道）
- [ ] 管理后台：列表、创建、改名（会话失效）、冻结、重置密码、删除
- [ ] 监控：RDS/DCS 连接数、慢查询、MQTT 消息量、`/health`
- [ ] 回滚演练：从 MySQL 切回 SQLite 只读快照，登录可用

---

## 9. 风险提示

1. **`get_db()` 每请求建表**（`wenxin_proxy.py:103-186`）在 MySQL 上会变成每请求一次元数据查询，必须前置到启动迁移。
2. **秒/毫秒混用**：`t_user.create_time` 是毫秒，`t_session`、验证码、MQTT 凭据是秒。迁移脚本若统一换算会破坏前端时间显示与过期判断。
3. **大小写排序规则**：不显式指定 `utf8mb4_bin`，`username` 唯一约束和登录匹配会出现 SQLite 没有的行为差异。
4. **冻结状态即时性**：会话进 Redis 后，若只靠缓存，冻结可能延迟生效；必须维护独立的冻结标记或在冻结时同步清理。
5. **broker 与 Web 共库**：`amqtt.yaml` 与 `guardian_mqtt_plugin.py` 的数据库配置必须与 Web 同时切换；先切 Web 会导致所有 App MQTT 连接失败。
6. **部署脚本缺文件**：`deploy/deploy-production.sh:18-37` 的必备清单不包含 6 个新模块，迁移时若直接复用会部署失败。
7. **`INSERT OR REPLACE` / `ON CONFLICT` / 部分唯一索引 / 列级触发器** 是四处典型的 SQLite 专属写法，必须逐条改写，不能靠驱动兼容层。
8. **录像与头像的体积**：RDS 单行存 750 KB 头像、板端 24 小时录像索引都在放大备份与恢复时间，建议 P2 提前评估。