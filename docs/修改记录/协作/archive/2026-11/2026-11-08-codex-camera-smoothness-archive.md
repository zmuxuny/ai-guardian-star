# Codex历史状态归档

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
