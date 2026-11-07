# Codex 历史状态归档

## 2026-11-05 · codex · T-20261105-08 · 已完成

> 分支：`wip/codex-20261105-home-camera-latency` @ `0157966`（已 push）；手机已更新，用户挥手复测确认“明显改善，已能接受”。
> 下一步：保留当前低延迟参数；未合并 zy，未更新开发板推理/录像逻辑。未测量物理动作到屏幕显示的精确毫秒值。

- 回退点 `backup/home-camera-latency-before-20261105@84e342a`，保留原有四处本机改动。
- 影响：`CameraStreamView.ets`、`MjpegPage.ets`、`tests/camera-latest-frame.test.cjs`、`deploy/aliyun/api.aistar.asia.conf`。
- 持续 MJPEG 改为串行获取最新 JPEG，下载/解码完成后再取下一帧；5 秒超时取消，失败重试，切后台/退出中止请求并释放 Blob。
- 第一版手机出图后用户反馈仍延迟约 1～2 秒；第二版增加云端轻量接口：首页 `/video_preview` 320×240/质量50，全屏 `/video_preview_full` 480×360/质量55，原 `/video_feed`、`/video_frame` 保留。
- Node 行为回归 7/7：单请求、解码背压、超时取消、旧请求失效、204重试、后台停用、URL释放/错误图恢复；diff --check 通过。
- DevEco 26.0.0.821 / SDK 26.0.0.105 / Hvigor 6.26.4 / HDC 3.2.0f；default/entry@default/release，签名构建成功。
- 最终 HAP `entry/build/default/outputs/default/entry-default-signed.hap`：24,698,570 B，2026-11-05 16:20:59；SHA256 `EA981C69ADC09D0E18348CCABACB6FB358958EBC7CB2BB95D6837059E7A101C8`。
- USB 手机 API26 和模拟器 API24 覆盖安装及启动成功；手机首页/首版全屏实际出图，最终首页出图并获用户延迟验收；日志无 FATAL/JS_ERROR/Unhandled/ERR_/loadData失败标记。
- 云端实际配置 `/www/server/panel/vhost/nginx/api.aistar.asia.conf` 只增两处 location；备份 `/root/backup/home-camera-latency-20261105-162203/`，nginx -t 和平滑 reload 成功，nginx/wenxin 均 active。
- 抽样原 JPEG 40,102 B，首页11,157 B（约减少72%），全屏20,614 B；接口返回200。响应时间是网络请求耗时，不能当物理端到端延迟。
- 部署顺序：回退点/配置备份→本地测试/签名构建→push WIP→云端最小补丁→安装手机/模拟器→用户复测；首次部署脚本因远端Python3.6参数不兼容未reload，已恢复配置、修正脚本后成功部署。
- 开发板 SSH 认证未通过，未改板端；所有截图与私有画面仅在被忽略的 `.tmp/simulator/home-latency-20261105/`，不提交。
- 回滚：恢复上述 nginx 备份并 `nginx -t` 后 reload；App 可回退此前 HAP/代码。未卸载或清数据，未发起通话或上传人脸。
