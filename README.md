<div align="center">

# 智护星

### 基于 OrangePi AIPro + 鸿蒙 OS 的智能居家老人看护系统

<br/>

[![Edge Device](https://img.shields.io/badge/Edge-OrangePi%20AIPro-orange?style=for-the-badge)](http://www.orangepi.cn/)
[![HarmonyOS](https://img.shields.io/badge/App-HarmonyOS%20NEXT-blue?style=for-the-badge)](https://developer.huawei.com/consumer/cn/harmonyos/)
[![AI](https://img.shields.io/badge/AI-扣子%20Coze-purple?style=for-the-badge)](https://www.coze.cn/)
[![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)](LICENSE)

<br/>

> **"让科技守护每一位独居老人，让家人安心每一个夜晚。"**

</div>

---

## 项目简介

**智护星**是一款面向居家养老场景的全栈智能看护系统。随着老龄化加剧，独居老人安全监护成为紧迫社会议题——传统人工看护成本高、响应慢，难以实现真正的 24 小时覆盖。

系统以 **"非接触式感知 + 端云协同 + AI 智能解读"** 为核心理念，将边缘 AI 计算前置至家庭场景：OrangePi AIPro 开发板运行姿态估计与异常检测算法，鸿蒙 OS 原生应用实现秒级告警推送，扣子智能体提供 AI 健康咨询，构建 **"本地智能分析 → 云端安全中转 → 手机即时响应 → AI 辅助决策"** 的完整闭环。

---

## 核心功能

### 实时行为检测（OrangePi AIPro 边缘端）

| 功能 | 描述 | 指标 |
|---|---|---|
| **摔倒检测** | 骨骼点运动轨迹分析，精准识别摔倒动作 | 置信度 ≥ 92%，响应延迟 ≤ 1.5s |
| **久坐提醒** | 静态姿态持续时长监测，超阈值触发提醒 | 阈值可配置（默认 60 分钟） |
| **隐私保护** | 人脸特征提取后原图即时销毁，特征向量不出开发板 | 零图像上云 |

### 鸿蒙 App 端

- **实时监控**：主页展示摄像头视频流（按需拉取），LIVE 状态动画，一键发起语音通话
- **即时告警**：MQTT 订阅检测结果，摔倒 / 久坐事件秒级推送
- **事件记录**：会话记录实时展示，历史记录持久化至 ArkDB，支持数据导出
- **人脸录入**：App 拍照 → 云端加密中转 → OrangePi AIPro 提取特征 → 原图销毁，全程隐私闭环
- **AI 健康助手**：接入扣子智能体，多轮对话，自动注入脱敏健康摘要，提供针对性建议
- **个人中心**：资料管理、紧急联系人、常用地址、深色 / 浅色 / 跟随系统主题切换

### 云端服务（华为云 ECS）

- **业务数据库**：OpenGauss 存储账号、健康事件、告警记录
- **AI 代理**：Flask 中转服务，隔离扣子 API Key，App 不持有密钥
- **人脸中转**：加密转发人脸图像至开发板，不落盘存储

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      华为云 ECS                              │
│   ┌──────────────────┐    ┌────────────────────────────┐    │
│   │  OpenGauss 数据库 │    │  信令服务 / AI 代理服务     │    │
│   │  账号·健康·告警   │    │  视频中转 · 扣子 API 代理  │    │
│   └──────────────────┘    └────────────────────────────┘    │
└────────────────┬──────────────────────┬─────────────────────┘
                 │ 账号/设置同步          │ 告警推送 / AI 对话
    ┌────────────▼──────────────┐    ┌──▼──────────────────────┐
    │  OrangePi AIPro（本地端）  │    │    App 端（手机）        │
    │                           │    │  HarmonyOS NEXT · ArkDB │
    │  · 姿态估计推理            │◄───┤                         │
    │  · 摔倒/久坐检测           │    │  · 实时视频流展示        │
    │  · 隐私数据库              │───►│  · MQTT 告警订阅         │
    │    人脸特征不上云           │    │  · AI 健康助手           │
    │  · 断网缓冲补传            │    │  · 历史记录 / 人脸录入   │
    └───────────────────────────┘    └─────────────────────────┘
              ▲
              │ MQTT 检测结果上传
              │ （摔倒/久坐/正常）
         USB 摄像头
```

---

## 隐私设计

全链路隐私保护：

- **人脸特征不上云**：人脸仅用于 OrangePi AIPro 本地提取 128 维特征向量，原图提取后即时销毁
- **AI 上下文脱敏**：发送给扣子的仅为聚合统计摘要（摔倒次数、久坐次数、距今天数），不含个人身份信息
- **API Key 不入包**：扣子 API Key 仅存于云端 Flask 服务，App 安装包不含任何密钥
- **手机号加密显示**：App 内手机号采用中间段 `****` 遮蔽

---

## 技术栈

| 层级 | 技术 |
|---|---|
| 边缘计算 | OrangePi AIPro · RKNN · OpenCV · paho-mqtt |
| 鸿蒙应用 | HarmonyOS NEXT · ArkTS · ArkUI · ArkDB · @ohos/mqtt |
| 云端服务 | 华为云 ECS · OpenGauss · Python Flask |
| AI 大模型 | 字节扣子 · Coze 智能体 |
| 通信协议 | MQTT · WebSocket · HTTP/HTTPS |

---

## 项目结构

```
zhihuxing/
├── entry/src/main/ets/
│   ├── config.ets                  # 全局配置（服务器/端口/存储 Key）
│   ├── components/                  # 共享 UI 组件
│   │   ├── GradientHeader.ets       #   蓝色渐变头部（7 个页面共用）
│   │   ├── MenuRow.ets              #   通用菜单行
│   │   └── StatDashboard.ets        #   个人中心统计面板
│   ├── common/                      # 服务层
│   │   ├── CloudService.ets         #   云端 REST API（注册/登录/验证码/改密）
│   │   ├── CloudSyncService.ets     #   云端数据同步
│   │   ├── WenxinService.ets        #   扣子 AI 对话服务
│   │   ├── MqttParser.ets           #   MQTT 消息解析
│   │   ├── ThemeManager.ets         #   主题管理（深色/浅色/跟随系统）
│   │   ├── UserManager.ets          #   用户登录态管理
│   │   └── AudioTransferManager.ets #   WebSocket 双向音频通话
│   ├── database/
│   │   └── DatabaseHelper.ets       #   ArkDB 封装（用户/事件/视频/设置表）
│   └── pages/                       # 页面
│       ├── Index.ets                #   启动页
│       ├── Layout.ets               #   底部 Tab 导航
│       ├── mainpage.ets             #   主页（视频流 + 设备状态 + 通话）
│       ├── record.ets               #   事件记录页
│       ├── AiChat.ets               #   AI 健康助手
│       ├── person.ets               #   个人中心
│       ├── Profile.ets              #   个人资料编辑
│       ├── Login.ets                #   登录 / 注册
│       ├── HealthHistory.ets        #   历史记录
│       ├── MyAddress.ets            #   常用地址
│       ├── MqttManager.ets          #   MQTT 连接管理
│       └── DatabaseDiagnostic.ets   #   数据库诊断工具
├── wenxin_proxy.py                  # 云端扣子 AI 代理（部署至 ECS）
└── PROJECT_STRUCTURE.md             # 详细项目结构文档
```

---

## 快速开始

### 环境要求

- **App 端**：DevEco Studio 6.0+，HarmonyOS SDK 20，HarmonyOS 5.0+ 真机
- **边缘端**：OrangePi AIPro，Ubuntu 22.04（ARM），RKNN 工具链
- **云端**：华为云 ECS，Python 3.8+

### 部署步骤

**1. 部署云端 AI 代理**

```bash
# 上传 wenxin_proxy.py 至 ECS
pip3 install flask flask-cors requests
nohup python3 /root/wenxin_proxy.py > /var/log/wenxin.log 2>&1 &
```

在 `wenxin_proxy.py` 中配置扣子 API Key，并在华为云安全组开放 TCP `8899` 端口。

**2. 配置 App 端**

编辑 `entry/src/main/ets/config.ets`：
```typescript
export const ECS_HOST = '你的ECS公网IP';
export const LAN_HOST = '192.168.xxx.xxx';  // OrangePi AIPro 局域网地址
```

**3. 编译运行**

DevEco Studio 连接真机，编译安装即可。

---

## 团队成员

| 姓名 | 年级 | 职责 |
|---|:---:|---|
| 曹泽阳 | 2022级 | 项目负责人 · 系统架构设计 |
| 简沅晞 | 2024级 | 鸿蒙应用全栈开发（UI / 通信 / 云端同步 / 数据库） |
| 董庄泽 | 2024级 | 边缘 AI 算法开发 · RKNN 模型部署与优化 |
| 何佳宝 | 2024级 | 边缘 AI 算法开发 · 数据集构建与标注 |
| 闻静涵 | 2024级 | 需求分析与产品设计 · 用户测试 |

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

<div align="center">

技术问题或合作意向，欢迎提交 Issue 或邮件至 **z4t155664@163.com**

</div>
