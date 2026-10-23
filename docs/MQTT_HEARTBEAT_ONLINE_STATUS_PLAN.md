# MQTT 心跳与设备在线状态优化方案

日期：2026-10-23

适用项目：智护星 `zhihuixing`

本地实施分支：`fix/mqtt-heartbeat-online-status`

基线提交：`fd1f4f229ace271edd60431c645b0545d279d2b2`

## 1. 目标与验收结论

本方案解决“设备正常运行但 20 秒没有告警消息时，App 显示设备未连接”的误报。

最终状态必须按以下含义分别显示：

| 状态 | 数据来源 | 含义 |
| --- | --- | --- |
| 告警通道 | App 与云端 MQTT Broker 的连接 | App 是否能接收消息，不代表开发板在线 |
| 开发板在线 | 板端每 10 秒发送的 MQTT 心跳 | 板端 AI 主进程最近是否仍在运行 |
| 视频服务可访问 | App 请求云端 `/api/stats` | 视频/HTTP 服务当前是否可用 |

验收通过必须同时具备以下证据：

1. 板端服务运行后，App 最迟 10 秒显示“开发板在线”。
2. 没有跌倒、久坐、陌生人或人脸事件时，App 连续运行 5 分钟仍保持在线。
3. 停止 `guardian-board.service` 后，App 在最后一次心跳后的 30～35 秒显示离线。
4. 恢复服务后，App 最迟 10 秒恢复在线，不需要重新登录。
5. 心跳不能清除正在处理的跌倒、久坐或陌生人状态。
6. `/api/stats` 异常时只能显示“视频服务不可用”，不能把 MQTT Broker 连接错误地当作开发板在线。

## 2. 当前问题

修改前，`entry/src/main/ets/pages/MqttManager.ets` 将任意设备消息的到达时间保存为 `lastDeviceActivity`，20 秒没有新消息就将 `deviceOnline` 设为 `false`。

板端 `src/ascend_main_other.py` 只发送业务事件：

- `ai_guardian/alerts/fall`
- `ai_guardian/alerts/sit`
- `ai_guardian/alerts/stranger`
- `ai_guardian/alerts/face`
- `ai_guardian/recordings/ready`

正常监护期间可能长时间没有业务事件，因此“最近收到事件”不能代表“开发板在线”。

`src/acllite/presenteragent` 中也存在 heartbeat，但它只服务于 Ascend Presenter 内部连接，不会发送到手机使用的 MQTT Broker，不能作为 App 在线状态依据。

## 3. 目标设计

### 3.1 心跳主题

本阶段使用：

```text
ai_guardian/alerts/heartbeat
```

选择该主题的原因：当前 App 和云端权限已经限制为 `ai_guardian/alerts/#`。将心跳放在现有范围内不需要扩大 MQTT 账号权限，也不需要修改云端 Broker 配置。

如果以后增加多块开发板，再迁移为 `ai_guardian/status/<deviceId>/heartbeat`，并同步实现账号与设备绑定、多个订阅主题和分设备授权。本次单板联调不要提前扩大范围。

### 3.2 心跳周期与离线门槛

- 默认发送周期：10 秒。
- 板端可选环境变量：`AI_GUARDIAN_HEARTBEAT_SECONDS`。
- 允许范围：5～60 秒；非法值回退为 10 秒。
- App 离线门槛：30 秒。
- App 每 5 秒检查一次，因此实际离线显示范围为最后一次心跳后的 30～35 秒。

### 3.3 心跳格式

```json
{
  "event": "heartbeat",
  "deviceId": "ascend_board",
  "timestamp": 1792742400000,
  "sequence": 1,
  "cameraConnected": true,
  "aiRunning": true
}
```

字段说明：

| 字段 | 含义 |
| --- | --- |
| `event` | 固定为 `heartbeat` |
| `deviceId` | 当前单板固定为 `ascend_board` |
| `timestamp` | 板端发送时的 Unix 毫秒时间 |
| `sequence` | 当前进程内递增序号，用于排查重复、停发和重启 |
| `cameraConnected` | 最近 3 秒是否读取到摄像头画面 |
| `aiRunning` | 推理主循环是否处于运行状态 |

