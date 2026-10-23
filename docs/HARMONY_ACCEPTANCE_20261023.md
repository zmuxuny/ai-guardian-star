# HarmonyOS 本地模拟器验收记录（2026-10-23）

验收代码：`backup/zy-merged-before-rollback-20261023`，基础提交 `9ccb75b`，已包含 `origin/ysh`。当前主工作区后来被另一操作重置到 `3d9617d`；本记录与产物只对应此备份工作区。为使项目可构建，从历史提交 `711cb57` 恢复了缺失的 Hvigor 配置、页面配置、BackupAbility 和资源文件，并将恢复文件与本记录保留在本地候选分支。

| 层级 | 操作与结果 | 结论 |
| --- | --- | --- |
| 工具链 | 本机 DevEco Studio、Hvigor 6.26.8、JBR、Node、OHPM 可用；使用已安装的 API 26 SDK 编译目标 API 24 | 通过 |
| 构建 | `assembleHap --no-daemon` 返回 `BUILD SUCCESSFUL` | 通过 |
| 产物 | `entry/build/default/outputs/default/entry-default-unsigned.hap`，SHA-256 `DEC69DF7A1C0430BBEFEFE541B43D753A59D12A9795330E95772E901FEA15D44`；`pack.info` 为 `com.jianyuanxi.guardianstar`、1.0.1 / 1010001、entry、API 24 | 通过（未签名） |
| 模拟器 | `Huawei_phone`，HarmonyOS 6.1.1(24)；`hdc` 连接 `127.0.0.1:5555`，设备报告 API 24 | 通过 |
| 安装与启动 | 上述 HAP 使用 `hdc install -r` 安装成功；`aa start` 成功并显示智护星主页。模拟器停止后重新启动，应用再次启动成功 | 通过 |
| 基础页面 | 主页显示设备未连接；“记录”页可打开，提示当前账号未获准访问监护设备；“个人”页可打开 | 页面导航通过，设备业务未覆盖 |
| 客户端认证契约 | `python -m unittest -q test_client_auth_contract.py`，21 项通过 | 通过 |
| 其他 Python 测试 | `test_ai_permissions.py` 缺少本机 Python 包 `flask`，未能运行 | 未验证 |
| 签名 | `signingConfigs` 为空，模拟器允许安装未签名 HAP | 本次模拟器验收不要求正式签名 |
| 权限、弱网及端到端 | 未取得可访问监护设备的测试账号/设备与后端环境；相机、麦克风权限和弱网业务链路未验收 | 未验证 |

已将 `AiChat.ets` 与 `Layout.ets` 中要求 API 26 的 `Circle.fill` 小圆点改为普通圆角组件；重新构建未再出现该 API 26 提示。编译器仍有音频系统能力与数据库异常处理提示，相关路径没有在本次模拟器场景中覆盖。AI 页面也未完成运行验收。

本次结论限于该 SHA-256 的合并候选 HAP 在 API 24 模拟器上的安装、启动和基础导航。它不代表真实手机、正式签名、设备连接、权限或后端业务验收。主工作区尚未合入这些构建修复；推送前应先核对主工作区与远端分支状态。
