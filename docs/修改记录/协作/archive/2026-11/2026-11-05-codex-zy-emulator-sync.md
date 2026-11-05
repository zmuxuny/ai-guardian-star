# Codex 模拟器同步归档

## 2026-11-05 · codex · T-20261105-05 · 已完成

> 分支：`wip/codex-20261105-zy-app-sync@298b83c`；复用最新 zy 整合版本签名 HAP，覆盖更新 API 24 模拟器成功。
> 下一步：用户在模拟器登录后检查个人/人脸信息入口；姓名、相机和姿态采集链路尚未验收。

- 通过 DevEco Emulator CLI 启动原 Pura X View，HDC 确认 emulator/API 24，目标 127.0.0.1:5555；未操作 USB 手机。
- HAP 与上一轮构建一致，24,686,693 B；SHA-256 `553D7101112155E483F4E8C6B3948DED130E097491ED6DD90C2E36D238936B59`；源码未变，未重复构建或测试。
- 安装前确认原 bundle 存在，覆盖安装和 EntryAbility 启动均返回成功；未卸载或清数据，实际停留在登录页，需要用户重新登录。
- 应用进程日志 319 行无 FATAL/JS_ERROR/Unhandled 标记；登录页截图已查看，证据 `.tmp/simulator/zy-sync-20261105/home.jpeg` 及布局/过滤日志均本地忽略。
- 未登录、未授予权限、未采集或上传人脸；未验证登录后页面、实时视频、录像或通话。
- 工具沿用 DevEco 26.0.0.821 / SDK 26.0.0.105 / Hvigor 6.26.4 / HDC 3.2.0f，default/entry@default/release，兼容及目标 API 24。
