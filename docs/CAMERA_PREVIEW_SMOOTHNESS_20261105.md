# 摄像头预览卡顿检查与改进（2026-11-05）

## 结论与范围

手机到阿里云 ICMP 6/6 返回，15～18 ms、无丢包；这只能说明该段基础网络正常，不能证明开发板公网/FRP 段无波动。云端持续 MJPEG 抽样约14帧/秒；逐帧请求时，手机取帧偶尔数百毫秒到数秒，解码约10～15 ms。因此主要瓶颈是跨隧道逐帧请求的等待和波动，以及旧客户端每帧完成后的额外80 ms等待。

修复后手机连续几个5秒窗口约9.3～10.5个不同源帧/秒，请求48～64 ms、解码9～13 ms；用户挥手复测确认“卡顿明显改善，可以接受”。后续仍采到一次源端停顿：最大显示间隔2337 ms，不能宣称彻底消除上游抖动。未用同步拍摄测量物理动作到显示的准确延迟。

## 实现

- App 调度改为让网络和解码时间计入67 ms的目标周期（最多约15 fps），慢请求完成后不再固定多等80 ms。
- 仍只有一个下载/解码任务；相同 `X-Camera-Sequence` 不重复解码、不计作新帧。
- 新增 `guardian-camera-preview.service`：使用既有Python3.11标准库，监听回环6011；一条连接持续接收回环6001的MJPEG，内存槽只保留最新JPEG。
- `/video_preview`、`/video_preview_full` 通过 Nginx 从6011取最新帧并继续缩放；原 `/video_feed`、`/video_frame` 保留。
- 1.5秒内无新帧返回204，源断线清空帧并重连；内存JPEG大小有上限，不保存图片或视频。
- `X-Camera-Frame-Age-Ms` 是云端收到帧后的时间，不是摄像头采集到手机显示的延迟。
- App 每5秒输出仅含帧率、请求/解码时间及最大帧间隔的聚合日志，不记录画面、账号或人脸标签。

## 验证与部署

- Python 4项回归通过：分片/合并帧解析、超大帧限制、最新帧淘汰/过期、多次HTTP读取同一槽及204。
- Node 11项通过，含超时、后台停止、Blob释放、慢请求不加额外等待、目标帧率上限和同源帧去重。
- Release签名构建、手机API26及模拟器API24覆盖安装/启动成功；手机首页实际出图，日志无FATAL/JS_ERROR/Unhandled/ERR_等标记。
- systemd unit校验、nginx -t、平滑reload通过；预览服务、Nginx、wenxin均active。预览服务抽样内存约10 MB、4线程、0次重启。
- 用户允许本次在GitHub故障时先部署后补推；未合并zy，未改开发板推理、识别或录像代码。

## 回滚

云端配置备份：`/root/backup/camera-shared-frame-20261105-163750/`。恢复其中 `api.aistar.asia.conf` 到 `/www/server/panel/vhost/nginx/api.aistar.asia.conf`，先 `nginx -t` 再平滑reload，然后 `systemctl disable --now guardian-camera-preview.service`。无需回滚数据库或开发板。

源码为 `deploy/camera_frame_relay.py`，服务文件为 `deploy/aliyun/guardian-camera-preview.service`；部署副本在 `/opt/wenxin/app/camera_frame_relay.py`、`/etc/systemd/system/guardian-camera-preview.service`。

HAP：`entry/build/default/outputs/default/entry-default-signed.hap`，24,697,163 B，2026-11-05 16:34:36，SHA256 `5111B4DC0BD58034D6DA24DDF7BE8AFB03EFEA8141E7ABC136C99D02CE581A0D`。
