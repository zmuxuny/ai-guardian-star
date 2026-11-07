# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-07 · codex · T-20261107-01 · 已完成

> 分支：`wip/codex-20261107-device-skills`；应用源码基线 `44025cf`，本轮仅安装本机技能与记录文档。
> 下一步：连接真机或 Android 目标后按场景执行验收；不将工具检查算作业务验收。

- 四个 skill 保存到 `$HOME/.codex/skills`；原始文件、适配版 ZIP、哈希、说明与检查脚本在 `$HOME/.codex/skill-validation/android-device-20261107/`。
- 修正 Claude 技能目录及不存在的 E 盘工具链路径；未改项目源码、签名、API、依赖或原工作区六处未提交改动。
- 构建辅助脚本 Toolchain/Discover/Artifact 三模式通过；检查的是已有 HAP，未重构建/重签/重装。
- 官方 ADB 37.0.1 已安装，实际枚举通过，无就绪 Android 目标；未安装额外 APK。
- 本地技能检查与 Android 合成样例 7 组通过；项目现有会话静态契约 21/21 通过。
- API24 Pura X View 模拟器无窗口启动后成功连接 HDC，属性/布局/截图回传通过；截图实际查看为锁屏，未进入业务应用。
- 原始模拟器启动日志含快照恢复错误，随后同一次启动自行恢复；没有 reset、清数据或冷启动重试。
- 真机、Android UI、应用安装/运行/权限/网络/端到端、Asset Store 运行时与服务端会话撤销均未验收。
- 细节及复用命令：`docs/DEVICE_SKILLS_SETUP_20261107.md`。仅本地提交，不 push、不合并 zy、不部署。

## 2026-11-05 · codex · T-20261105-10 · 已完成

> 分支：`wip/codex-20261105-camera-black` @ `1fbabac`；模拟器黑屏已实际复现并修复，首页/全屏/返回及手机首页均已看到画面。
> 下一步：GitHub可用时补推；未合并zy。云端/开发板本轮未修改。

- 回退 `backup/camera-black-before-20261105@10cc779`；保留原有四处本机改动。
- 黑屏时Web仍输出约8～11fps解码指标；网络已收到JPEG，模拟器截图却为纯黑。Web渲染模式、尺寸及固定画布尝试无效，均已撤回；未确认具体GPU/驱动内部原因。
- 改为 `CameraFrameClient.ets` 原生HTTP取帧、ImageKit解码、ArkUI Image显示，绕过模拟器Web显示链路；ready由原生Image完成事件确认。
- `CameraStreamView.ets` 保留最新帧序号去重、单请求调度、隐藏/退出取消、过期请求失效、断流重试；保留前两帧直到新图附着，退出释放位图。
- 新增 `tests/camera-native-frame.test.cjs`：7/7通过（正常解码/资源释放、重复帧、204、坏图、网络失败、取消、超大响应）。
- 最终签名Release构建成功；HAP 24,697,840B，2026-11-05 16:56:05；SHA256 `04D9DA0A97A0C119E0F63EED3AB2D1C03F7145DAF0C5073E12A03D1CC5B3C6C9`。
- API24模拟器已覆盖安装、启动；首页、全屏、返回首页实际截图已看，最终首页正常；API26手机覆盖安装/启动及首页截图正常，无卸载/清数据。
- 最终抽样模拟器8.7～8.9fps、取帧49～55ms、解码4～5ms；手机6.7～8.3fps、取帧40～45ms、解码7～10ms；属短窗口指标，不代表精确物理端到端延迟。
- 两端日志无FATAL/JS_ERROR/Unhandled/ERR_标记；本地证据 `.tmp/simulator/camera-black-20261105/` 已忽略，不提交私有画面或原始日志。
- 工具沿用DevEco26.0.0.821/SDK26.0.0.105/Hvigor6.26.4/HDC3.2.0f；default/entry@default/release，API24目标；未升级依赖。

## 2026-11-05 · codex · T-20261105-09 · 已完成

> 分支：`wip/codex-20261105-camera-smoothness`；调度/连接复用 `d0cfcf3` 已push，共享最新帧 `b0289d0` 待补推；云端部署/两端更新完成，用户确认“卡顿明显改善，可以接受”。
> 下一步：GitHub恢复后补推；保留当前参数，仍可能受板端/公网瞬时停顿影响。细节及回滚见 `docs/CAMERA_PREVIEW_SMOOTHNESS_20261105.md`。

- 回退 `backup/camera-smoothness-before-20261105@43e2fdd`；保留原有四处本机改动，未合并zy。
- 手机到云端ping 6/6、15～18ms无丢包；云端流抽样14.03～14.37fps；逐帧取图偶发数百ms～数秒，解码稳定约10～15ms。
- 去掉每帧后固定80ms等待；仅保留一个请求，按总耗时调度；源序号去重；新增聚合性能日志（无个人/画面数据）。
- 云端独立标准库服务复用一条MJPEG连接并只保留最新JPEG，回环6011供两种轻量预览读取；过期204、断流清空重连；原始视频与识别/录像逻辑未改。
- Python 4项、Node 11项通过；Release签名构建和两端覆盖安装/启动通过；手机首页已检查，日志无FATAL/JS_ERROR/Unhandled/ERR_。
- 真机多窗口实测9.3～10.5不同源帧/秒，请求48～64ms、解码9～13ms；后续仍采到一次2337ms源停顿，未宣称完全消除网络波动或精确物理端到端延迟。
- HAP 24,697,163B，2026-11-05 16:34:36；SHA256 `5111B4DC0BD58034D6DA24DDF7BE8AFB03EFEA8141E7ABC136C99D02CE581A0D`。
- 云端备份 `/root/backup/camera-shared-frame-20261105-163750/`；unit校验、nginx -t/reload成功；预览服务/Nginx/wenxin均active，预览服务约10MB、4线程、NRestarts=0。
- GitHub经现有SSH隧道及替代IP均超时；用户明确允许先部署再补推。新代码已本地提交，记录推送结果以最终回复为准。
- 所有截图、私有画面和原始设备日志仅在被忽略的 `.tmp/simulator/camera-smoothness-20261105/`；未发起通话或上传人脸。
