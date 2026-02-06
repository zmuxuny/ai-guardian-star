# AI守护星：基于昇腾与鸿蒙OS的智能老人看护系统

![Ascend Logo](https://img.shields.io/badge/Powered%20by-Ascend-red)
![HarmonyOS Logo](https://img.shields.io/badge/OS-HarmonyOS-blue)
![Platform](https://img.shields.io/badge/Edge%20Device-Atlas%20200I%20DK%20A2-green)
![Framework](https://img.shields.io/badge/Framework-PyTorch%20/%20CANN-orange)
![License](https://img.shields.io/badge/License-MIT-purple)

**仓库名称：** `ai-guardian-star
`

---

## 📖 项目简介 (Introduction)

**“AI守护星”** 是一款聚焦居家养老安全的智能看护系统。随着全球老龄化加剧，独居老人的居家安全与健康监护成为突出社会问题——传统人工看护成本高、响应迟，难以实现24小时全覆盖。

本项目通过 **“边缘AI计算+鸿蒙终端响应”** 的全栈技术架构，将AI感知能力前置到家庭场景：基于华为昇腾Atlas 200I DK A2边缘计算板实现实时人体姿态分析，精准识别异常行为；结合鸿蒙OS原生应用实现秒级告警推送，构建“本地智能分析+远程即时响应”的闭环看护体系，用科技为老人筑起无形的安全防线。

## ✨ 核心功能 (Core Features)

系统通过轻量化姿态估计算法与多场景逻辑判断，实现三大核心看护能力：

- **🚨 摔倒检测 (Fall Detection)**  
  基于骨骼点运动轨迹分析，精准识别老人摔倒动作，触发紧急告警（支持置信度≥92%，响应延迟≤1.5秒）。

- **⏰ 久坐提醒 (Sedentary Alert)**  
  实时监测老人静态姿态持续时间，超过自定义阈值（如60分钟）时，通过鸿蒙应用推送温和提醒，降低血栓等健康风险。

- **⚠️ 危险区域告警 (Intrusion Warning)**  
  支持用户在鸿蒙应用中标定家庭危险区域（如厨房灶台、阳台边缘），老人进入时立即推送预警，防患于未然。

## 🚀 技术架构 (Technical Architecture)

系统采用“边缘端-通信层-终端”三层解耦架构，兼顾实时性与扩展性：

- **边缘计算端（昇腾Atlas 200I DK A2）**  
  - 核心能力：USB摄像头实时视频采集、轻量化YOLO姿态估计算法推理（基于CANN AIPP硬件加速）、异常行为逻辑判断。
  - 技术栈：PyACL推理框架、OpenCV视频处理、paho-mqtt客户端。

- **移动应用端（鸿蒙OS）**  
  - 核心能力：MQTT消息订阅、告警弹窗/铃声提醒、历史记录查询、危险区域标定。
  - 技术栈：ArkTS语言、ArkUI声明式UI、ohpm-mqtt库。

- **通信层**  
  - 协议：MQTT轻量级发布/订阅协议（低带宽占用，适合家庭网络）。
  - 数据格式：JSON结构化消息（包含事件类型、时间戳、置信度、设备ID）。

```mermaid
graph LR
    A[USB摄像头] --> B[昇腾Atlas 200I DK A2<br>（姿态估计+异常判断）];
    B -- MQTT发布告警 --> C[MQTT Broker];
    C -- MQTT订阅告警 --> D[鸿蒙OS应用<br>（弹窗+铃声提醒）];
    D -- 配置同步 --> B;
```

## 🛠️ 硬件与环境 (Hardware & Environment)

- **核心边缘设备：** 华为昇腾Atlas 200I DK A2（搭载Ascend 310B AI芯片，16TOPS INT8算力）
- **终端设备：** 鸿蒙OS 3.0及以上版本智能手机/平板
- **开发环境：**  
  - 边缘端：MindStudio 5.0+、CANN 6.0+、Ubuntu 20.04 (ARM)
  - 应用端：DevEco Studio 4.0+、HarmonyOS SDK 7.0+


## 👨‍💻 团队成员 (Team Members)

| 姓名 (Name) | 年级 (Grade) | 角色 (Role) |
| :---------- | :----------: | :---------- |
| 曹泽阳      |   2022级   | 项目组长（系统架构设计） |
| 董庄泽      |   2024级   | 边缘AI算法开发 |
| 何佳宝      |   2024级   | 昇腾模型部署与优化 |
| 简沅晞      |   2024级   | 鸿蒙应用UI开发 |
| 闻静涵      |   2024级   | 鸿蒙通信功能开发 |

## ©️ 许可证 (License)

本项目采用 [MIT License](LICENSE) 开源许可证。

## 📝 备注 (Notes)

项目正处于开发阶段，代码将持续更新。如需技术交流或问题反馈，欢迎提交Issue或联系团队邮箱：aiguard_team@cqu.edu.cn。
