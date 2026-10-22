# AI 守护星 · 项目交接文档
> 供 Hermes Agent 快速接手，由前任 Claude 整理 · 最后更新：2026-04-22

---

## 一、项目概览

| 项目       | 值                                                 |
| ---------- | -------------------------------------------------- |
| 项目名     | AI 守护星（AI Guardian Star）                      |
| 赛事       | 2026 中国大学生计算机设计大赛（4C大赛）            |
| 目标奖项   | 国家二等奖（算法深度达到可发表质量时冲国家一等奖） |
| 仓库       | github.com/zmuxuny/ai-guardian-star                |
| 本地根目录 | `E:\caringSystem`                                  |



---

## 二、编程环境

### 2.1 本机开发环境（Frank · Windows）

| 项目       | 路径 / 版本                            |
| ---------- | -------------------------------------- |
| 系统       | Windows 11                             |
| 主驱动器   | D 盘                                   |
| 桌面       | `D:\16228\desktop`                     |
| 下载       | `D:\16228\Dmowload`                    |
| 文档       | `D:\16228\Documents`                   |
| 项目根目录 | `E:\caringSystem`                      |
| IDE        | DevEco Studio（HarmonyOS NEXT SDK 20） |

### 2.2 云端服务器（Huawei Cloud ECS）

| 项目        | 值                                                                        |
| ----------- | ------------------------------------------------------------------------- |
| 公网 IP     | `117.78.9.144`                                                            |
| 操作系统    | Linux（Ubuntu）                                                           |
| 数据库      | OpenGauss（业务数据）                                                     |
| MQTT Broker | amqtt，端口 `1883`                                                        |
| AI 代理服务 | `wenxin_proxy.py`，Flask，端口 `8899`                                     |
| 终端工具    | FinalShell（**只支持单行 Python 命令**，heredoc 多行会 IndentationError） |

### 2.3 开发板（Atlas 200I DK A2）

| 项目                 | 值                                                        |
| -------------------- | --------------------------------------------------------- |
| 系统                 | OpenHarmony                                               |
| IP（USB RNDIS 直连） | `192.168.0.2`                                             |
| IP（局域网 WiFi）    | 动态，用 `get_host_ip()` 获取，目前约为 `192.168.137.100` |
| SSH                  | 通过 FinalShell，板子和电脑同局域网时可用                 |
| 数据库               | OpenGauss（本地隐私数据，人脸特征永不离板）               |
| Web 服务             | `ascend_board_server.py`，FastAPI，端口 `5000`            |
| 推理框架             | AscendCL（NPU 推理）                                      |
| 代码路径             | `/root/yolo/src/`                                         |

---

## 三、系统架构与信息传输

### 3.1 三端架构图（文字版）

```
┌─────────────────────────────────────────────────────────┐
│              华为云 ECS (117.78.9.144)                  │
│  ┌──────────────────┐   ┌────────────────────────────┐  │
│  │  OpenGauss 业务库 │   │   信令/中转服务             │  │
│  │  账号/健康/告警   │   │   MQTT Broker (1883)        │  │
│  └──────────────────┘   │   wenxin_proxy.py (:8899)   │  │
│                         └────────────────────────────┘  │
└──────┬──────────────────────────────────┬───────────────┘
       │ 检测结果上传 (MQTT/HTTP)          │ 告警推送 (MQTT)
       │ 账号/设置同步                    │ 账号/设置同步
┌──────▼──────────────────┐   ┌──────────▼───────────────┐
│  开发板 (Atlas 200I DK)  │   │   手机 App (HarmonyOS)    │
│  OpenHarmony             │   │   ArkDB (本地缓存)        │
│  OpenGauss (人脸特征库)  │   │   账号/个人设置           │
│  检测缓冲（断网补传）    │   │   检测记录（从云端拉取）  │
│  YOLO 摔倒/久坐检测      │   │   AI 助手（文心守护）     │
│  ArcFace 人脸识别        │   │   视频流展示              │
│  LD6002C 雷达接入        │   │   双向语音对讲            │
└─────────────────────────┘   └──────────────────────────┘
```

