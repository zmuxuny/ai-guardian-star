# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-01

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- **修复后及时推送**：修复一个问题、确认没问题之后，必须立即 commit + push，不要积攒多个修复再一次推送。

## Key Learnings

- **Project:** caringSystem
- **Description:** <div align="center">
- **Layout.ets 已改为 Stack + visibility 常驻方案（2026-05-06）**：去掉 Tabs，每页用 Stack 叠加 + `visibility(Visible/None)` 控制显示，底部用自定义 Row。四页始终挂载不销毁，切 tab 保留聊天/输入/滚动状态。Tabs 层的 expandSafeArea + backgroundColor 冲突问题彻底消除，每页完全独立控制自己的顶部安全区
- **Record 页面模式（标准参考）**：GradientHeader 不带 expandSafeArea（仅用 topSafeHeight padding） + 圆角底部 + 紧随其后的卡片用负 margin（-4%）叠入渐变区域形成过渡桥
- mainpage：VideoArea 移出 Scroll 并用负 margin 叠入渐变头部，模仿 record 的 StatDashboard 过渡模式
- AiChat：新增 HealthOverview 卡片（复用 MqttManager 数据），置于 GradientHeader 与 Scroll 之间，用负 margin 叠入渐变
- person：StatDashboard 已有负 margin，仅需保持 GradientHeader 与 record 一致（无 expandSafeArea + borderRadius）

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-05] **主页面响应式改造时，不要把共享卡片（平板和手机共用）的 padding/margin/borderRadius 从百分比改成 rSize() 像素值。** 手机端应该保留原来的百分比值，只有平板特有的双列布局区域才用 rSize()。正确做法：共享区域保持百分比值，平板特有区域用 rSize() + constraintSize。
- [2026-05-05] **loginComponentManager.HuaweiIDCredential 和 authentication.LoginWithHuaweiIDResponse 是 Account Kit 中两个不同 API 体系的类型，不能互相强转。** LoginWithHuaweiIDButton 的回调参数类型是 loginComponentManager.HuaweiIDCredential，它的结构可能是 { data: jsonString } 或直接展开的对象，需要防御式解析。

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- **2026-05-02: Tabs → 条件渲染 + 悬浮底栏** — Tabs 的 expandSafeArea(TOP) + backgroundColor 与各页面 GradientHeader 的 expandSafeArea(TOP) 三层叠加冲突，导致反复出现顶部白块/黑块。去掉 Tabs 后每页独立控制安全区，无冲突。同时将底栏改为 iOS 风格悬浮胶囊（backdropBlur + 圆角 + 阴影），视觉更现代。
