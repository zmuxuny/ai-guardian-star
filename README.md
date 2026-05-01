<div align="center">

# 🌟 AI 守护星

### 基于昇腾边缘计算与鸿蒙 OS 的智能居家老人看护系统

<br/>

[![Powered by Ascend](https://img.shields.io/badge/Powered%20by-Ascend%20Atlas-red?style=for-the-badge&logo=huawei)](https://www.hiascend.com/)
[![HarmonyOS](https://img.shields.io/badge/App-HarmonyOS%20NEXT-blue?style=for-the-badge)](https://developer.huawei.com/consumer/cn/harmonyos/)
[![Edge Device](https://img.shields.io/badge/Edge-Atlas%20200I%20DK%20A2-green?style=for-the-badge)](https://www.hiascend.com/hardware/developer-kit)
[![AI](https://img.shields.io/badge/AI-ERNIE%204.5%20文心-orange?style=for-the-badge)](https://qianfan.cloud.baidu.com/)
[![License](https://img.shields.io/badge/License-MIT-purple?style=for-the-badge)](LICENSE)

<br/>

> **"让科技守护每一位独居老人，让家人安心每一个夜晚。"**

</div>

---

## 📖 项目简介

**AI 守护星**是一款面向居家养老场景的全栈智能看护系统。随着全球老龄化加剧，独居老人的安全监护已成为重要社会议题——传统人工看护成本高、响应慢，难以实现真正的 24 小时全覆盖。

本项目以 **"非接触式感知 + 端云协同 + AI 智能解读"** 为核心理念，将昇腾边缘计算能力前置至家庭场景。基于华为昇腾 Atlas 200I DK A2 实现实时姿态分析与异常检测，通过鸿蒙 OS 原生应用实现秒级告警推送，并引入百度文心大模型提供 AI 健康咨询，构建"**本地智能分析 → 云端安全中转 → 手机即时响应 → AI 辅助决策**"的完整闭环看护体系。

---

## ✨ 核心功能

### 🔍 实时行为检测（边缘端）

| 功能 | 描述 | 指标 |
|---|---|---|
| **摔倒检测** | 基于骨骼点运动轨迹分析，精准识别老人摔倒动作 | 置信度 ≥ 92%，响应延迟 ≤ 1.5s |
| **久坐提醒** | 实时监测静态姿态持续时长，超阈值触发健康提醒 | 自定义阈值（默认 60 分钟） |
| **隐私保护** | 人脸特征提取后原图即时销毁，特征向量不离开开发板 | 零图像上云 |

### 📱 鸿蒙 App 端（手机）

- **实时监控**：主页展示摄像头视频流（按需拉取），LIVE 状态动画，一键发起语音通话
- **即时告警**：MQTT 订阅检测结果，摔倒 / 久坐事件秒级弹窗推送
- **事件记录**：本次会话记录实时展示，历史记录持久化至 ArkDB，支持 7 天数据保留与导出
- **人脸录入**：App 拍照 → 云端加密中转 → 开发板提取特征 → 原图销毁，全程隐私闭环
- **AI 健康助手**：接入百度文心 ERNIE-4.5 大模型，支持多轮对话，自动注入监护统计摘要（脱敏），提供针对性健康建议
- **个人中心**：用户信息管理、紧急联系人、常用地址、数据保留设置、深色/浅色/跟随系统主题切换

### ☁️ 云端服务（华为云 ECS）

- **业务数据库**：OpenGauss 存储账号、健康事件、告警记录
- **AI 代理服务**：Flask 中转服务，隔离百度千帆 API Key，App 不直接持有密钥
- **人脸中转**：加密转发人脸图像至开发板，不落盘存储

---

## 🏗️ 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      华为云 ECS                              │
│   ┌──────────────────┐    ┌────────────────────────────┐    │
│   │  OpenGauss 数据库 │    │  信令服务 / AI 代理服务     │    │
│   │  账号·健康·告警   │    │  视频中转 · 文心 API 代理  │    │
│   └──────────────────┘    └────────────────────────────┘    │
└────────────────┬──────────────────────┬─────────────────────┘
                 │ 账号/设置同步          │ 告警推送 / AI 对话
    ┌────────────▼──────┐    ┌───────────▼──────────────────┐
    │  开发板（本地端）   │    │      App 端（手机）           │
    │  Atlas 200I DK A2  │    │   HarmonyOS NEXT · ArkDB    │
    │                    │    │                              │
    │  · 姿态估计推理     │◄───┤  · 实时视频流展示            │
    │  · 摔倒/久坐检测    │    │  · MQTT 告警订阅             │
    │  · 隐私数据库       │───►│  · AI 健康助手               │
    │    人脸特征不上云    │    │  · 历史记录 / 人脸录入       │
    │  · 断网缓冲补传     │    │  · 个人中心 / 主题切换       │
    └────────────────────┘    └──────────────────────────────┘
              ▲
              │ MQTT 检测结果上传
              │ （摔倒/久坐/正常）
         USB 摄像头
```

---

## 🔒 隐私设计

系统的隐私保护贯穿全链路：

- **人脸特征不上云**：人脸图像仅用于在开发板本地提取 128 维特征向量，提取完成后原图即时销毁
- **AI 上下文脱敏**：发送给文心大模型的仅为聚合统计摘要（摔倒次数、久坐次数、距今天数），不含任何可识别个人身份的信息
- **API Key 不入包**：百度千帆 API Key 仅存在于云端 Flask 服务，App 安装包内不包含任何密钥
- **手机号加密显示**：App 内手机号显示采用中间段 `*` 遮蔽处理

---

## 🛠️ 技术栈

| 层级 | 技术 |
|---|---|
| 边缘计算 | Atlas 200I DK A2 · CANN · PyACL · OpenCV · paho-mqtt |
| 鸿蒙应用 | HarmonyOS NEXT · ArkTS · ArkUI · ArkDB · ohos-mqtt |
| 云端服务 | 华为云 ECS · OpenGauss · Python Flask |
| AI 大模型 | 百度千帆 · ERNIE-4.5-turbo-128k |
| 通信协议 | MQTT · WebSocket · HTTP/HTTPS |

---

## 📦 项目结构

```
ai-guardian-star/
├── entry/src/main/ets/
│   ├── config.ets                  # 全局配置（服务器地址/端口/存储Key）
│   ├── components/                  # 共享 UI 组件
│   │   ├── GradientHeader.ets       #   蓝色渐变头部（7个页面共用）
│   │   ├── MenuRow.ets              #   通用菜单行（图标+标题/副标题+箭头）
│   │   └── StatDashboard.ets       #   个人中心统计面板（天数+预警数）
│   ├── common/                      # 服务层
│   │   ├── CloudService.ets         #   云端账号 REST API（注册/登录/验证码/改密）
│   │   ├── CloudSyncService.ets     #   云端数据同步服务
│   │   ├── WenxinService.ets        #   文心 AI 对话服务封装
│   │   ├── MqttParser.ets           #   MQTT 消息解析（纯函数，可独立测试）
│   │   ├── ThemeManager.ets         #   主题管理（深色/浅色/跟随系统）
│   │   ├── UserManager.ets          #   用户登录态管理
│   │   └── AudioTransferManager.ets #   音频通话（WebSocket 双向对讲）
│   ├── database/
│   │   └── DatabaseHelper.ets       #   ArkDB 数据库封装（用户/事件/视频/设置表）
│   └── pages/                       # 页面
│       ├── Index.ets                #   启动页（自动登录检测 → 跳转）
│       ├── Layout.ets               #   底部 Tab 导航（主页/记录/AI/个人）
│       ├── mainpage.ets             #   主页（视频流 + 设备状态 + 告警卡 + 通话）
│       ├── record.ets               #   事件记录页（本次会话内存记录）
│       ├── AiChat.ets               #   AI 健康助手（文心大模型对话）
│       ├── person.ets               #   个人中心（资料/人脸/地址/联系人/历史/主题）
│       ├── Profile.ets              #   个人资料编辑（头像/名字/手机/邮箱/密码）
│       ├── Login.ets                #   登录/注册（手机号+邮箱自动识别）
│       ├── HealthHistory.ets        #   历史记录（数据库加载+导出）
│       ├── MyAddress.ets            #   常用地址编辑
│       ├── MqttManager.ets          #   MQTT 连接+订阅+告警状态管理
│       └── DatabaseDiagnostic.ets   #   数据库诊断工具（长按Logo进入）
├── wenxin_proxy.py                  # 云端 AI 代理服务（部署至 ECS）
└── PROJECT_STRUCTURE.md             # 详细项目结构文档
```

---

## 🚀 快速开始

### 环境要求

- **App 端**：DevEco Studio 6.0+，HarmonyOS SDK 20，鸿蒙 OS 5.0+ 真机
- **边缘端**：CANN 7.0+，OpenEuler 22（ARM），Atlas 200I DK A2
- **云端**：华为云 ECS（任意规格），Python 3.8+

### 部署步骤

**1. 部署云端 AI 代理服务**

```bash
# 上传 wenxin_proxy.py 至 ECS，然后执行：
pip3 install flask flask-cors requests
nohup python3 /root/wenxin_proxy.py > /var/log/wenxin.log 2>&1 &
```

在 `wenxin_proxy.py` 中填入百度千帆 API Key：
```python
QIANFAN_API_KEY = "your_api_key_here"
```

在华为云安全组开放入站 TCP 端口 `8899`。

**2. 配置 App 端**

编辑 `entry/src/main/ets/config.ets`，修改服务器地址：
```typescript
export const ECS_HOST = '你的ECS公网IP';       // 云端 API / MQTT / 视频流
export const LAN_HOST = '192.168.xxx.xxx';      // 局域网开发板地址
```

**3. 编译运行**

使用 DevEco Studio 连接真机，编译并安装。

---

## 👨‍💻 团队成员

| 姓名 | 年级 | 角色 |
|---|:---:|---|
| 曹泽阳 | 2022级 | 项目负责人 · 系统架构设计 · 全栈开发 |
| 董庄泽 | 2024级 | 边缘 AI 算法开发 · 昇腾模型部署与优化 |
| 何佳宝 | 2024级 | 边缘 AI 算法开发 · 昇腾模型部署与优化 |
| 简沅晞 | 2024级 | 鸿蒙应用 UI 开发 · 通信功能开发 |
| 闻静涵 | 2024级 | 鸿蒙应用 UI 开发 · 通信功能开发 |

---

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

如有技术问题或合作意向，欢迎提交 Issue 或发送邮件至 **z4t155664@163.com**

</div>
