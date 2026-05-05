# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-01

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->

## Key Learnings

- **Project:** caringSystem
- **Description:** <div align="center">
- **Layout.ets 已改为条件渲染 + 悬浮底栏方案（2026-05-02）**：去掉 Tabs，每页用 `if (currentIndex === N)` 条件渲染，底部用自定义 Row 实现 iOS 风格悬浮底栏。Tabs 层的 expandSafeArea + backgroundColor 冲突问题彻底消除，每页完全独立控制自己的顶部安全区
- **Record 页面模式（标准参考）**：GradientHeader 不带 expandSafeArea（仅用 topSafeHeight padding） + 圆角底部 + 紧随其后的卡片用负 margin（-4%）叠入渐变区域形成过渡桥
- mainpage：VideoArea 移出 Scroll 并用负 margin 叠入渐变头部，模仿 record 的 StatDashboard 过渡模式
- AiChat：新增 HealthOverview 卡片（复用 MqttManager 数据），置于 GradientHeader 与 Scroll 之间，用负 margin 叠入渐变
- person：StatDashboard 已有负 margin，仅需保持 GradientHeader 与 record 一致（无 expandSafeArea + borderRadius）

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- **2026-05-02: Tabs → 条件渲染 + 悬浮底栏** — Tabs 的 expandSafeArea(TOP) + backgroundColor 与各页面 GradientHeader 的 expandSafeArea(TOP) 三层叠加冲突，导致反复出现顶部白块/黑块。去掉 Tabs 后每页独立控制安全区，无冲突。同时将底栏改为 iOS 风格悬浮胶囊（backdropBlur + 圆角 + 阴影），视觉更现代。
