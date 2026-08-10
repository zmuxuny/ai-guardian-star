# Changelog

所有重大变更将在此记录。遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式。

## [Unreleased]

---

## [0.2.0] — 2026-08-10

### Added
- 深色模式全局适配（跟随系统 / 手动切换）
- 文心 AI 健康助手 + 扣子智能体对话
- 个人资料编辑（手机号、邮箱、密码修改 + 验证码）
- 健康历史记录页
- 紧急联系人入口（开发中）
- AI 语音通话功能

### Changed
- 包名改为 `com.jianyuanxi.guardianstar`，厂商名 `Jianyuan Xi`
- 主题管理器全局统一（`@Observed` + `@Track` 响应式）
- 用条件渲染替代 Tabs 组件
- 路由器由 `route_map.json` 统一管理
- 语义文字色（链接/成功/警告/危险）收敛到 ThemeManager，取值满足华为无障碍对比度要求
- Login 顶部渐变与表单卡片、Index / 注销弹窗宽度改为内容驱动，修正平板观感

### Removed
- 数据库诊断页及其残留入口、辅助方法与文档条目

### Fixed
- 登录参数缺失（HTTP 400）
- Tab 页面状态丢失
- StatDashboard 遮挡问题
- 华为账号登录按钮 DB 同步
- 注册昵称必填校验
- 代码混淆后字段名被重命名

### Security
- 开启 Release 代码混淆
- 证书/混淆规则 keep-list 补全
- 账号注销改用绑定手机号/邮箱的一次性验证码，不再提交密码
- 云端头像管理与多设备同步
- 用户管理后台重构 + 安全账号操作

---

## [1.0.0] — 2026-03 ~ 2026-05

### Added
- 用户注册/登录（手机号 + 密码 + 验证码）
- 智能居家监护主页（视频流 + AI 状态 + 摔倒记录）
- MQTT 实时数据推送
- 云端账号同步（CloudService / CloudSyncService）
- ArkDB 本地数据库（用户、健康记录）
- 个人中心（资料、地址、健康历史、数据库诊断）
- 华为 Account Kit 登录
- 平板/手机双设备适配
