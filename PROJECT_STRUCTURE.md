# 项目结构详解

> 总代码量：~6400 行（24 个源文件） | 最后更新：2026-05-01

## 导航速查表

| 我想改... | 去这个文件 |
|-----------|-----------|
| 服务器 IP / 端口 / URL | [config.ets](entry/src/main/ets/config.ets) |
| 蓝色渐变头部样式 | [components/GradientHeader.ets](entry/src/main/ets/components/GradientHeader.ets) |
| 主页视频流 / 状态卡 | [pages/mainpage.ets](entry/src/main/ets/pages/mainpage.ets) |
| AI 对话 / 快捷问题 | [pages/AiChat.ets](entry/src/main/ets/pages/AiChat.ets) |
| 个人中心菜单 / 统计数据 | [pages/person.ets](entry/src/main/ets/pages/person.ets) |
| 菜单行点击 / 按压动效 | [components/MenuRow.ets](entry/src/main/ets/components/MenuRow.ets) |
| 个人资料编辑（头像/名字/密码） | [pages/Profile.ets](entry/src/main/ets/pages/Profile.ets) |
| 登录 / 注册 / 自动识别 | [pages/Login.ets](entry/src/main/ets/pages/Login.ets) |
| 数据库表结构 / CRUD | [database/DatabaseHelper.ets](entry/src/main/ets/database/DatabaseHelper.ets) |
| 云端 API（注册/登录/验证码） | [common/CloudService.ets](entry/src/main/ets/common/CloudService.ets) |
| MQTT 连接 / 告警推送 | [pages/MqttManager.ets](entry/src/main/ets/pages/MqttManager.ets) |
| MQTT 消息解析逻辑 | [common/MqttParser.ets](entry/src/main/ets/common/MqttParser.ets) |
| 深色/浅色主题 | [common/ThemeManager.ets](entry/src/main/ets/common/ThemeManager.ets) |
| 用户登录态管理 | [common/UserManager.ets](entry/src/main/ets/common/UserManager.ets) |
| 语音通话（WebSocket） | [common/AudioTransferManager.ets](entry/src/main/ets/common/AudioTransferManager.ets) |
| 文心 AI 对话 API | [common/WenxinService.ets](entry/src/main/ets/common/WenxinService.ets) |
| App 启动 / 自动登录 | [pages/Index.ets](entry/src/main/ets/pages/Index.ets) |
| 底部 Tab 导航 | [pages/Layout.ets](entry/src/main/ets/pages/Layout.ets) |
| 事件记录（本会话） | [pages/record.ets](entry/src/main/ets/pages/record.ets) |
| 历史记录 + 导出 | [pages/HealthHistory.ets](entry/src/main/ets/pages/HealthHistory.ets) |
| 地址编辑 | [pages/MyAddress.ets](entry/src/main/ets/pages/MyAddress.ets) |
| 数据库诊断工具 | [pages/DatabaseDiagnostic.ets](entry/src/main/ets/pages/DatabaseDiagnostic.ets) |
| 全局常量（AppStorage Key 等） | [config.ets](entry/src/main/ets/config.ets) |

---

## 目录结构一览

```
entry/src/main/ets/
├── config.ets                        40 行  全局配置
├── components/                              共享 UI 组件（3 个）
│   ├── GradientHeader.ets            19 行    蓝色渐变头部容器
│   ├── MenuRow.ets                   56 行    通用菜单行
│   └── StatDashboard.ets             39 行    统计面板
├── common/                                  服务层（7 个）
│   ├── CloudService.ets             130 行    云端 REST API
│   ├── CloudSyncService.ets         143 行    云端数据同步
│   ├── WenxinService.ets            122 行    文心 AI 对话
│   ├── MqttParser.ets                56 行    MQTT 消息解析
│   ├── ThemeManager.ets             199 行    主题管理
│   ├── UserManager.ets               64 行    用户登录态
│   └── AudioTransferManager.ets     191 行    音频通话
├── database/                                 数据库（1 个）
│   └── DatabaseHelper.ets           821 行    ArkDB 封装
└── pages/                                    页面（11 个）
    ├── Index.ets                      64 行    启动页
    ├── Layout.ets                    111 行    Tab 导航
    ├── mainpage.ets                  368 行    主页
    ├── record.ets                    234 行    事件记录
    ├── AiChat.ets                    308 行    AI 助手
    ├── person.ets                    602 行    个人中心
    ├── Profile.ets                   694 行    资料编辑
    ├── Login.ets                     844 行    登录/注册
    ├── HealthHistory.ets             267 行    历史记录
    ├── MyAddress.ets                 157 行    地址编辑
    ├── MqttManager.ets               513 行    MQTT 管理
    └── DatabaseDiagnostic.ets        349 行    数据库诊断
```

