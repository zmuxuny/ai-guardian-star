# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

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
