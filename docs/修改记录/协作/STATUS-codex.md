# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-05 · codex · T-20261105-07 · 待验证

> 分支：`wip/codex-20261105-face-preview-ratio` @ `3647e19`；修复人脸预览随手机/模拟器窗口非等比拉伸，签名 HAP 已覆盖安装两端。
> 下一步：用户解锁手机复测正脸比例；拍照后的确认图、重拍和上传链路未实测，保留 WIP，未合并 zy、未 push。

- 回退点 `backup/face-preview-before-20261105@e7c83ef`；复用 Codex 工作区，保留原有四处本机改动。
- 影响：`FaceEnrollment.ets`、`face/FacePreviewGeometry.ets`、`tests/face-preview-geometry.test.cjs`。
- 锁定 Surface 方向，使用相机实际预览旋转角交换流宽高，再等比居中裁切；响应窗口尺寸变化，取景椭圆按可用空间同比缩小。
- 照片输出优先匹配预览宽高比，并指定相机计算的拍照方向；未对上传原图做拉伸。
- Node 几何回归 6/6 通过（长屏、短屏、0/90/180/270°、横屏、正方形及竖向流）；diff --check 通过。
- DevEco 26.0.0.821 / SDK 26.0.0.105 / Hvigor 6.26.4 / HDC 3.2.0f；default/entry@default/release，签名构建成功（既有警告）。
- HAP：`entry/build/default/outputs/default/entry-default-signed.hap`，24,691,293 B，2026-11-05 15:41:49；SHA256 `766C6914E08DF478884B279200E2D1FDBE1F81BC2E95AFEEDECE6B7C217DBF7A`。
- API 24 模拟器覆盖安装/启动成功；沿用现有登录会话进入个人/人脸信息，用临时测试姓名进入采集页；相机已授权，无权限弹窗操作。
- 预览实际可用、按钮可用，取景框完整，截图已查看；按进程日志无 FATAL/JS_ERROR/Unhandled/相机启动及调整失败标记。已返回姓名页释放相机，未拍照或上传。
- USB 手机 API 26 覆盖安装成功；启动因锁屏返回 10106102，未解锁，真机比例未验收。
- 本地证据 `.tmp/simulator/face-ratio-20261105/` 被忽略，含私人画面，不提交/不分享。

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
