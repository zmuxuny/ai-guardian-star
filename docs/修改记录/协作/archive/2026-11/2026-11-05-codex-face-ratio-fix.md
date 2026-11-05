# 人脸预览比例修复归档

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
