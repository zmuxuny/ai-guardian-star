<div align="center">

# AI Guardian Star · 智护星

**An open-source edge–cloud–device elderly-care system built with HarmonyOS and edge AI.**  
**基于 HarmonyOS 与边缘 AI 的开源端—云—边居家照护系统。**

[English](#english) · [中文](#中文)

[![CI](https://github.com/zmuxuny/ai-guardian-star/actions/workflows/ci.yml/badge.svg)](https://github.com/zmuxuny/ai-guardian-star/actions/workflows/ci.yml)
[![HarmonyOS](https://img.shields.io/badge/HarmonyOS-6.1.0%20%7C%20API%2023-0A59F7?style=flat-square)](https://developer.huawei.com/consumer/cn/harmonyos/)
[![Backend](https://img.shields.io/badge/Backend-Python%20%7C%20Flask-3776AB?style=flat-square)](https://flask.palletsprojects.com/)
[![Release](https://img.shields.io/github/v/release/zmuxuny/ai-guardian-star?include_prereleases&style=flat-square)](https://github.com/zmuxuny/ai-guardian-star/releases)
[![License](https://img.shields.io/badge/License-Apache--2.0-2EA44F?style=flat-square)](LICENSE)

</div>

---

# English

## Overview

**AI Guardian Star** is an open-source reference implementation for home elderly care that connects a native HarmonyOS application, a production-oriented cloud service, and independently deployed edge-AI devices.

The repository contains the **HarmonyOS client**, **account/session and AI gateway backend**, **deployment/operations tooling**, **security controls**, **automated tests**, and **CI/CD configuration**. Edge devices integrate with the system through MQTT, HTTP, and WebSocket interfaces. The edge-device inference implementation itself is deployed separately and is not included in this repository.

The project is designed around a practical end-to-end path:

**edge perception → secure event transport → cloud/account services → native HarmonyOS experience → caregiver-facing alerts and health records.**

The current public prerelease includes a deployable HarmonyOS HAP and an actively maintained backend. Core account flows have been validated on HarmonyOS API 23 devices.

## Why this project exists

Many elderly-care prototypes stop at a model demo or a single mobile interface. AI Guardian Star focuses on the integration work required to turn edge perception into a maintainable application system:

- native HarmonyOS phone/tablet client;
- secure cloud account and session management;
- edge-device event ingestion over MQTT TLS;
- local health-event persistence with ArkDB;
- AI health assistant with explicit data-sharing levels;
- content moderation around model input/output;
- video, face-enrollment, and voice communication integration points;
- deployment, monitoring, backup, security, CI, and regression testing.

It is intended both as an application and as a reusable engineering reference for developers exploring **HarmonyOS + edge AI + cloud services**.

## Architecture

<p align="center">
  <img src="guardian_system_architecture.svg" alt="AI Guardian Star architecture" width="900" />
</p>

```text
┌──────────────────────── HarmonyOS App ────────────────────────┐
│ ArkUI · ArkDB · Asset Store · HTTPS · MQTT TLS · WebSocket   │
└──────────────────┬──────────────────────────┬─────────────────┘
                   │ HTTPS                    │ MQTT / HTTP / WS
                   ▼                          ▼
┌──────────────────────── Cloud Service ────────────────────────┐
│ Reverse Proxy / HTTPS → Flask                                 │
│ Accounts · Sessions · SQLite · AI Gateway · Moderation       │
│ Operations · Backup · Monitoring                             │
└───────────────────────────────────────────────────────────────┘
                                              ▲
                                              │
                                ┌─────────────┴─────────────┐
                                │ Independently deployed    │
                                │ edge-AI device            │
                                │ pose / video / face / IoT │
                                └───────────────────────────┘
```

## Key capabilities

### HarmonyOS client

- Native HarmonyOS 6.1 / API 23 application using ArkTS, ArkUI, and the Stage model.
- Responsive phone/tablet layouts and light/dark themes.
- Account profile, address, password, session, and local preference management.
- ArkDB persistence for health events, video metadata, settings, and local user data.
- Health-history views and event records.

### Authentication and security

- Short-lived access tokens and rotatable refresh tokens.
- Automatic token refresh on authenticated request failure.
- Refresh-token persistence in HarmonyOS Asset Store when “Remember me” is enabled; access tokens remain in memory.
- Server-side session revocation and logout support.
- SMS verification for registration and password recovery, with challenge validation and rate/cost controls.
- Password hashing and validation utilities on the backend.
- Administrative database access designed for SSH-tunnel-only operation instead of public exposure.

### Edge-device integration

- MQTT TLS event ingestion for fall, sedentary, stranger, normal, and unknown states.
- Device liveness tracking and alert-state recovery logic.
- Health events persisted into the application database.
- App-side integration points for video streams, face enrollment, and bidirectional WebSocket audio.

### AI health assistant

- Server-side AI gateway rather than embedding model credentials in the client.
- `basic`, `privacy`, and `full` data-sharing levels for contextual health assistance.
- Input and output moderation around AI requests.
- Health summaries built from application state instead of unrestricted raw-data forwarding.

### Engineering and operations

- GitHub Actions CI for Python regression tests, syntax checks, and diff validation.
- Optional self-hosted Windows runner for signed HarmonyOS Release HAP builds.
- Optional production deployment workflow for the backend.
- systemd-oriented production deployment examples.
- SQLite maintenance, backup, and monitoring utilities.
- Issue templates, PR template, security policy, contribution guide, changelog, and release artifacts.

## Current project status

| Area | Status | Notes |
|---|---|---|
| HarmonyOS login & account management | ✅ Validated | Login, profile, password, logout/session revocation, account deletion |
| Session security | ✅ Implemented | Access/refresh tokens, refresh rotation, server-side revocation |
| “Remember me” | ✅ Device-validated | Refresh token stored through Asset Store |
| SMS registration | ✅ Device-validated | Real SMS send / verify / registration flow |
| ArkDB local data | ✅ Implemented | Health events, settings, video metadata, local state |
| MQTT alerts | ✅ Integrated | TLS connection; real edge-device deployments still require environment-specific integration |
| AI health assistant | ✅ Integrated | AI gateway + three privacy levels + input/output moderation |
| CI / backend deployment | ✅ Implemented | Tests, optional HAP build, optional production deploy |
| Video / face / voice | 🚧 Integration stage | App interfaces exist; complete end-to-end validation depends on edge deployment |
| openGauss migration | 🧪 Evaluated | Production currently remains on SQLite |

## Repository layout

```text
ai-guardian-star/
├── AppScope/                       # HarmonyOS application-level configuration/resources
├── entry/                          # Main HarmonyOS module
│   └── src/main/ets/
│       ├── common/                 # Cloud, AI, MQTT, theme, session and audio services
│       ├── components/             # Reusable ArkUI components
│       ├── database/               # ArkDB data-access layer
│       └── pages/                  # Login, home, records, AI assistant, profile, etc.
├── deploy/                         # Production deployment / monitoring / maintenance tools
├── docs/                           # Security, SMS, moderation and database documentation
├── .github/                        # CI, issue templates and PR template
├── wenxin_proxy.py                 # Account/session + AI gateway backend
├── security_utils.py               # Password/security utilities
├── test_wenxin_proxy.py            # Backend regression tests
├── test_client_auth_contract.py    # Client/backend authentication contract tests
├── test_ops_monitor.py             # Operations monitoring tests
├── test_sqlite_maintenance.py      # SQLite maintenance tests
└── guardian_system_architecture.svg
```

For a deeper code map, see [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md).

## Quick start

### Requirements

- DevEco Studio 6.0 or newer
- HarmonyOS SDK 6.1 / API 23
- Python 3.8+ for the backend and tests

### Build the HarmonyOS app

1. Clone the repository and open it with DevEco Studio.
2. Install HarmonyOS project dependencies.
3. Configure your own signing certificate and Profile for the `default` product.
4. Review the endpoint configuration in `entry/src/main/ets/config.ets` for your deployment.
5. Connect a HarmonyOS device and build/install the `default` product.

A Release HAP can also be built with DevEco Studio's Hvigor tooling:

```powershell
<DevEco-Studio>\tools\hvigor\bin\hvigorw.bat `
  --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=release `
  assembleHap --no-daemon
```

Never commit signing passwords, private keys, access keys, personal absolute paths, or production secrets.

### Run the backend

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-production.txt
python wenxin_proxy.py
```

For production, run the Flask application behind an HTTPS reverse proxy and keep the application port bound to loopback. See the examples under [`deploy/`](deploy/) and the security documentation under [`docs/`](docs/).

### Run tests

```bash
python -m unittest discover -v
```

CI also runs Python compilation checks and diff validation. HarmonyOS Release HAP builds can be enabled on a configured self-hosted Windows runner.

## Releases

The latest public prerelease is available from [GitHub Releases](https://github.com/zmuxuny/ai-guardian-star/releases).

`v0.1.0` provides a HarmonyOS HAP for device validation and includes responsive-layout work, password-recovery flow improvements, privacy/security fixes, and production-service hardening.

## Security

Security-sensitive configuration is injected through server environment variables and must not be embedded in the application or committed to the repository.

See:

- [SECURITY.md](SECURITY.md)
- [Security remediation notes](docs/security-remediation-2026-07-15.md)
- [Database administration access](docs/database-admin-access.md)
- [SMS registration setup](docs/aliyun-sms-registration-setup.md)
- [Content moderation setup](docs/aliyun-content-moderation-setup.md)

Please do **not** disclose suspected vulnerabilities in a public Issue before reading [SECURITY.md](SECURITY.md).

## Contributing

Contributions are welcome. Bug reports, documentation improvements, HarmonyOS compatibility fixes, backend hardening, edge-device adapters, tests, and deployment improvements are all useful.

Please read [CONTRIBUTING.md](CONTRIBUTING.md) and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before submitting changes.

## Roadmap

- [x] Real-device SMS registration verification
- [x] “Remember me” device validation
- [x] Secure database administration through SSH tunneling
- [x] Automated backend test workflow
- [x] Optional HarmonyOS Release HAP CI job
- [x] Optional production backend deployment workflow
- [ ] Complete broader real-device validation for refresh-token rotation
- [ ] Complete end-to-end video / face / voice integration with edge devices
- [ ] Run production migration and recovery drills for the database layer
- [ ] Expand reusable edge-device integration documentation and adapters

## Maintainers and contributors

| Name | Role |
|---|---|
| **Cao Zeyang (@zmuxuny)** | Project lead, architecture, backend/security and system integration |
| Jianyuanxi | HarmonyOS application, communication, cloud sync and database |
| Dong Zhuangze | Edge-AI algorithms, deployment and optimization |
| He Jiabao | Edge-AI algorithms, dataset construction and annotation |
| Wen Jinghan | Requirements, product design and user testing |

## License

Licensed under the [Apache License 2.0](LICENSE).

---

# 中文

## 项目简介

**智护星（AI Guardian Star）** 是一套面向居家老人照护场景的开源端—云—边协同系统，连接 **HarmonyOS 原生应用、生产化云端服务与独立部署的边缘 AI 设备**。

本仓库包含 **HarmonyOS 客户端、账号/会话与 AI 网关后端、部署运维工具、安全机制、自动化测试与 CI/CD 配置**。边缘设备通过 MQTT、HTTP 和 WebSocket 与系统对接；板端 AI 推理代码作为独立部署组件维护，不在本仓库中。

项目希望解决的不只是“跑通一个模型”或“做出一个 App”，而是把真实的边缘感知链路工程化为：

**边缘感知 → 安全事件传输 → 云端账号/AI 服务 → HarmonyOS 原生交互 → 告警与健康记录。**

目前公开预发布版本已经提供可安装的 HarmonyOS HAP，云端服务持续维护，核心账号链路已在 HarmonyOS API 23 真机完成验证。

## 为什么做这个项目

很多老人看护项目停留在算法 Demo 或单一移动端界面。智护星更关注真正落地时需要解决的系统工程问题，包括：

- HarmonyOS 手机/平板原生客户端；
- 安全的云端账号与会话体系；
- MQTT TLS 边缘告警接入；
- ArkDB 本地健康事件持久化；
- 带显式数据授权等级的 AI 健康助手；
- AI 输入/输出内容审核；
- 视频、人脸录入、语音通信接口；
- 部署、监控、备份、安全、CI 与回归测试。

因此它既是一套实际应用，也希望成为 **HarmonyOS + 边缘 AI + 云服务** 场景下可以复用和参考的开源工程实现。

## 系统架构

<p align="center">
  <img src="guardian_system_architecture.svg" alt="智护星系统架构" width="900" />
</p>

```text
┌──────────────────────── HarmonyOS App ────────────────────────┐
│ ArkUI · ArkDB · Asset Store · HTTPS · MQTT TLS · WebSocket   │
└──────────────────┬──────────────────────────┬─────────────────┘
                   │ HTTPS                    │ MQTT / HTTP / WS
                   ▼                          ▼
┌──────────────────────── 云端服务 ─────────────────────────────┐
│ HTTPS 反向代理 → Flask                                       │
│ 账号 · 会话 · SQLite · AI 网关 · 内容审核                    │
│ 运维 · 备份 · 监控                                           │
└───────────────────────────────────────────────────────────────┘
                                              ▲
                                              │
                                ┌─────────────┴─────────────┐
                                │ 独立部署的边缘 AI 设备    │
                                │ 姿态 / 视频 / 人脸 / IoT  │
                                └───────────────────────────┘
```

## 核心能力

### HarmonyOS 客户端

- HarmonyOS 6.1 / API 23 原生应用，使用 ArkTS、ArkUI 与 Stage 模型。
- 手机/平板自适应布局，支持深色与浅色主题。
- 账号资料、地址、密码、会话和本地偏好管理。
- 使用 ArkDB 保存健康事件、视频元数据、设置及本地用户信息。
- 提供健康历史与事件记录页面。

### 账号与安全

- 短时 Access Token + 可轮换 Refresh Token。
- 鉴权请求失败时支持自动刷新 Token。
- 勾选“记住我”时，Refresh Token 通过 HarmonyOS Asset Store 持久化；Access Token 仅保存在内存。
- 支持服务端会话撤销与主动退出。
- 手机验证码注册与密码找回，包含一次性挑战校验、频控与费用限制。
- 后端提供密码哈希及安全校验工具。
- 数据库管理后台采用仅 SSH 隧道访问的部署方式，不直接暴露公网。

### 边缘设备接入

- 通过 MQTT TLS 接收跌倒、久坐、陌生人、正常及未知状态事件。
- 设备在线状态检测和告警恢复逻辑。
- 告警事件写入应用本地健康数据库。
- App 侧已提供视频流、人脸录入和 WebSocket 双向语音接口。

### AI 健康助手

- AI 请求统一经过服务端网关，模型密钥不进入客户端。
- 支持 `basic`、`privacy`、`full` 三档上下文数据授权。
- 对用户输入与 AI 输出执行内容审核。
- 基于应用健康状态构造摘要，而不是无约束转发全部原始数据。

### 工程化与运维

- GitHub Actions 自动执行 Python 回归测试、语法检查与 diff 校验。
- 可选 self-hosted Windows Runner 自动构建 HarmonyOS Release HAP。
- 可选生产环境后端自动部署流程。
- 提供面向 systemd 的生产部署示例。
- 提供 SQLite 维护、备份与运行监控工具。
- 已配置 Issue Template、PR Template、安全策略、贡献指南、变更记录和 Release 产物。

## 当前状态

| 模块 | 状态 | 说明 |
|---|---|---|
| HarmonyOS 登录与账号管理 | ✅ 已验证 | 登录、资料、改密、退出/撤销会话、删除账号 |
| 服务端会话安全 | ✅ 已实现 | Access/Refresh Token、刷新轮换、服务端撤销 |
| 记住登录 | ✅ 真机验证 | Refresh Token 通过 Asset Store 保存 |
| 手机验证码注册 | ✅ 真机验证 | 已完成真实短信发送、核验和注册流程 |
| ArkDB 本地数据 | ✅ 已实现 | 健康事件、设置、视频元数据及本地状态 |
| MQTT 告警 | ✅ 已接入 | TLS 连接；不同边缘部署环境仍需针对性联调 |
| AI 健康助手 | ✅ 已接入 | AI 网关 + 三档数据授权 + 输入/输出审核 |
| CI / 后端部署 | ✅ 已实现 | 自动测试、可选 HAP 构建、可选生产部署 |
| 视频 / 人脸 / 语音 | 🚧 联调阶段 | App 接口已具备，完整验证依赖边缘设备 |
| openGauss 迁移 | 🧪 已评估 | 当前生产数据仍使用 SQLite |

## 仓库结构

```text
ai-guardian-star/
├── AppScope/                       # HarmonyOS 应用级配置与资源
├── entry/                          # HarmonyOS 主模块
│   └── src/main/ets/
│       ├── common/                 # 云服务、AI、MQTT、主题、会话、语音服务
│       ├── components/             # 可复用 ArkUI 组件
│       ├── database/               # ArkDB 数据访问层
│       └── pages/                  # 登录、主页、记录、AI、个人中心等页面
├── deploy/                         # 生产部署、监控与维护工具
├── docs/                           # 安全、短信、内容审核与数据库文档
├── .github/                        # CI、Issue Template、PR Template
├── wenxin_proxy.py                 # 账号/会话 + AI 网关后端
├── security_utils.py               # 密码与安全工具
├── test_wenxin_proxy.py            # 后端回归测试
├── test_client_auth_contract.py    # 客户端/服务端鉴权契约测试
├── test_ops_monitor.py             # 运维监控测试
├── test_sqlite_maintenance.py      # SQLite 维护测试
└── guardian_system_architecture.svg
```

更详细的代码导航见 [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)。

## 快速开始

### 环境要求

- DevEco Studio 6.0 或更新版本
- HarmonyOS SDK 6.1 / API 23
- Python 3.8+（运行后端与测试）

### 构建 HarmonyOS App

1. 克隆仓库并使用 DevEco Studio 打开。
2. 安装 HarmonyOS 项目依赖。
3. 为 `default` 产品配置自己的签名证书与 Profile。
4. 根据自己的部署环境检查 `entry/src/main/ets/config.ets` 中的服务地址。
5. 连接 HarmonyOS 真机并构建、安装 `default` 产品。

也可以使用 DevEco Studio 自带的 Hvigor 构建 Release HAP：

```powershell
<DevEco-Studio>\tools\hvigor\bin\hvigorw.bat `
  --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=release `
  assembleHap --no-daemon
```

签名密码、私钥、AccessKey、个人绝对路径以及生产环境密钥均不得提交到仓库。

### 运行后端

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-production.txt
python wenxin_proxy.py
```

生产环境应将 Flask 放在 HTTPS 反向代理之后，并仅监听回环地址。具体示例见 [`deploy/`](deploy/) 与 [`docs/`](docs/) 下的部署、安全文档。

### 运行测试

```bash
python -m unittest discover -v
```

CI 还会执行 Python 编译检查与 diff 校验；配置 self-hosted Windows Runner 后，可启用 HarmonyOS Release HAP 自动构建。

## Release

最新公开预发布版本见 [GitHub Releases](https://github.com/zmuxuny/ai-guardian-star/releases)。

`v0.1.0` 提供用于真机验证的 HarmonyOS HAP，包含多设备自适应布局、密码找回、安全与隐私修复、生产服务加固等更新。

## 安全

所有云端敏感配置均通过服务器环境变量注入，不应写入 App 或提交到仓库。

相关文档：

- [安全策略](SECURITY.md)
- [安全整改记录](docs/security-remediation-2026-07-15.md)
- [数据库管理后台安全访问](docs/database-admin-access.md)
- [阿里云短信验证码注册配置](docs/aliyun-sms-registration-setup.md)
- [阿里云内容审核配置](docs/aliyun-content-moderation-setup.md)

如果发现潜在安全漏洞，请先阅读 [SECURITY.md](SECURITY.md)，不要直接在公开 Issue 中披露敏感细节。

## 参与贡献

欢迎提交 Bug、文档改进、HarmonyOS 兼容性修复、后端安全加固、边缘设备适配、自动化测试和部署改进。

提交前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md) 和 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 路线图

- [x] 完成短信验证码真实注册验收
- [x] 完成“记住我”真机验证
- [x] 通过 SSH 隧道安全开放数据库管理后台
- [x] 建立后端自动化测试流程
- [x] 增加可选 HarmonyOS Release HAP CI 构建
- [x] 增加可选生产后端自动部署流程
- [ ] 扩大 Refresh Token 轮换的真机验证覆盖
- [ ] 完成视频 / 人脸 / 语音与边缘设备的端到端联调
- [ ] 完成数据库生产迁移与恢复演练
- [ ] 完善可复用的边缘设备适配文档与接口

## 维护者与贡献者

| 姓名 | 职责 |
|---|---|
| **曹泽阳 (@zmuxuny)** | 项目负责人、系统架构、后端/安全与系统集成 |
| 简沅晞 | HarmonyOS 应用、通信、云端同步与数据库 |
| 董庄泽 | 边缘 AI 算法、模型部署与优化 |
| 何佳宝 | 边缘 AI 算法、数据集构建与标注 |
| 闻静涵 | 需求分析、产品设计与用户测试 |

## 许可证

本项目基于 [Apache License 2.0](LICENSE) 开源。