当前 App 只使用“收到有效心跳”更新在线时间；`cameraConnected` 和 `aiRunning` 先保留为诊断字段。后续需要展示“摄像头异常”或“AI 已暂停”时，直接消费这两个字段，不要重新定义心跳格式。

### 3.4 告警状态保护

App 必须把 `heartbeat` 解析为独立的 `EventType.HEARTBEAT`。收到心跳时只更新在线时间并立即返回，不能进入普通 `NORMAL` 分支，否则心跳会清除跌倒、久坐和陌生人状态。

## 4. 文件修改任务

| 任务 | 文件 | 操作 |
| --- | --- | --- |
| 板端心跳模块 | `src/guardian_heartbeat.py` | 构造稳定 JSON、限制周期、启动/停止后台线程、QoS 1 发布 |
| 板端接线 | `src/ascend_main_other.py` | 定义心跳主题；AI 初始化成功后启动心跳；退出时停止线程 |
| App 消息类型 | `entry/src/main/ets/common/MqttParser.ets` | 新增 `EventType.HEARTBEAT` 并识别 `event=heartbeat` |
| App 在线逻辑 | `entry/src/main/ets/pages/MqttManager.ets` | 超时改为 30 秒；有效消息立即标记在线；心跳不修改告警状态 |
| App 状态文案 | `entry/src/main/ets/pages/mainpage.ets` | 状态弹窗明确区分视频、告警通道和开发板 |
| Release 混淆 | `entry/obfuscation-rules.txt` | 保留心跳跨端 JSON 字段名 |
| 板端测试 | `tests/test_guardian_heartbeat.py` | 验证周期边界、载荷和 QoS 1 发布契约 |
| App 测试 | `entry/src/test/LocalUnit.test.ets` | 验证心跳被识别为独立类型 |

## 5. 本地开发与验证步骤

### 5.1 检查代码状态

在 Windows PowerShell 7 中执行：

```powershell
Set-Location 'C:\Users\Yang\Documents\ChatGPT\zhihuixing'
git status --short --branch
git branch --show-current
```

预期分支为 `fix/mqtt-heartbeat-online-status`。若存在与本方案无关的未提交修改，先停止，不要覆盖。

### 5.2 运行板端隔离测试

```powershell
python -m unittest discover -s tests -p 'test_guardian_heartbeat.py' -v
python -m py_compile src/guardian_heartbeat.py src/ascend_main_other.py
```

预期：4 项测试全部通过，`py_compile` 无输出。

### 5.3 同步 HarmonyOS 现有依赖

只在 `oh_modules` 缺失或切换分支后执行；不升级依赖版本：

```powershell
$DevEcoHome = 'C:\Program Files\Huawei\DevEco Studio'
$Node = Join-Path $DevEcoHome 'tools\node\node.exe'
$Ohpm = Join-Path $DevEcoHome 'tools\ohpm\bin\pm-cli.js'
& $Node $Ohpm install --all
if ($LASTEXITCODE -ne 0) { throw "OHPM 依赖安装失败：$LASTEXITCODE" }
```

### 5.4 构建 Release HAP

```powershell
$DevEcoHome = 'C:\Program Files\Huawei\DevEco Studio'
$env:DEVECO_SDK_HOME = Join-Path $DevEcoHome 'sdk'
$env:JAVA_HOME = Join-Path $DevEcoHome 'jbr'
$env:Path = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:Path
$Hvigor = Join-Path $DevEcoHome 'tools\hvigor\bin\hvigorw.bat'

& $Hvigor --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=release `
  assembleHap --no-daemon
if ($LASTEXITCODE -ne 0) { throw "Release HAP 构建失败：$LASTEXITCODE" }
```

构建成功后核对：

```powershell
$Hap = Get-Item '.\entry\build\default\outputs\default\entry-default-unsigned.hap'
$Hap | Select-Object FullName, Length, LastWriteTime
$Hap | Get-FileHash -Algorithm SHA256
```

本次仍是未签名 HAP，只用于模拟器验收。

### 5.5 运行 App 本地单元测试

先确认依赖已经同步，然后在 PowerShell 7 中执行：

```powershell
$DevEcoHome = 'C:\Program Files\Huawei\DevEco Studio'
$env:DEVECO_SDK_HOME = Join-Path $DevEcoHome 'sdk'
$env:JAVA_HOME = Join-Path $DevEcoHome 'jbr'
$env:Path = (Join-Path $env:JAVA_HOME 'bin') + ';' + $env:Path
$Hvigor = Join-Path $DevEcoHome 'tools\hvigor\bin\hvigorw.bat'