### 3.2 具体通信链路

| 链路                 | 协议                   | 端点                                      | 说明                                           |
| -------------------- | ---------------------- | ----------------------------------------- | ---------------------------------------------- |
| 板 → 云：检测告警    | MQTT QoS 1             | broker: `117.78.9.144:1883`               | 摔倒/久坐/陌生人事件                           |
| 板 → App：视频流     | HTTP 轮询（单帧 JPEG） | `http://<板IP>:5000/video_frame`          | 200ms 轮询，约 5-8 fps                         |
| 板 → App：视频流备选 | HTTP MJPEG             | `http://<板IP>:5000/video_feed`           | 经典推流模式                                   |
| 云 → App：MQTT 消息  | MQTT                   | broker: `117.78.9.144:1883`               | 告警推送到手机                                 |
| App → 云：AI 助手    | HTTP SSE               | `http://117.78.9.144:8899/chat`           | Flask 代理转发                                 |
| 云代理 → Coze        | HTTPS SSE              | `https://yhgh6fywzc.coze.site/stream_run` | AI 流式回复                                    |
| App → 板：人脸录入   | HTTP POST              | `http://<板IP>:8080/upload`               | 拍照→云中转→板提取特征→原图销毁                |
| 板 ←→ App：语音对讲  | WebSocket PCM          | `ws://<板IP>:5000/ws/intercom`            | 当前状态：WebSocket 接口存在但服务端未完整实现 |
| LD6002C → 板         | 串口 TinyFrame         | `/dev/ttyAMA0`，115200 baud               | 60GHz 毫米波雷达跌倒检测                       |


### 3.3 MQTT Topic 约定

| Topic                | 发布方 | 订阅方   | 内容          |
| -------------------- | ------ | -------- | ------------- |
| `guardian/fall`      | 板端   | App + 云 | 摔倒事件 JSON |
| `guardian/sedentary` | 板端   | App + 云 | 久坐事件 JSON |
| `guardian/stranger`  | 板端   | App + 云 | 陌生人告警    |

---

## 四、App 端代码结构（E:\caringSystem）

```
entry/src/main/ets/
├── pages/
│   ├── Layout.ets          # 底部导航 Tab，含 AiChat 标签页
│   ├── home.ets            # 主页，视频流展示
│   ├── record.ets          # 检测记录页（摔倒/久坐 Tab）
│   ├── HealthHistory.ets   # 历史记录页
│   ├── AiChat.ets          # 文心守护 AI 聊天页 ← 最新新增
│   ├── person.ets          # 人脸录入页
│   ├── Profile.ets         # 个人设置页（含头像 picker）
│   └── mainpage.ets        # 主容器页
├── common/
│   ├── MqttManager.ets     # MQTT 客户端封装（单例）
│   ├── AudioTransferManager.ets  # 语音对讲 WebSocket 封装
│   └── WenxinService.ets   # AI 助手 SSE 请求封装 ← 最新新增
└── ...
entry/src/main/
└── module.json5            # 权限声明（CAMERA 等）
wenxin_proxy.py             # ECS 侧 Flask AI 代理（部署在云端）
```

### 4.1 已解决的历史 Bug（不要回头挖坑）

| Bug                        | 根因                                      | 已修复方式                                     |
| -------------------------- | ----------------------------------------- | ---------------------------------------------- |
| 底部 Tab Header 高度不一致 | record.ets 底部 padding 20→34             | 已修复                                         |
| SVG 图标不渲染             | ArkTS SVG 兼容问题                        | 改为基础几何图形                               |
| ForEach 不刷新             | key 只用了 index，框架无法感知数据变化    | key 改为包含 `isLoading` + 内容长度            |
| 记录页刷新不及时           | ForEach 引用 MqttManager 内部数组原始引用 | 改为 `@State` 本地数组 + 500ms 定时器同步      |
| WAL 模式下 DB 看不到数据   | HarmonyOS RDB 默认 WAL，数据在 .db-wal 里 | 需三文件一起导出，或调 PRAGMA wal_checkpoint   |
| `catch (e: Error)` 报错    | ArkTS 不允许 catch 子句写类型标注         | 改为 `catch (e)` 裸变量                        |
| PowerShell 写文件乱码      | `-replace` + `Set-Content` 破坏 UTF-8     | **全项目禁用此方式**，统一用 Desktop Commander |