---

## 逐文件说明

### config.ets — 全局配置

所有环境相关的常量和 Key 集中在这里，换服务器只需改这一个文件。

| 导出 | 值示例 | 用途 |
|------|--------|------|
| `ECS_HOST` | `'117.78.9.144'` | 云端服务器 IP |
| `ECS_BASE_URL` | `http://...` | REST API 基址 |
| `BROKER_URL` | `tcp://...` | MQTT Broker |
| `VIDEO_FEED_URL` | `http://...` | 视频流地址 |
| `STORE_KEY_NICKNAME` | `'loggedInNickname'` | 昵称 AppStorage Key |
| `PREF_NAME_AUTH` | `'guardian_auth'` | 登录态偏好存储名 |

---

### components/ — 共享 UI 组件

#### GradientHeader.ets（19 行）
所有页面的蓝色渐变头部共享组件。使用方法：
```typescript
GradientHeader() {
  // 自定义内容放在这里
  Row() { Text('标题')... }
}
```
渐变值 `#1e40af → #3b82f6 → #60a5fa`、圆角 `6%`、`expandSafeArea(TOP)` 统一在此维护。

#### MenuRow.ets（56 行）
个人中心菜单行。参数：`imgRes`, `bgColorLight`, `bgColorDark`, `title`, `subTitle`, `onClickAction`。
自带按压态动画（深色 `#2a3a50` / 浅色 `#e8edf5`）。

#### StatDashboard.ets（39 行）
"XX天·已监护 | XX次·已预警" 统计卡片。参数：`useDays`, `totalAlertCount`。

---

### common/ — 服务层

#### CloudService.ets（130 行）
封装对 ECS Flask 后端 `/api/register`、`/api/login`、`/api/updateUser`、`/api/sendCode`、`/api/verifyCode`、`/api/changePassword` 的 HTTP POST 请求。所有方法失败时静默降级，不阻塞本地流程。

#### CloudSyncService.ets（143 行）
云端数据同步服务。当前 `preSyncOnAppStart()` 为空壳，`syncUserFromCloud()` 有实质逻辑但未被调用。

#### WenxinService.ets（122 行）
文心 AI 对话封装。核心方法：`chat(userMessage, history)` → 构建带健康摘要的请求 → POST `/ai/chat` → 返回 AI 回复。健康摘要从 MqttManager 提取脱敏统计（摔倒次数、久坐次数、距今天数）。

#### MqttParser.ets（56 行）
**纯函数模块，无副作用。** 导出：
- `payloadToString(payload)` — ArrayBuffer → 字符串
- `parseAlert(payload)` — 解析 JSON 并分类事件类型 → `{ type: EventType, raw: string }`
- `EventType` 枚举 — `FALL | SEDENTARY | STRANGER | NORMAL | UNKNOWN`

#### ThemeManager.ets（199 行）
单例。管理 `isDarkMode`、`colors`（ThemeColors 实例）、`themeMode`（跟随系统/浅色/深色）。通过 preferences 持久化用户选择。

#### UserManager.ets（64 行）
单例。统一入口管理当前登录用户的 username（读写 AppStorage）。

#### AudioTransferManager.ets（191 行）
音频通话管理。通过 WebSocket 实现双向对讲。

---

### database/ — 数据库

#### DatabaseHelper.ets（821 行）
**核心模块，最大单文件。** ArkDB 单例封装。

**数据表：**
| 表名 | 用途 |
|------|------|
| `t_user` | 用户账号（username/phone/email/password_hash/avatar_path/address） |
| `t_health_event` | 健康事件（摔倒/久坐，含时间、严重程度、处理状态） |
| `t_video_record` | 监控视频元数据（7 天滚动覆盖） |
| `t_setting` | 用户设置（key-value，云端同步） |

**关键方法：**
- `init(context)` — 初始化（幂等）
- `insertUser(user)` / `updateUser(user)` — 用户 CRUD
- `queryUserByIdentifier(id)` — 自动识别手机号/邮箱/用户名
- `queryHealthEvents(type, username)` — 按类型查健康事件
- `saveSetting(username, key, value)` / `loadSetting(username, key)` — 设置读写

---

### pages/ — 页面

#### Index.ets（64 行）
App 启动页。`checkAutoLogin()` 读 preferences 判断是否已登录 → 跳转 Layout 或 Login 页。

#### Layout.ets（111 行）
底部 4 Tab 导航（主页/记录/AI助手/个人）。使用 `Tabs` + `TabContent`，切换时带动画。

