# Hardware-free device simulator / 无硬件设备模拟器

The repository includes `tools/device_simulator.py` so contributors can exercise the MQTT alert path without the physical edge-AI board.

仓库提供 `tools/device_simulator.py`，用于在没有真实边缘 AI 开发板的情况下验证 MQTT 告警链路。

## What it simulates / 可模拟事件

- `normal`
- `fall`
- `sedentary`
- `stranger`
- `sequence` — emits a short recovery sequence containing all major alert states

The generated payload follows the same contract consumed by `entry/src/main/ets/common/MqttParser.ets`:

```json
{
  "event": "fall",
  "source": "ai-guardian-star-simulator",
  "timestamp": "2026-08-15T00:00:00+00:00",
  "message_id": "..."
}
```

客户端 `MqttParser.ets` 会读取 `event` 字段，因此模拟器和真实告警走相同的解析路径。

## 1. Inspect payloads without MQTT / 不连接 MQTT 查看消息

No additional dependency is required:

```bash
python tools/device_simulator.py fall --dry-run
python tools/device_simulator.py sequence --dry-run
```

这一步适合先确认事件格式，也会被仓库中的单元测试覆盖。

## 2. Publish to a local development broker / 发布到本地开发 Broker

Install the simulator dependency:

```bash
pip install -r requirements-simulator.txt
```

For a local broker without TLS:

```bash
python tools/device_simulator.py sequence \
  --host 127.0.0.1 \
  --port 1883 \
  --no-tls
```

The default topic is:

```text
ai_guardian/alerts/simulator
```

The HarmonyOS client subscribes to `ai_guardian/alerts/#`, so the simulator topic is inside the same topic tree.

HarmonyOS 客户端默认订阅 `ai_guardian/alerts/#`，因此模拟器默认 topic 会被同一订阅规则接收。

> `--no-tls` is intended only for a local development broker. Do not disable TLS for production deployments.
>
> `--no-tls` 仅用于本地开发 Broker，生产环境不要关闭 TLS。

## 3. Publish to an authenticated TLS broker / 发布到带认证的 TLS Broker

Prefer environment variables so credentials do not appear in shell history:

```bash
export GUARDIAN_MQTT_HOST=broker.example.com
export GUARDIAN_MQTT_PORT=8883
export GUARDIAN_MQTT_USERNAME=developer
export GUARDIAN_MQTT_PASSWORD='...'
export GUARDIAN_MQTT_CA_CERT=/path/to/ca.crt

python tools/device_simulator.py sequence
```

Supported variables:

| Variable | Purpose |
|---|---|
| `GUARDIAN_MQTT_HOST` | Broker host |
| `GUARDIAN_MQTT_PORT` | Broker port |
| `GUARDIAN_MQTT_USERNAME` | MQTT username |
| `GUARDIAN_MQTT_PASSWORD` | MQTT password |
| `GUARDIAN_MQTT_CA_CERT` | CA certificate file path |

Do not commit credentials or private keys to this repository.

不要把 Broker 密码、私钥或其他生产凭据提交到仓库。

## End-to-end flow / 端到端链路

```text
device_simulator.py
        ↓ MQTT JSON
ai_guardian/alerts/simulator
        ↓
MqttManager.handleMessage()
        ↓
MqttParser.parseAlert()
        ↓
fall / sedentary / stranger / normal state
        ↓
HarmonyOS UI + local health-event persistence
```

This simulator deliberately targets the same parsing and state path used by physical devices. It is not a separate mock-only code path.

该模拟器刻意复用真实设备的消息解析与状态更新链路，而不是单独维护一套只在 Demo 中生效的 mock 逻辑。