---

## 五、云端服务（ECS：117.78.9.144）

### 5.1 wenxin_proxy.py（AI 助手代理）

- **文件路径**：`/root/wenxin_proxy.py`（或项目根 `E:\caringSystem\wenxin_proxy.py`）
- **端口**：8899
- **功能**：接收 App 的 `/chat` 请求，携带 Coze API Token 转发至 Coze stream_run 端点，返回 SSE 流
- **Coze 配置**：
  - `project_id`: `7627479213733445658`
  - endpoint: `https://yhgh6fywzc.coze.site/stream_run`
  - model: `doubao-seed-1-8-251228`
  - Access Token：**仅存于 ECS 服务端，不写入 App 代码**

### 5.2 ⚠️ 最后已知 Blocker：SSE 解析问题

**状态：未解决**

ECS curl 测试 Coze `stream_run` 端点返回空输出。调试中断于此。

**下一步排查思路**：
1. 用 `curl -N -X POST https://yhgh6fywzc.coze.site/stream_run -H "Authorization: Bearer <token>" -d '{"project_id":"...","input":"你好"}' --no-buffer` 验证 Coze 端点本身是否正常
2. 检查 `wenxin_proxy.py` 里的 SSE 解析逻辑，Coze 的 `stream_run` 返回格式为 `data: {...}\n\n`，需要按行解析 `data:` 前缀
3. 确认 Flask 代理是否用了 `stream=True` 的 requests + `Response(generate(), mimetype='text/event-stream')`

---

## 六、板端代码（Atlas 200I DK · /root/yolo/src/）

### 6.1 文件结构

| 文件                     | 职责                                                                 |
| ------------------------ | -------------------------------------------------------------------- |
| `ascend_board_server.py` | FastAPI 服务器，HTTP 视频流 + WS 对讲入口，推理主循环调度            |
| `ascend_main_other.py`   | 核心引擎：ACL 推理 + 摔倒检测 + 人脸识别 + MQTT 客户端（约 1825 行） |
| `ascend_video_stream.py` | OpenCV JPEG 编码缓冲，限速 20fps，含 `/api/stats` 接口               |
| `ascend_voice_stream.py` | PyAudio 音频收发封装（48kHz PCM16）                                  |

### 6.2 检测算法关键参数

```python
FALL_CONFIRM_SECONDS = 0.6   # 连续判定为摔倒所需秒数
STATIONARY_TIME_THRESHOLD_SECONDS = 10  # 久坐判定阈值（秒）
STATIONARY_PIXEL_THRESHOLD = ...  # 质心移动像素阈值（静止判定）
```


### 6.3 ⚠️ 板端已知问题

| 问题                                           | 状态                                                  |
| ---------------------------------------------- | ----------------------------------------------------- |
| 语音对讲 `/ws/intercom` 服务端直接 close(1000) | 接口存在但功能为摆设，未真正实现双向 PCM 转发         |
| UDP 对讲代码被注释                             | `run_system()` 里 UDP socket 初始化全在注释里         |
| FPS 约 7-8（NPU 推理耗时）                     | 摔倒确认需 4-5 帧（约 0.6s），测试时需趴下保持 2-3 秒 |

---

## 七、硬件模组

### LD6002C 毫米波雷达（海凌科）

