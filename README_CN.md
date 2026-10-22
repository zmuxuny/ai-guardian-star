# 智护星（昇腾边缘端）

本仓库当前包含运行于昇腾开发板的 Python 服务端：摄像头采集、姿态推理、跌倒与久坐判断、人脸识别、网页状态页、对讲和 MQTT 告警。HarmonyOS 客户端工程不在本仓库中。

## 目录说明

- `src/ascend_board_server.py`：FastAPI 服务入口，网页、视频、状态、WebSocket 对讲和人脸管理接口。
- `src/ascend_main_other.py`：当前服务使用的 ACL Lite 推理、跟踪、告警和人脸识别实现。
- `src/ascend_video_stream.py`：线程安全的视频帧和运行状态缓存。
- `src/ascend_voice_stream.py`：PyAudio/ALSA 采集、播放和设备选择。
- `src/ascend_audio_output.py`：当系统没有可用播放设备时，尝试加载板载耳机动态库。
- `src/acllite/`：昇腾 ACL Lite Python 与本地库支持文件。
- `*.om`、`*.onnx`：模型文件；多个同名变体的来源和用途尚未完整记录，使用前请对照 `MODEL_PATH` 配置。
- `data/test/` 和根目录媒体文件：开发样例数据，不参与默认在线推理。

`src/ascend_main.py`、`src/dt_pref.py`、`src/detect.py` 和 `src/object_detect.py` 是独立或较早的样例实现，不是 `ascend_board_server.py` 当前启动链路的一部分。

## 运行环境

服务依赖昇腾 CANN/ACL Lite、板端 OpenCV、摄像头和音频系统。请在已安装并配置对应 CANN 环境的开发板上运行；普通 Windows 环境不能替代板端推理验证。

```bash
# 按开发板实际安装位置加载 CANN 环境
source /usr/local/Ascend/ascend-toolkit/set_env.sh

# 安装 Python 服务依赖；ACL、OpenCV 等板端原生组件需使用设备匹配的版本
python3 -m pip install -r requirements-edge.txt

# 从仓库根目录启动，默认网页端口为 5000
python3 src/ascend_board_server.py
```

默认人体模型从 `src/best.om`、当前目录的 `best.om` 等候选路径中查找。若需指定数据库位置，可设置 `AI_GUARDIAN_DB_PATH`。

人脸管理接口默认关闭。启动前配置仅保存在设备环境变量中的管理员令牌：

```bash
export AI_GUARDIAN_FACE_ADMIN_TOKEN='请替换为本机生成的长随机令牌'
```

调用人脸录入、删除和列表接口时，通过 `X-Admin-Token` 请求头提交该令牌。不要把实际令牌写入仓库、脚本或日志。

板载 3.5 mm 耳机输出是可选后备路径，需要部署与设备匹配的 `src/libguardian_audio.so`；缺少它不会阻止其他可用的 PyAudio 输入/输出设备启动。该动态库目前不随仓库提供。

## 接口

- `GET /`：服务端内嵌状态页面。
- `GET /api/stats`：运行状态和检测统计。
- `GET /video_feed`：MJPEG 视频流。
- `WS /ws/intercom`：浏览器与开发板双向 PCM 对讲。
- `/api/face/*`：需配置管理员令牌的人脸管理接口。

## 验证边界

静态语法检查和 Windows 上的轻量检查不能验证 ACL 模型、摄像头、ALSA/PyAudio、板载动态库或 MQTT Broker。部署前应在目标板分别确认服务启动、视频帧更新、双向对讲、人脸录入/删除和告警链路。

## 修改记录与离线检查

开发板 24 小时连续录像与七天异常片段的当前适配见 [开发板 24 小时录像说明](docs/board-24h-recording.md)。两条录像链路均为显式配置启用；真实摄像头、编码负载、长期存储及手机回放仍需在开发板和手机上验证。早期方案和准备阶段记录分别见 [全天录像与七天缓存预案](docs/全天录像与七天缓存预案.md) 与 [录像代码预处理说明](docs/录像代码预处理说明.md)。

每次修改和优化的原因、影响文件、提交号、验证结果、待验证事项与回退方法记在 [修改记录索引](docs/修改记录/README.md)，并随代码推送到 `zy`。运行代码最近记录：[2026-10-19 运行稳定性优化](docs/修改记录/2026-10-19-运行稳定性优化.md)。

运行不依赖 ACL、摄像头或音频设备的回归测试：

```bash
python -m unittest discover -s tests -v
```

这些测试检查计时、告警事件和隔离的控制流，完整服务仍需开发板验证。
