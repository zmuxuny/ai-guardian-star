# 模拟器首页异常色块修复（2026-11-08）

- 任务：T-20261108-04；分支 `wip/codex-20261108-emulator-render`，源码基线 `b115a23`。
- 回退点：`backup/emulator-render-before-20261108`，原模拟器配置备份在本机 `.tmp/simulator/render-artifacts-20261108/config-before.ini`。
- 目标：Pura X View，HarmonyOS 6.1.1 / API24，HDC `127.0.0.1:5555`。USB 手机未操作。

## 复现和定位

用户截图中的大面积三角形、紫色条带，在 HDC 直接抓取的模拟器 framebuffer 中同样出现，因此不是电脑上的模拟器窗口缩放造成。
应用 force-stop 后重新启动，色块形状变化但没有完全消失；保留应用和数据，使用现有实例 `coldboot` 启动后恢复正常。结果支持模拟器运行/快照相关图形状态异常，尚未定位具体驱动内部缺陷。

## 实际修改

只修改本机 `D:\Huawei\Emulator\deployed\Pura X View\config.ini` 中一项：`isHotBoot=true` → `isHotBoot=false`，避免继续通过快速启动恢复旧运行状态。字节比对确认只改此项，CLI 实际读取到 `isHotBoot=false`。

此次没有修改 ArkTS、SVG、主题、API、签名或依赖；没有重新构建、覆盖安装、清除应用数据、恢复出厂设置，也没有操作服务器/开发板。原工作区的六处未提交修改保留。

## 验证

- 修复前：HDC 截图实际查看，确认首页大面积图形畸变。
- 仅重启应用：仍有畸变，不能作为修复。
- 完整冷启动：首页的图标、标题、卡片、底部导航恢复正常，异常色块消失。
- 点击“记录”：历史记录页正常显示，无大面积色块；返回“主页”后仍正常。
- 快速启动配置：备份、单项修改、实际读取与精确差异检查通过。尚未长期观察反复关机/启动后的行为，不承诺其他驱动问题永不发生。
- 最终状态：模拟器窗口保持打开，停在主页，原会话与本地记录保留。
- 有限日志样本未找到 FATAL / JS_ERROR；不据此声明整个应用无错误。

截图与日志仅保留在本机 `.tmp/simulator/render-artifacts-20261108/`，不提交账号数据、摄像头原图或原始日志。关键证据：`before.jpeg`、`app-restart.jpeg`、`home-after.jpeg`、`records-after.jpeg`、`final-home.jpeg`、`result.json`。

## 尚未通过的连接与业务项

摄像头当前显示“暂时无法获取画面”、通道异常；本机访问 `https://api.aistar.asia/video_preview` 时 HTTPS 握手超时。当前证据不能证明断点在服务器、代理、网络还是设备端，未改动生产连接配置。历史记录的服务器读取、视频流、权限、登录和端到端业务均不属于本轮图形修复通过项。

## 再次出现图形畸变时

先保存证据，再关闭该模拟器，使用对应 DevEco 的 Emulator 命令完整冷启动，保留用户数据：

```powershell
& "$HOME\Documents\DevEco Studio\tools\emulator\Emulator.exe" -stop 'Pura X View'
& "$HOME\Documents\DevEco Studio\tools\emulator\Emulator.exe" -start 'Pura X View' -instancePath 'D:\Huawei\Emulator\deployed' -imageRoot 'D:\Huawei\Sdk' -bootMode coldboot
```

不要使用 `reset`、删除实例或卸载应用来解决图形问题。需要回退快速启动设置时，关闭模拟器后恢复本机备份配置；不要覆盖运行中的用户数据镜像。