#### mainpage.ets（368 行）
**主页。** 三大区域：
1. `GradientHeader` — 标题"智护星" + LIVE 绿点呼吸动画
2. `VideoArea` — Web 组件嵌入视频流（在线/离线两态）
3. `StatusCards` — 设备状态卡 + 监测状态卡（摔倒/久坐变色）+ 人脸识别卡 + 音量滑块
4. 底部通话按钮

关键状态来自 `MqttManager`，每 100ms 轮询同步一次。

#### record.ets（234 行）
本会话事件记录。实时展示内存中的摔倒/久坐记录，支持时间线视图。

#### AiChat.ets（308 行）
AI 健康助手。顶部 GradientHeader + 健康概览卡片（摔倒/久坐次数），底部对话列表 + 4 个快捷问题 + 输入框。消息气泡支持 loading 动画（三点跳动）。

#### person.ets（602 行）
**个人中心。** 三大区域：
1. 头像 + 昵称（自 GradientHeader 组件）
2. 服务设置菜单（个人资料/人脸信息/常用地址/紧急联系人/历史记录）— 使用 MenuRow 组件
3. 系统偏好（外观模式切换/清理缓存/数据保留时长）
4. 退出登录按钮

人脸录入功能 `takePhotoAndSendToBoard()` 在此文件中（~90 行）。

#### Profile.ets（694 行）
**个人资料编辑。** 包含：
- 头像选择（相册选取 → 拷贝至沙箱）
- 昵称编辑（2-12 字校验）
- 手机号弹窗编辑（PhoneEditDialog）
- 邮箱弹窗编辑（EmailEditDialog）
- 密码弹窗编辑（PasswordEditDialog，含旧密码验证 + 云端兜底）
- 保存逻辑（先写本地 RDB → 异步同步云端）

#### Login.ets（844 行）
**最大页面文件。** 登录/注册合一：
- 手机号/邮箱 Tab 切换
- 自动识别格式、自动回填
- 新用户自动注册 + 设置昵称弹窗（NicknameDialog）
- 验证码弹窗（VerifyDialog，当前为测试模式）
- 渐变背景 + Logo 长按进入数据库诊断

#### HealthHistory.ets（267 行）
数据库历史记录。加载保留期内的摔倒/久坐事件，支持 Tab 切换和导出功能。

#### MyAddress.ets（157 行）
地址编辑页。从数据库加载 → 编辑 → 保存到本地 + 云端同步。

#### MqttManager.ets（513 行）
**MQTT 通信核心。**
- 连接管理：`connectAndSubscribe()` → Broker 连接 + 订阅 `ai_guardian/alerts/#`
- 消息处理：`handleMessage()` → 调用 MqttParser 分类 → 更新状态 + 写数据库 + 启动恢复定时器
- 设备健康检查：每 5 秒检查最近消息时间戳，20 秒无消息判定离线
- 状态暴露：`isFallDetected`、`isSedentaryDetected`、`isStrangerDetected`、`deviceOnline`、`latestMessage`（全部 `@Track` 装饰）
- 恢复定时器：摔倒 3 秒/久坐 3 秒/陌生人 5 秒后自动清除告警状态

#### DatabaseDiagnostic.ets（349 行）
数据库诊断工具。长按 Login 页 Logo 进入。可查看表结构、记录数、执行 SQL。

---

## 关键数据流

### 告警链路
```
开发板 MQTT publish → MqttManager.handleMessage()
  → MqttParser.parseAlert() 分类
  → MqttManager 更新 @Track 状态
  → mainpage / record 等页面轮询或响应式刷新 UI
  → 同时写入 DatabaseHelper (t_health_event 表)
```

### 登录链路
```
Login.ets 输入手机号/邮箱
  → DatabaseHelper.queryUserByIdentifier() 本地查
  → 有新用户 → 自动注册写本地 → CloudService.register() 异步同步云端
  → 有旧用户 → 密码校验（本地优先，失败走云端兜底）
  → Index.ets checkAutoLogin() 下次启动自动登录
```

### 主题切换链路
```
person.ets 点击外观模式
  → ThemeManager.setThemeMode() → 更新 isDarkMode + colors
  → 所有 @State themeManager 的组件自动重渲染
```

---

## 废弃/待清理

| 文件/功能 | 状态 |
|-----------|------|
| `CloudSyncService.preSyncOnAppStart()` | 空壳，仅打日志 |
| `Login.ets` VerifyDialog 验证码 | 测试模式，确认即通过 |
| `person.ets` 紧急联系人菜单 | 功能开发中（showToast 占位） |
| MqttManager 100ms 轮询 | 应用层同步状态，待改为事件驱动 |
