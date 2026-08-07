<div align="center">

# 智护星

面向居家照护场景的 HarmonyOS 原生应用与云端服务

[![HarmonyOS](https://img.shields.io/badge/HarmonyOS-6.1.0%20%7C%20API%2023-0A59F7?style=flat-square)](https://developer.huawei.com/consumer/cn/harmonyos/)
[![Backend](https://img.shields.io/badge/Backend-Python%20%7C%20Flask-3776AB?style=flat-square)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-2EA44F?style=flat-square)](LICENSE)

> 让科技守护每一位独居老人，让家人安心每一个夜晚。

</div>

## 项目简介

智护星是一套面向居家老人看护场景的端云协同系统。本仓库包含 HarmonyOS 手机端、账号与 AI 网关服务，以及对应的安全配置和回归测试；边缘设备通过 MQTT、HTTP 和 WebSocket 接口对接，板端推理代码不在本仓库中。

当前已完成 API 23 真机登录验证。账号接口统一通过 HTTPS 访问，服务端采用短时 Access Token 与可轮换 Refresh Token 管理会话；AI 对话在服务端依次经过输入审核、Coze 调用和输出审核。

## 当前状态

| 模块 | 状态 | 说明 |
|---|---|---|
| HarmonyOS 登录与账号管理 | 已验证 | 支持登录、资料修改、改密、注销会话和删除账号 |
| 服务端会话安全 | 已验证 | Access Token、Refresh Token 轮换及服务端撤销 |
| 本地数据与主题 | 已实现 | ArkDB 健康记录、个人设置、深浅色主题 |
| MQTT 告警 | 已接入 | 使用 TLS 连接，需结合实际设备继续联调 |
| AI 健康助手 | 已接入 | Coze 对话、三档数据授权、阿里云输入/输出内容审核 |
| 视频、人脸与语音 | 待联调 | App 接口已接入，依赖边缘设备和服务器端到端验证 |
| 手机验证码注册 | 已验证 | 阿里云短信认证已启用，真机已完成真实发送、核验与注册验收 |
| 记住登录 | 已验证 | 真机已验证登录状态保持；主动退出仍会清除会话 |
| 数据库管理后台 | 已安全开放 | 仅允许通过 SSH 隧道访问，不对公网暴露管理路由 |
| openGauss | 已评估 | 服务器已安装并仅监听回环地址；生产数据当前仍使用 SQLite |

## 核心能力

- HarmonyOS 原生手机/平板界面，支持资料、地址、密码、主题和账号管理。
- HTTPS 云账号服务，支持登录鉴权、令牌刷新与主动撤销。
- 可选“记住我”，Refresh Token 存入 HarmonyOS Asset Store，Access Token 仅保存在内存。
- 手机号验证码注册具备本地频控、每日费用上限和一次性挑战校验。
- ArkDB 本地存储健康事件、视频记录、用户设置和基础资料。
- MQTT TLS 接收跌倒、久坐等设备事件并生成健康记录。
- AI 助手支持 `basic`、`privacy`、`full` 三档上下文授权。
- 阿里云内容安全增强版审核用户输入与 AI 回复。
- 视频流、人脸录入和 WebSocket 语音接口已在 App 侧预留。

## 系统架构

```text
┌──────────────────── HarmonyOS App ────────────────────┐
│ ArkUI 页面 · ArkDB 本地数据 · MQTT TLS · HTTPS API   │
└───────────────┬───────────────────────┬───────────────┘
                │ HTTPS                 │ MQTT / HTTP / WS
                ▼                       ▼
┌──────────────────── 云端服务 ─────────────────────────┐
│ 反向代理（HTTPS） → Flask（127.0.0.1:8899）           │
│ 账号与会话 · SQLite · 内容审核 → Coze → 内容审核      │
└───────────────────────────────────────────────────────┘
                                        ▲
                                        │
                          ┌─────────────┴─────────────┐
                          │ 边缘设备（独立部署组件）  │
                          │ 姿态检测 · 视频 · 人脸等  │
                          └───────────────────────────┘
```

## 技术栈

| 层级 | 技术 |
|---|---|
| HarmonyOS 应用 | HarmonyOS 6.1.0 / API 23、Stage 模型、ArkTS、ArkUI、ArkDB |
| 云端服务 | Python、Flask、SQLite、systemd、HTTPS 反向代理 |
| 通信 | HTTPS、MQTT TLS、WebSocket |
| AI 与安全 | Coze、阿里云内容安全增强版 |
| 目标设备 | HarmonyOS 手机、平板；边缘设备独立部署 |

## 仓库结构

```text
caringSystem/
├── AppScope/                         # 应用级配置与资源
├── entry/                            # HarmonyOS 主模块
│   └── src/main/ets/
│       ├── common/                   # 云服务、AI、MQTT、主题、用户管理
│       ├── components/               # 复用 UI 组件
│       ├── database/                 # ArkDB 数据访问层
│       └── pages/                    # 登录、主页、记录、AI、个人中心等页面
├── deploy/                           # 服务端环境变量与 systemd 配置示例
├── docs/                             # 部署、安全与数据库评估文档
├── wenxin_proxy.py                   # 账号与 AI 网关服务
├── security_utils.py                 # 密码哈希与校验工具
├── test_wenxin_proxy.py              # 服务端回归测试
└── test_client_auth_contract.py      # App 鉴权契约测试
```

## 快速开始

### 环境要求

- DevEco Studio 6.0 或更新版本
- HarmonyOS SDK 6.1.0 / API 23
- Python 3.8 或更新版本（运行云端服务或回归测试时需要）

### 构建 HarmonyOS App

1. 使用 DevEco Studio 打开仓库并安装项目依赖。
2. 为 `default` 产品配置自己的签名证书与 Profile。
3. 检查 `entry/src/main/ets/config.ets` 中的公网 API 域名和边缘设备地址。
4. 连接 HarmonyOS 真机，选择 `default` 产品后构建并安装。

也可以使用 DevEco Studio 自带的 Hvigor：

```powershell
<DevEco-Studio>\tools\hvigor\bin\hvigorw.bat `
  --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=release `
  assembleHap --no-daemon
```

签名密码、私钥、AccessKey 和个人绝对路径均不得提交到版本库。

### 运行云端服务

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install flask flask-cors requests
pip install -r requirements-moderation.txt
pip install -r requirements-sms.txt
python wenxin_proxy.py
```

生产环境应使用 systemd 管理进程，让 Flask 仅监听 `127.0.0.1:8899`，再由 Nginx 或等价反向代理提供 HTTPS。不要把 8899 端口直接开放到公网。

## 配置与安全

App 当前通过 `https://api.aistar.asia` 访问公网接口。云端密钥只通过服务器环境变量注入，不得写入 App 或仓库：

- `COZE_API_TOKEN`
- `ALIBABA_CLOUD_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_ACCESS_KEY_SECRET`
- `AI_RISK_CONTROL_READY`
- `ALIYUN_MODERATION_ENABLED`
- `ALIBABA_CLOUD_SMS_ACCESS_KEY_ID`
- `ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET`
- `ALIYUN_SMS_ENABLED`

管理后台默认关闭。生产环境启用后仍应由 Nginx 对公网返回 404，只允许通过 SSH 隧道访问本机回环地址；同时必须配置 `ADMIN_PASSWORD` 与 `FLASK_SECRET_KEY`。

更多说明见 [安全策略](SECURITY.md) 和 [安全整改记录](docs/security-remediation-2026-07-15.md)。

## 测试

服务端与客户端鉴权契约测试：

```powershell
D:\Anaconda\python.exe -m unittest discover -v
```

提交前还应在 DevEco Studio 完成 Release 构建，并在真机验证登录、令牌刷新和核心页面跳转。

## 部署与运维文档

- [阿里云内容审核配置](docs/aliyun-content-moderation-setup.md)
- [阿里云短信验证码注册配置](docs/aliyun-sms-registration-setup.md)
- [数据库管理后台安全访问](docs/database-admin-access.md)
- [openGauss 迁移评估](docs/opengauss-migration-assessment.md)
- [安全整改记录](docs/security-remediation-2026-07-15.md)
- [贡献指南](CONTRIBUTING.md)
- [变更记录](CHANGELOG.md)

## 路线图

- [x] 完成阿里云短信认证配置与真实注册验收
- [x] 完成“记住我”真机登录状态保持验收
- [ ] 完成 Access Token 过期后的自动刷新与轮换真机验收
- [x] 通过 SSH 隧道开放数据库管理后台
- [ ] 完成 openGauss 生产迁移前置整改与备份演练
- [ ] 完成边缘设备的视频、人脸和语音端到端联调
- [ ] 增加自动化构建、部署和恢复验证

## 团队成员

| 姓名 | 年级 | 职责 |
|---|:---:|---|
| 曹泽阳 | 2022 级 | 项目负责人、系统架构设计 |
| 简沅晞 | 2024 级 | HarmonyOS 应用、通信、云端同步与数据库 |
| 董庄泽 | 2024 级 | 边缘 AI 算法、模型部署与优化 |
| 何佳宝 | 2024 级 | 边缘 AI 算法、数据集构建与标注 |
| 闻静涵 | 2024 级 | 需求分析、产品设计与用户测试 |

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

如有问题或合作意向，请提交 Issue，或联系 `z4t155664@163.com`。
