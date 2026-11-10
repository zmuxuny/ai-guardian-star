# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-10 · codex · T-20261110-01 · 待验证

> 分支 `wip/codex-20261110-home-review@7d6ee20`，改动 `entry/src/main/ets/pages/Layout.ets`。
> 下一步由用户审核已安装的首页留白调整。真机和非空事件列表未实测。

- 页面底色延伸到系统手势区。签名 HAP 构建、Mate 90 Pro（API 26）覆盖安装、首页与记录页切换通过。原白色区域像素与页面浅蓝 #F0F4FF 一致。
- HAP 24,712,747 字节，SHA256 `1D48CEA78DB16259DA29870B4251DB71073016C195524F9341E631846A51FCCF`。
- 首页提交 `1c57ffa` 修改 `mainpage.ets`。保持原模块顺序，仅在高屏事件空态分配间距。构建、覆盖安装、首页实图通过。底部开放间距在同列实测约 665 → 206 像素。
- 新 HAP SHA256 `037675FF6CDC67E67D92035CD064EB5FDCFB07686511B8F753C2576B0B48FBA0`。前后实图与旧包备份在本机 `.tmp/simulator/home-spacing-review-20261110/`。
- 临时构建配置已恢复。已按用户要求推送协作分支，GitHub 回查确认包含审核版提交 `58c6456`，队友可拉取继续修改。

## 2026-11-09 · codex · T-20261109-03 · 已完成

> 分支 `wip/codex-20261109-glass-tab@4d278f6`，基于人脸样式版本 `a9d255d`。新增 GlassBottomBar，接入 Layout 和四个页面的滚动。
> Mate 90 Pro（API 26）已覆盖安装并返回首页。真机、深色和大屏未实测。

- 参考 Jianyuanxi/GlassTabBar。使用 ArkUI 原生背景模糊、饱和度和高光。实现浮动胶囊、选中块浮起与局部染色、松手吸附和滚动收窄。
- Android 的透镜折射、色散和震动未移植。保留原 AI 入口开关和宽屏侧栏。
- 签名 Release HAP 24,712,958 字节，SHA256 `ae5894a41289a51bbdd1c9fc0d1639289d17422800105886ec30364c1942cd33`。临时构建配置和锁文件改动已恢复。
- HDC 实测四入口、记录横拖至个人、个人页收窄/展开、返回主页。拖动中实图看到选中胶囊浮起。截图本机 `.tmp/simulator/glass-tab-20261109/`。
- 摄像头和录像业务未验收。记录页实际提示录像暂不可用。仅本地提交。

## 2026-11-09 · codex · T-20261109-02 · 已完成

> 分支 `wip/codex-20261109-face-style@d3dfbfc`。影响 `entry/src/main/ets/pages/FaceEnrollment.ets`。
> Mate 90 Pro（API 26）已覆盖安装，停在姓名页。采集、上传和真机待验证。

- 复用首页主题色、白色圆角卡片与按钮风格。状态栏、标题区、主体和底部操作区使用连续浅蓝底色。
- 签名 Release HAP 构建通过，SHA256 `4b6102351c5095b1d36a06fcfe34f98368a34132e45380d29ab0bfd4a9703a5e`。临时构建配置已恢复，预览几何测试 6 项通过。
- HDC 从个人页进入人脸信息并实图检查。截图侧边六处背景均为 #F0F4FF。证据在本机 `.tmp/simulator/face-style-20261109/`。
- 仅本地提交，下一步如需验收采集与上传，在授权测试设备上执行。