& $Hvigor --mode module `
  -p product=default `
  -p module=entry@default `
  test --no-daemon
if ($LASTEXITCODE -ne 0) { throw "App 单元测试失败：$LASTEXITCODE" }
```

测试结果位于：

```text
entry/.test/default/intermediates/test/coverage_data/test_result.txt
```

确认 `classifies heartbeat without treating it as a normal monitoring event` 为 `Success`。若命令一直等待，先执行 `hdc list targets`；目标为空时启动模拟器后重试，不要把等待状态写成测试通过。

### 5.6 本次本机验证记录

截至 2026-10-23，本地已获得以下结果：

- 板端心跳隔离测试：4 项通过；
- `guardian_heartbeat.py` 与 `ascend_main_other.py`：`py_compile` 通过；
- App 本地测试：3 项通过、0 失败、0 错误，新增心跳分类测试通过；
- Release HAP：`BUILD SUCCESSFUL`；
- 产物：`entry/build/default/outputs/default/entry-default-unsigned.hap`；
- 大小：24,363,110 字节；
- SHA-256：`A6D0FCA35E8FA9B8A834595949DE14DC440AA571759F6BFEA61AE057A0C7A52D`；
- 模拟器：`Huawei_phone`，HarmonyOS 6.1.1 API 24，HDC 目标 `127.0.0.1:5555`；
- HAP 重新安装成功，`EntryAbility` 启动成功，应用进程处于前台。

上述结果证明代码可编译、App 可安装启动且心跳解析测试通过，不代表板端心跳已经完成端到端验收。

## 6. 开发板部署步骤

开发板服务目录是 `/root/ai_guardian`，服务名是 `guardian-board.service`。仓库文件与板端路径对应如下：

| 仓库文件 | 板端目标 |
| --- | --- |
| `src/guardian_heartbeat.py` | `/root/ai_guardian/guardian_heartbeat.py` |
| `src/ascend_main_other.py` | `/root/ai_guardian/ascend_main_other.py` |

### 6.1 连接前检查

1. 网线连接开发板与电脑。
2. 开发板上电并等待启动。
3. 使用 FinalShell 中保存的“香橙派”连接；连接失败时重新查询 DHCP 地址，不能假定旧 IP。
4. 登录后执行：

```bash
systemctl is-active guardian-board.service
systemctl status guardian-board.service --no-pager
```

### 6.2 备份现网文件

```bash
stamp=$(date +%Y%m%dT%H%M%S)
backup=/root/ai_guardian-backups/mqtt-heartbeat-$stamp
install -d -m 700 "$backup"
cp -a /root/ai_guardian/ascend_main_other.py "$backup/"
if [ -f /root/ai_guardian/guardian_heartbeat.py ]; then
  cp -a /root/ai_guardian/guardian_heartbeat.py "$backup/"
fi
sha256sum "$backup"/* > "$backup/SHA256SUMS"
echo "$backup"
```

记录输出的备份目录。不要复制或输出 MQTT 密码、证书私钥和其他凭据。

### 6.3 上传候选文件

先上传到临时名称：

```text
/root/ai_guardian/guardian_heartbeat.py.new
/root/ai_guardian/ascend_main_other.py.new
```

在板端执行语法检查：

```bash
cd /root/ai_guardian
.venv/bin/python -m py_compile guardian_heartbeat.py.new ascend_main_other.py.new
```

只有语法检查通过后才停止服务并替换：

```bash
systemctl stop guardian-board.service
install -o root -g root -m 644 guardian_heartbeat.py.new guardian_heartbeat.py
install -o root -g root -m 644 ascend_main_other.py.new ascend_main_other.py
systemctl start guardian-board.service
systemctl is-active guardian-board.service
```

默认心跳周期已经是 10 秒，不需要新增配置。如需显式固定，在 `guardian-board.service` 的 systemd drop-in 中加入：

```ini
[Service]
Environment=AI_GUARDIAN_HEARTBEAT_SECONDS=10
```

修改 drop-in 后执行：

```bash
systemctl daemon-reload
systemctl restart guardian-board.service
```

