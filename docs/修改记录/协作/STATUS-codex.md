# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

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

## 2026-10-27 · codex · T-20261027-01 · 已完成

> 分支：`ysh`，代码提交 `eb01e18` 已推送并核对远端 SHA；用户明确授权同步。
> 下一步：队友获取 origin/ysh，先读 docs/handoff-20261027.md；本轮不部署服务器或开发板。

### 交接

- 包含原本地 `1e2578a` 主页/事件配色及 `29edf9a` 队友录像日期加载合并，再加入当天事件页与方案三通话入口恢复。
- 最近两套实际 ArkTS 隔离检查各 12 项已通过，源码未再修改，按仓库规则不重复测试；两版构建、模拟器界面与离线通话反馈已验证。
- 模拟器现有最新 HAP SHA-256 `D31C90707B6FF62E10B6317CD3F8B60EBDA7F1690F2E7643D5C39A5CBFE738FA`；用户会话和数据保留。
- 真正陌生人告警、双向声音、录像下载播放与生产部署仍未现场验收；当前告警通道连接超时，不声称完整链路通过。
- 私人签名、`.wolf` 本机笔记、截图/日志及临时文件不进入提交；Git 使用单次 openssl 后端绕过本机 schannel 握手失败，不改远端或全局配置。
- 队友同步说明见 `docs/handoff-20261027.md`。
