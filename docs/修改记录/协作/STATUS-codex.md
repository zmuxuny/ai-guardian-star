# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-05 · codex · T-20261105-03 · 待验证

> 分支：`ysh@9fe9e2a`；业务代码 `843dbe3`，用户完成华为登录后已更新自动签名、重新构建并成功安装 USB 真机。
> 下一步：用户手动解锁手机并保持亮屏后启动应用；如出现协议、登录或敏感权限提示，由用户本人完成，再检查可达功能。

- 手机：MIA-AL00（nova 14 Pro），API 26；未记录设备标识或账号资料到 Git。
- 新签名 Release HAP：24,661,497 B，2026-11-05 15:10:33；SHA-256 `45A25EA8513E74E3258D7C4D5A91DFF311ED207EAE6E03AE575CB0C97630A431`。
- 构建 BUILD SUCCESSFUL，安装返回 install bundle successfully；此前 Profile 未授权错误 9568423 已解决，bm dump 确认 1.0.1/1010001，兼容及目标 API 24。
- 启动返回 10106102：开发者模式下手机锁屏，系统不允许自动解锁；已请用户手动解锁，未尝试绕过锁屏或关闭开发者模式。
- 原签名材料及 build-profile 已在本机私有目录备份；新签名配置仅本地保留，不提交密码或材料。两份 oh-package-lock 的已有变更保留，git diff 无内容变化。
- 本轮未卸载、未清数据、未改业务源码、未授权相机/麦克风；真机功能仍未验收。
- 本地记录：`.tmp/phone-validation-20261105/preflight.md`；未保存锁屏截图，避免收集通知等私人信息。

## 2026-11-05 · codex · T-20261105-02 · 已完成

> 分支：`ysh@6b2cad0`；业务代码 `843dbe3` 已签名构建并覆盖安装到 API 24 模拟器。
> 下一步：开发板视频和录像服务恢复后验证实时画面、在线播放、拖动和下载；本轮未部署云端或开发板、未操作真机。

- 工具：DevEco 26.0.0.821，SDK 26.0.0.105，Hvigor 6.26.4，Node 24.14.1，HDC 3.2.0f；default/entry@default/release，目标与兼容 API 24。
- 产物：`entry/build/default/outputs/default/entry-default-signed.hap`，24,661,439 B，2026-11-05 14:50:39；SHA-256 `D41C62002A4730888D0849FB6DBD5BC3AD85ADE2D85281B8DF292DEFAA1D3AEF`。
- `127.0.0.1:5555` 确认为 emulator/API 24；覆盖安装和 EntryAbility 启动均返回成功，原有登录会话保留；未卸载或清数据。
- 实际访问主页与记录页，再返回主页；记录页出现新版在线播放/下载说明和日期分组。应用进程日志 620 行中无 FATAL/JS_ERROR/Unhandled 标记。
- 限制：主页显示暂时无法获取画面，录像查询提示开发板录像暂不可用；未验证真实播放、下载、告警或双向声音。
- 本地证据：`.tmp/simulator/sync-20261105-1450/` 的 ready/records JPEG、布局与筛选日志；目录被 Git 忽略，不提交。
- 仅更新协作记录，原 `.wolf/cerebrum.md` 和 `build-profile.json5` 本地改动保留；首次 HDC 路径使用正斜杠失败，改 Windows 原生路径后安装成功。

## 2026-11-05 · codex · T-20261105-01 · 已完成

> 分支：`ysh`；从 `8267c85` 快进到 `origin/feature/jyx-home@843dbe3`，同步 12 个队友提交。
> 下一步：需要运行新版时按 DEVECO_BUILD.md 构建安装；本轮只同步源码，未 push、未部署。

- 影响：录像在线播放、批量查询、实时画面质量及断流重连等 19 个文件；未额外合入 `origin/zy@a8bc088` 的头姿探针。
- 回退点：`backup/ysh-before-sync-20261105@8267c85`；原有两处本地修改已在用户目录 Documents/Codex/backups/caringSystem-20261105-sync 备份。
- 验证：快进无冲突；本地构建配置与项目笔记文件和备份 SHA-256 一致；`git diff --check` 通过。
- 未验证：本轮未构建、未安装、未进行设备或服务端验收；队友记录不能代替本轮现场验证。
