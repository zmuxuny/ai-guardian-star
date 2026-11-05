# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-05 · codex · T-20261105-06 · 已完成

> 分支：`wip/codex-20261105-zy-app-sync@cd7e6f7`；将与模拟器一致的最新 zy 签名 HAP 覆盖同步到 USB 手机，安装和启动成功。
> 下一步：用户在手机登录后从个人/人脸信息检查新流程；相机授权、姿态采集、上传与真实设备链路尚未验收。

- 手机 MIA-AL00/nova 14 Pro（API 26），明确使用 USB 目标；未操作模拟器，未卸载或清数据。
- HAP SHA-256 `553D7101112155E483F4E8C6B3948DED130E097491ED6DD90C2E36D238936B59`，24,686,693 B；源码和包未变，复用此前成功构建，不重复构建或测试。
- 覆盖安装返回 install bundle successfully；EntryAbility 返回 start ability successfully，当前可达登录页，进程存在，按进程读取日志无 FATAL/JS_ERROR/Unhandled 标记。
- 本地布局 `.tmp/phone-validation-20261105/resync-layout.json` 被忽略；未截取个人资料，未登录、授权相机/麦克风或上传数据。
- 保留现有四处本机改动；仅本地协作记录提交，未 push 或部署服务器/开发板。

## 2026-11-05 · codex · T-20261105-05 · 已完成

> 分支：`wip/codex-20261105-zy-app-sync@298b83c`；复用最新 zy 整合版本签名 HAP，覆盖更新 API 24 模拟器成功。
> 下一步：用户在模拟器登录后检查个人/人脸信息入口；姓名、相机和姿态采集链路尚未验收。

- 通过 DevEco Emulator CLI 启动原 Pura X View，HDC 确认 emulator/API 24，目标 127.0.0.1:5555；未操作 USB 手机。
- HAP 与上一轮构建一致，24,686,693 B；SHA-256 `553D7101112155E483F4E8C6B3948DED130E097491ED6DD90C2E36D238936B59`；源码未变，未重复构建或测试。
- 安装前确认原 bundle 存在，覆盖安装和 EntryAbility 启动均返回成功；未卸载或清数据，实际停留在登录页，需要用户重新登录。
- 应用进程日志 319 行无 FATAL/JS_ERROR/Unhandled 标记；登录页截图已查看，证据 `.tmp/simulator/zy-sync-20261105/home.jpeg` 及布局/过滤日志均本地忽略。
- 未登录、未授予权限、未采集或上传人脸；未验证登录后页面、实时视频、录像或通话。
- 工具沿用 DevEco 26.0.0.821 / SDK 26.0.0.105 / Hvigor 6.26.4 / HDC 3.2.0f，default/entry@default/release，兼容及目标 API 24。

## 2026-11-05 · codex · T-20261105-04 · 已完成

> 分支：`wip/codex-20261105-zy-app-sync`；整合 `origin/zy@d903e20` 与本地 `ysh@3acec5e`，代码和路由与远端 zy 一致。
> 下一步：用户解锁手机后启动，验收个人页/人脸信息/姓名页；相机、三姿态采集及上传需用户参与；保留在 WIP 分支直至实际验收。

- 已同步人脸姓名与独立采集页、严格姿态门禁、板端探针等 23 个文件；业务代码无冲突，无额外源码修改，双方协作记录均保留归档。
- Release 签名构建成功；HAP `entry/build/default/outputs/default/entry-default-signed.hap`，24,686,693 B，2026-11-05 15:21:29。
- SHA-256 `553D7101112155E483F4E8C6B3948DED130E097491ED6DD90C2E36D238936B59`；USB 手机覆盖安装返回 install bundle successfully，未卸载或清数据。
- 启动返回 10106102（手机锁屏，开发者模式不允许自动解锁）；未操作锁屏、登录、相机/麦克风权限、采集或上传，未做真机功能通过声明。
- 业务源码与远端一致；远端记录的 Node 15 项和 Python 78 项已通过，本轮未重复执行；合并冲突解决后 diff --check 通过。
- 回退分支 `backup/ysh-before-zy-app-sync-20261105@3acec5e`；签名配置、笔记及补丁已在本机私有目录备份，原有四处本机改动保留。
- 未 push、未部署服务器或开发板；本地记录 `.tmp/zy-sync-20261105/` 被忽略，不保存锁屏截图。
