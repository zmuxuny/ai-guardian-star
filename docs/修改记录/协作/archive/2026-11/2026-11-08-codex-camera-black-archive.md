# Codex历史状态归档

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