- **型号**：HLK-LD6002C + HLK-LD60G80G-Kit 底板
- **功能**：60GHz FMCW 毫米波，独立跌倒检测，不依赖摄像头
- **接入方式**：串口，115200 baud，TinyFrame 私有协议
- **板端接线**：LD6002C TX0 → Atlas UART RX，RX0 → Atlas UART TX
- **协议文档**：已在项目 knowledge 中（`LD6002C跌倒检测串口协议文档.pdf`）
- **当前状态**：硬件已到位，串口解析代码已集成进 `ascend_main_other.py`

---

## 八、待完成工作（优先级排序）

### 🔴 P0：阻塞性问题

- [ ] **修复 Coze SSE 解析**：`wenxin_proxy.py` 的流式转发逻辑，使 App 文心守护 AI 助手可用
- [ ] **语音对讲功能实装**：`/ws/intercom` 服务端需实现真正的 PCM 双向转发（板端麦克风→App，App 麦克风→板端扬声器）

### 🟡 P1：竞赛得分关键项

- [ ] **国产 AI 工具合规清单**：2026 规则要求使用 ≥15 个国产 AI 工具，需整理文档（目前可用的：Coze/豆包、AscendCL、MindSpore、文心系列等）
- [ ] **算法创新深度提升**：YOLOv8-pose 检测同质化严重，需增加技术差异点（多模态融合：摄像头 + 雷达）
- [ ] **单摄像头鲁棒性**：添加遮挡处理、光照自适应、俯视角修正
- [ ] **演示材料**：比赛现场答辩用的 PPT / 演示视频，需专门制作

### 🟢 P2：锦上添花

- [ ] 后台管理员 Web 端完善（目前开发板 Web 页面基本可用）
- [ ] App 端人脸录入完整流程测试（相机权限 → 拍照 → 上传 → 板端提取 → 原图销毁）
- [ ] OpenGauss 断网补传逻辑验证（板端缓冲→恢复连接后批量上传 ECS）
- [ ] 健康数据图表完善（HealthHistory 页面状态框大小已修复，数据展示逻辑待完善）

---

## 九、操作规范（重要）

### 文件操作

- ✅ **始终用 Desktop Commander** 读写 `E:\caringSystem` 下的文件
- ❌ 禁用 PowerShell `-replace` + `Set-Content`（会破坏 ArkTS 文件 UTF-8 编码）
- ✅ 大文件写入采用 rewrite 首块 + append 追加模式，每次 ≤30 行

### 代码修改原则（CLAUDE.md）

- **先出方案再动手**：任何改动前必须先列出方案，由 Frank 确认后再执行
- **外科手术式修改**：只改需要改的，不顺手"优化"周边代码
- **禁用自我纠错语言**：不说"等等""不对""哦对""我刚才说错了"，每次输出必须是深思熟虑后的最终版本

### ECS 命令

- FinalShell 只能执行**单行命令**
- Python 多行逻辑必须写成 `python3 -c "..."` 单行形式或上传文件后执行

### ArkTS 注意事项

- `catch (e)` 不能加类型标注（ArkTS 规则）
- `ForEach` 的 key 必须包含可变状态，否则框架不触发重渲染
- `@State` 数组需要赋值新引用（`[...arr]`）才能触发响应式更新

---

## 十、竞赛策略摘要

| 维度        | 现状                                | 建议                                                |
| ----------- | ----------------------------------- | --------------------------------------------------- |
| 技术差异点  | YOLO + 雷达双模态检测（同质化风险） | 强调全链路国产化叙事（昇腾 + 鸿蒙 + 开高斯 + 扣子） |
| 算法深度    | 工程集成为主，无创新算法            | 增加轻量级姿态时序模型或多模态融合，争取学术加分    |
| AI 工具合规 | 扣子编程已用                        | 补充到 15 个，整理对应文档证明                      |
| 现实目标    | 国家二等奖                          | 算法深度到位可冲一等奖                              |

---

*本文档由 Claude (Sonnet 4.6) 根据与 Frank (简沅晞) 的全部项目对话自动整理生成。*
*如有信息遗漏或过时，请直接修改本文件。*
