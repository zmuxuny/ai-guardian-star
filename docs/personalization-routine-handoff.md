# 作息提醒联调与交接

对应 [Issue #28 作息记录与反常提醒](https://github.com/zmuxuny/ai-guardian-star/issues/28) 和 [Issue #29 本地模型问答](https://github.com/zmuxuny/ai-guardian-star/issues/29)。个性化端负责采样回放、判定异常和发送提醒。模型端通过 [v5 HTTP 协议](personalization-message-format.md) 回传回答，App 通过现有 MQTT 告警订阅接收作息记录。

## 电脑上先跑

```powershell
python -m tools.routine_alert_demo
python -m tools.personalization_http_demo
python -m unittest discover -s tests -p "test_routine_alert_demo.py" -v
```

第一条命令从 14 天模拟作息中得到 07:00 的离床基线。正常和缺记录场景各 0 条，三种异常场景各 1 条。第二条命令验收 HTTP 问答、回执丢失、重启补发和版本乱序。更多用法见 [本机 HTTP 联调](personalization-http-demo.md)。

| 本次模拟规则 | 触发条件 | 演示触发点（UTC+8） |
| --- | --- | --- |
| 晚起 `late_wakeup` | 从 06:00 起有连续在床区记录，达到离床基线加 90 分钟 | 11 月 24 日 08:30 |
| 白天活动 `daytime_inactivity` | 09:00 至 20:00，在同一区域连续观测到坐姿或躺姿满 120 分钟 | 11 月 24 日 15:00 |
| 夜间卫生间停留 `night_bathroom_stay` | 22:00 至次日 06:00，连续观测到在卫生间满 30 分钟，可跨午夜 | 11 月 25 日 00:00 |

连续时长只由有效采样累积。漏采或观测不到会中断连续证据。同一已触发的持续事件只发一次，短暂缺测不会把它分成两条。时长是联调用的默认值，后两种类型和参数待真实采样联调确认。

## 板端采样对接

板端可先导出一份单设备、单人的 UTF-8 CSV，字段顺序为 `timestamp,zone,state`。规则按 UTC+8 的自然日分组，记录每 5 分钟对齐一次，时间须包含偏移量。使用 `bed`、`bathroom` 和其他已校准的稳定区域名。状态为 `standing`、`sitting`、`lying` 或 `absent`。遮挡、身份不确定、采集掉线、区域未映射时，留空该采样点或落为 `unknown,absent`。同一时刻在时区转换后只保留一条。下面的数据是示例。

```csv
timestamp,zone,state
2026-11-23T06:55:00+08:00,bed,lying
2026-11-23T07:00:00+08:00,living_room,standing
2026-11-23T07:05:00+08:00,unknown,absent
```

```powershell
python -m tools.routine_alert_demo --history history.csv --observations observations.csv
```

历史基线和验收日期分别导出。历史需覆盖晨间在床和离床过程，回放文件可覆盖多日。先看样本能否识别床区、卫生间以及离开，再用样本检验阈值和漏采处理。真实作息保留在设备或受控测试环境。

## App 测试消息

App 在既有单板授权订阅中识别 `ai_guardian/alerts/routine`。载荷是 UTF-8 JSON，字段为 `event: "routine_alert"`、`schema_version: "2"`、`event_id`、`alert_type`、`timestamp`、`reason`。MQTT 沿用原 `event_id` 和触发时间，按 QoS 1 发布，关闭 retain。App 按账号和原事件 ID 去重，在首页「近期事件」和「当天事件」显示类型、时间，详情显示原因。

```powershell
python -m tools.routine_alert_demo --mqtt
python -m tools.routine_alert_demo --mqtt --mqtt-preview --publish-port 1883
```

第一条输出固定日期的 MQTT 样例。第二条只向 `127.0.0.1` 上的测试 broker 发送，按当前日期生成标记为「模拟样例」的事件，方便当天显示。需安装 `paho-mqtt`。用开发版 App 对接同一个隔离 broker 和测试账号，检查三种提醒名称、中文原因与时间，然后重发同一条 JSON，核对只显示一条记录。实际板端发布前，在测试环境核对账号只接收其获授权的单板事件。

## 联调时双方各做什么

1. 周洋提供板端区域映射、无效采样标记以及一份脱敏回放样本。个性化端用同一脚本验收三条规则和实际误触发。
2. 周洋提供可启动的 v5 模型服务、提醒端口与绑定设备 ID，配置结果回传到个性化端。双方用 `peer` 模式联调 `ok`、`needs_help` 和超时。语音及拔网线后的问答需要实板验证。
3. App 侧在隔离环境验证实际收包和详情展示。三条规则、本机模拟 HTTP 与 MQTT 测试可在电脑上先复现。

## 本轮验收记录

| 层级 | 结果 |
| --- | --- |
| 作息规则与模拟 HTTP | 10 项作息回归通过，HTTP 演示复测通过，覆盖重发、重启、求助去重和版本乱序。 |
| MQTT 与 App 源码 | 隔离的 AMQTT broker 和订阅者实际接收三类 QoS 1 载荷。15 项 App 解析和事件处理测试通过，旧数据库及全新数据库的 SQLite 去重 SQL 均已验证。 |
| HarmonyOS 构建 | `default/entry@default` Release HAP 构建通过，产物未签名。 |
| 设备与真实链路 | 待用开发签名包、隔离 broker 与测试账号验收 App 实际收包和页面展示。板端作息、真实模型和断网语音也待联调。 |
