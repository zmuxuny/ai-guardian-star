# 四个设备相关 Skill：本机安装与验证

日期：2026-11-07（Asia/Shanghai）。来源：用户提供的 android-device.zip。

## 保存位置与用途

安装目录：`$HOME\.codex\skills`。四个 skill 均为独立目录，下一轮对话即可自动发现，也可直接用 `$技能名` 指定。

| Skill | 用途 | 本次结果 |
|---|---|---|
| android-device | 通过 ADB 获取 Android 控件、点击、输入、截图、日志 | ADB 安装与设备枚举通过；入口、解析、编号、缓存、标号截图本地样例通过；无就绪 Android 目标 |
| harmony-device-acceptance | 鸿蒙静态/构建/安装/运行/权限/网络/端到端分层验收 | 文档与引用检查通过；API 24 模拟器连接、属性读取、布局抓取、截图回传及人工查看通过 |
| harmony-release-builder | 鸿蒙 Release 构建流程、工具链与 HAP/APP 产物检查 | Toolchain（含版本）、Discover、Artifact 三种脚本模式通过 |
| harmony-secure-session | 鸿蒙 Token、Asset Store、刷新与退出会话实现/审查 | 引用检查通过；项目现有会话静态契约测试 21/21 通过；不等于运行时会话安全验收 |

后两类流程型技能并非独立应用，不能将“安装技能”写成“完整发布/会话业务已通过”。

## 本机适配

- 将包内 `~/.claude/skills`、`$HOME\.claude\skills` 改为 Codex 技能目录。
- 将包内不存在的 `E:\DevEco Studio` 修正为实测存在的 `C:\Program Files\Huawei\DevEco Studio`。
- 保留用户原始压缩包与本目录 `original/`，适配版另存 `四个设备技能_Codex本机适配版.zip`；安装文件哈希见 `installed-manifest.json`。
- 不改应用源码、API、签名材料、项目依赖或用户原有未提交改动。不推送、不部署。

## 已验证证据

- 工具链：Node v24.14.1，Hvigor 6.26.4，OHPM 26.0.0.630，SDK 26.0.0.105 / API 26，HDC 3.2.0f。
- 检查的是已有 HAP，并未重构建：`D:\caringSystem\entry\build\default\outputs\default\entry-default-signed.hap`，24,697,840 字节，修改时间 2026-11-05T08:56:05.2798614Z；SHA-256 `04D9DA0A97A0C119E0F63EED3AB2D1C03F7145DAF0C5073E12A03D1CC5B3C6C9`。本次只确认文件与哈希，没有重验签或重装应用。
- 模拟器：Pura X View / HarmonyOS 6.1.1 / API 24，HDC `127.0.0.1:5555`，设备 model 回报 emulator。使用现有实例无窗口启动，保留数据；初始日志含快照恢复错误，随后同一次启动自行恢复并正常连接。未执行 reset。
- HDC `uitest dumpLayout` 与 `file recv` 成功，`harmony-layout.json` 是真实模拟器布局。
- `snapshot_display` 与 `file recv` 成功，`harmony-emulator.jpeg` 已打开检查，为正常锁屏画面；未解锁、未启动业务应用。模拟器保持运行，后续可继续验证。
- `validate-local.py`：四个技能的名称、路径、引用检查，以及 Android 合成 XML/编号/状态、隔离缓存、标号截图，共 7 组通过；`android-SYNTHETIC-marked.jpg` 是合成白底样例，不是设备截图。
- `session-static-results.json` / `session-static-tests.log`：现有 `test_client_auth_contract.py` 21 项通过，属于源码静态契约检查。

## Android ADB 实测

- 已安装官方 Platform-Tools 到 `%LOCALAPPDATA%\Android\Sdk\platform-tools`，无需改永久 PATH，adbui 会自动发现。
- `adb version`：1.0.41 / 37.0.1-15733141；`adbui devices` 成功调用实际 adb，输出一个 offline 的 emulator-5554，未发现就绪 Android 设备。
- `adbui ui` 正确以非零退出并提示 No ready device；不会在无目标时盲目操作。offline 条目不视为已连接 Android 设备。
- 下载包 CRC 检查通过，SHA-256 `45f4d63113e895ebde0c90f194099a4676b6ac653bd28d54314a9e022bbc1a99`。网络单流下载超时后使用 HTTPS 分段续传，未关闭证书验证。

## 未执行边界

- 本轮未连接真机，真机验证为 not run。
- Android 真机/模拟器 UI、输入、安装和日志未实测。
- 本轮未构建/重签/安装 HAP，未验收应用启动、权限允许/拒绝、弱网、登录、真实 Asset Store 持久化、服务端撤销或端到端业务。
- 不将已有 HAP、静态测试、锁屏截图等证据写成应用整体验收通过。

## 后续直接使用

对话示例：

- “用 $android-device 检查这台 Android 手机的当前页面。”
- “用 $harmony-release-builder 构建当前项目的 Release HAP。”
- “用 $harmony-device-acceptance 分开记录真机与模拟器验证结果。”
- “用 $harmony-secure-session 检查登录刷新和退出竞争。”

只读环境与连接检查：

```powershell
& "$HOME\.codex\skill-validation\android-device-20261107\Check-DeviceSkills.ps1"
```

Android：

```powershell
python "$HOME\.codex\skills\android-device\scripts\adbui.py" devices
python "$HOME\.codex\skills\android-device\scripts\adbui.py" -s <设备ID> ui
python "$HOME\.codex\skills\android-device\scripts\adbui.py" -s <设备ID> shot --marks
```

鸿蒙使用 HDC，不能调用 Android 的 adbui 来控制。多设备必须指定目标。设备已获当前任务授权时直接继续；涉及尚未授权的安装、权限、账户或数据操作时按请求范围处理。

ADB 工具来源为 [Android 官方 Platform-Tools](https://developer.android.com/tools/releases/platform-tools)，没有通过第三方镜像或关闭 TLS 校验下载。