### 6.4 板端启动检查

```bash
journalctl -u guardian-board.service -n 100 --no-pager
systemctl show guardian-board.service -p MainPID -p ActiveState -p SubState
```

检查要求：

- 服务为 `active/running`；
- 出现 `MQTT Connected`；
- 没有持续出现 `heartbeat publish failed`；
- 摄像头和推理仍按原逻辑启动。

本方案没有修改云端代码和 MQTT 权限。若心跳不能送达，优先检查板端 MQTT 连接、证书和账号，不要先扩大 Broker 权限。

## 7. App 安装与端到端验收

### 7.1 安装

1. 启动 `Huawei_phone` HarmonyOS 6.1.1(24) 模拟器。
2. 使用 DevEco Studio 运行，或使用 `hdc install -r` 安装新 HAP。
3. 登录已在设备访问名单中的测试账号。

### 7.2 正常在线

1. 保持 `guardian-board.service` 运行。
2. 打开主页并等待最多 10 秒。
3. 点击设备状态，预期显示：
   - 告警通道：已连接；
   - 开发板：在线；
   - 视频服务：以 `/api/stats` 实际结果为准。
4. 不制造任何告警，保持 5 分钟。
5. 预期监测卡片持续显示“监测中”，不得在 20 秒后变成“设备未连接”。

### 7.3 离线与恢复

在板端执行：

```bash
systemctl stop guardian-board.service
```

记录最后一次在线时间。预期 App 在 30～35 秒变为离线。

然后执行：

```bash
systemctl start guardian-board.service
```

预期 App 在板端重新连上 MQTT 并发送心跳后的 10 秒内恢复在线，不需要退出登录或重启 App。

### 7.4 告警回归

依次验证跌倒、久坐、陌生人和人脸消息。要求：

- 业务消息正常显示；
- 心跳到达时不清除当前告警；
- 原有告警恢复定时器仍按各自规则清除状态；
- App 断开 Broker 时显示“告警通道未连接”，不能继续显示开发板在线超过 30 秒。

### 7.5 证据保存

交付人员应保存：

- 本地提交号和 `git status`；
- HAP 完整路径、大小和 SHA-256；
- 板端部署前后两个文件的 SHA-256；
- `guardian-board.service` 状态及必要日志；
- App 正常在线、停止服务后离线、恢复服务后重新在线的时间记录；
- 告警未被心跳清除的结果。

不要保存登录密码、Access Token、MQTT 临时密码、证书私钥或板端管理令牌。

## 8. 回滚步骤

若板端出现启动、MQTT、摄像头或推理回归，立即回滚：

```bash
systemctl stop guardian-board.service
backup=/root/ai_guardian-backups/mqtt-heartbeat-<实际时间戳>
cp -a "$backup/ascend_main_other.py" /root/ai_guardian/ascend_main_other.py
if [ -f "$backup/guardian_heartbeat.py" ]; then
  cp -a "$backup/guardian_heartbeat.py" /root/ai_guardian/guardian_heartbeat.py
else
  rm -f /root/ai_guardian/guardian_heartbeat.py
fi
systemctl start guardian-board.service
systemctl is-active guardian-board.service
```

App 回滚使用修改前的 HAP 重新安装。云端无需回滚，因为本方案没有修改云端服务或 Broker 权限。

## 9. 任务分工与完成标准

| 编号 | 负责人角色 | 任务 | 完成标准 | 当前状态 |
| --- | --- | --- | --- | --- |
| T1 | 板端开发 | 心跳模块及主程序接线 | 隔离测试通过，10 秒持续发布 | 本地完成，待板端验证 |
| T2 | HarmonyOS 开发 | 心跳解析、30 秒超时、状态文案 | Release HAP 构建成功 | 本地完成 |
| T3 | 板端运维 | 备份、上传、重启服务 | 服务 active，无持续错误 | 待执行 |
| T4 | App 测试 | 正常、离线、恢复、告警回归 | 第 1 节六项标准全部满足 | 待执行 |
| T5 | 交付负责人 | 汇总哈希、日志、时间记录 | 证据可追溯且不含凭据 | 待执行 |

只有 T1～T5 全部完成后，才能把结论写为“软硬件心跳在线状态验收通过”。本地构建成功只能证明代码可编译。
