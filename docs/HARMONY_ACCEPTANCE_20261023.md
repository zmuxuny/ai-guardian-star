# HarmonyOS 本地模拟器验收记录（2026-10-23）

验收代码：`integration/ysh-latest-zy-hardware`。HarmonyOS 软件端完整恢复到 `origin/ysh` 最新提交 `eaaa7ba`；硬件、录像与板端代码保留 `origin/zy` 最新提交 `9ccb75b`。手机端相对 `ysh` 仅有四处适配：两个录像接口字段用于对接板端完整录像分段，两个小圆点改用 API 24 支持的等效组件。

| 层级 | 操作与结果 | 结论 |
| --- | --- | --- |
| 工具链 | 本机 DevEco Studio、Hvigor 6.26.8、JBR、Node、OHPM 可用；使用已安装的 API 26 SDK 编译目标 API 24 | 通过 |
| 构建 | `assembleHap --no-daemon` 返回 `BUILD SUCCESSFUL` | 通过 |
| 产物 | `entry/build/default/outputs/default/entry-default-unsigned.hap`，24,362,994 字节，SHA-256 `3554034821ED7D32C25E40D94B485D89308C4126CE6705F491909A72AE86EFF4`；`pack.info` 为 `com.jianyuanxi.guardianstar`、1.0.1 / 1010001、entry、API 24 | 通过（未签名） |
| 模拟器 | `Huawei_phone`，HarmonyOS 6.1.1(24)；`hdc` 连接 `127.0.0.1:5555`，设备报告 API 24 | 通过 |
| 安装与启动 | 上述 HAP 使用 `hdc install -r` 安装成功；`aa start` 成功并显示智护星主页。模拟器停止后重新启动，应用再次启动成功 | 通过 |
| 基础页面 | 主页显示设备未连接；“记录”页可打开，提示当前账号未获准访问监护设备；“个人”页可打开 | 页面导航通过，设备业务未覆盖 |
| 客户端认证契约 | `python -m unittest -q test_client_auth_contract.py`，21 项通过 | 通过 |
| AI 权限接口测试 | 使用临时 uv 环境安装 Flask、Flask-CORS、Requests 后运行 `test_ai_permissions.py`，22 项通过；测试使用隔离 SQLite 和模拟的模型调用 | 通过（离线测试） |
| 签名 | `signingConfigs` 为空，模拟器允许安装未签名 HAP | 本次模拟器验收不要求正式签名 |
| 权限、弱网及端到端 | 未取得可访问监护设备的测试账号/设备与后端环境；相机、麦克风权限和弱网业务链路未验收 | 未验证 |

已将 `AiChat.ets` 与 `Layout.ets` 中要求 API 26 的 `Circle.fill` 小圆点改为普通圆角组件；重新构建未再出现该 API 26 提示。编译器仍有音频系统能力与数据库异常处理提示，相关路径没有在本次模拟器场景中覆盖。AI 页面也未完成运行验收。

本次结论限于该 SHA-256 的组合候选 HAP 在 API 24 模拟器上的安装、启动和基础导航。它不代表真实手机、正式签名、设备连接、权限或后端业务验收。
