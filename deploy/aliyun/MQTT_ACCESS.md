# App MQTT 告警访问

2026-09-08：当前 AMQTT 版本为 0.11.3。复用现有 Flask 登录会话，`POST /api/mqtt/credentials` 下发 300 秒以内的独立 MQTT 凭据，只订阅 `ai_guardian/alerts/#`，不能发布。凭据只驻留 App 内存；数据库仅存 SHA-256。退出登录、冻结/删除账号、删除允许账号或凭据到期后，broker 拒绝后续实时消息投递。

当前项目只有一块共享监护开发板，没有用户与设备绑定表。`/etc/wenxin/mqtt-users.json` 明确列出允许查看该板全部告警的账号。当前已授权且经登录核实的 username 为 `test`，因此配置为 `["test"]`。不能据手机号直接猜 username，也不能默认放开全部注册用户。新增独立家庭或第二块板时，应先实现设备绑定与分设备主题，再扩大开放范围。

## 部署顺序

1. 确认生产 broker 仍为 AMQTT 0.11.3；备份 `/opt/wenxin/app/wenxin_proxy.py`、`/etc/amqtt/amqtt.yaml`、`/etc/systemd/system/amqtt.service` 和现有 `/etc/wenxin/mqtt-users.json`（若存在），并用 SQLite backup API 备份数据库。备份目录只允许 root 访问。
2. 将仓库根目录 `wenxin_proxy.py`、`mqtt_access.py`、`guardian_mqtt_plugin.py` 放入 `/opt/wenxin/app/`。插件不需要新增 Python 依赖。
3. 隔离测试目录放入上述文件及 `security_utils.py`、`admin_panel.html`、`test_wenxin_proxy.py`、`test_mqtt_access.py`。使用 `/opt/wenxin/venv/bin/python test_mqtt_access.py -v` 运行。测试使用临时 SQLite 和 `127.0.0.1` 随机端口，不接触生产数据库或 8883；运行后清理临时测试目录。
4. 将本目录 `amqtt.yaml` 放入 `/etc/amqtt/amqtt.yaml`；`mqtt-users.json` 放入 `/etc/wenxin/mqtt-users.json`，权限 0600。原 `/etc/amqtt/passwd`、TLS CA/证书/私钥保持原样。原 `ascend_board` 密码继续认证；旧共享 `harmony_app` 身份退役。
5. 将本目录 `amqtt.service` 放入 `/etc/systemd/system/amqtt.service`，新增 `WorkingDirectory=/opt/wenxin/app` 与 `PYTHONPATH=/opt/wenxin/app`，保证插件可导入。执行 systemd daemon-reload。
6. 重启 `wenxin.service`，确认匿名请求凭据接口返回 401，登录且允许账号返回短时凭据、未允许账号返回 403。不要打印或保存响应密码、会话 token。接口会创建 `t_mqtt_grant`，不修改既有用户记录。
7. 重启 `amqtt.service` 加载插件与配置（不能用 API 的 HUP 代替 broker 重启）。确认原开发板自动重连，登录 App 能订阅真实心跳/告警，发布被拒绝，退出后停止投递。重启会短暂中断 MQTT；保留旧主机回退。
8. 构建并安装新版 App。`MqttManager` 在登录后领取凭据、到期前 30 秒重新领取并连接；断线重试也重新领取。CloudService 会话清理会断开 MQTT、清掉定时器和缓存。固定 Client ID 和共享密码已移除。

## 回滚

恢复备份的 `wenxin_proxy.py`、AMQTT YAML、systemd unit、allowlist 文件，再 daemon-reload 并重启两个服务。新 Python 模块与新增表可以保留，不影响旧服务；不要为了回滚代码覆盖已有新增业务数据。回滚后旧板端连接仍可用，但旧 App 缺少凭据的问题也会恢复。新 App 需要新接口和插件同时部署。

## 安全与验收边界

- AMQTT 0.11.3 的遗嘱发布不经过普通 PUBLISH 授权，离线缓存重放不经过 RECEIVE。App CONNECT 因此禁止遗嘱并强制 cleanSession；授权只允许固定告警订阅，保留消息仅在有效授权订阅时发送。
- PacketLoggerPlugin 可能记录 CONNECT 凭据，部署配置禁止启用。不要调试打印请求体、响应体或会话对象。
- 现有 broker 公共证书 SAN 已核实包含 IP `47.108.167.0` 与 DNS `api.aistar.asia`，App 保持 CA 校验并启用服务身份校验 `verify: true`。
- 到期/撤销保证停止新消息投递；空闲 TCP 连接可能继续存在。已在网络中的消息无法撤回。
- 测试验证 API 认证、账号授权、密码错误、发布拒绝、主题边界、遗嘱/持久会话拒绝、握手后到期/注销、原板端发布和 broker 重启。App 真机安装、TLS SDK 行为和真实告警呈现仍需现场验收。

## Release 混淆回归

2026-09-08 模拟器初次验收中，TLS 与订阅已成功，但 App 约每 0.4 秒重新领取凭据。已构建 HAP 的 `entry/build/default/outputs/default/symbol/release/entry-nameCache.json` 显示 `PropertyCache.expiresIn = "n4"`；服务端返回固定 JSON 键 `expiresIn`，App 混淆后读取另一名称，续期间隔得到 NaN，定时器立即执行。

`entry/obfuscation-rules.txt` 因此显式保留 CloudService 的外部 JSON 字段，`test_cloud_json_contract_fields_are_preserved_in_release_obfuscation` 检查响应及请求契约；客户端同时拒绝非有限的凭据有效期。构建后应检查产物 nameCache 中这些字段未改名，不能以 Debug 成功或接口测试通过代替 Release 验证。
