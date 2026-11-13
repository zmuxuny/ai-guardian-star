# Orange Pi AI Pro 板载耳机输出

3.5mm 耳机口通过 Ascend MPI AO 输出，不在 ALSA/PyAudio 播放设备列表中。USB 仅供电的音响需要同时接耳机线。USB 麦克风继续使用现有 PyAudio 输入。

`ascend-audio-output.patch` 在 PyAudio 没有输出设备时加载 `ascend_audio_output.py`；桥接使用原厂 AO device 2/channel 0，48 kHz、单声道 S16 PCM，每帧 960 点。每 20 ms 从现有播放缓冲读取一帧，保留原有超时补零和积压裁剪。发送失败会关闭输出状态，不将失败显示为正常播放。

`ascend_audio_output.c` 由当前板端 CANN 头文件编译，避免手写 ctypes 结构体 ABI。`hi_mpi_sys_init` 按官方要求在当前进程幂等初始化；绝不调用 `hi_mpi_sys_exit`，避免撤销同进程摄像头/NPU使用的媒体系统。只关闭本桥接成功启用的 AO 通道和设备。

## 部署

先备份原始 `ascend_voice_stream.py`，确认补丁只改变无输出设备分支；已有输出设备路径保持原样。业务停止和重启由统一部署流程执行。在板端源码目录运行：

```text
patch --dry-run --batch --forward -p1 -i /补丁目录/ascend-audio-output.patch
patch --batch --forward -p1 -i /补丁目录/ascend-audio-output.patch
gcc -shared -fPIC -Wall -Wextra -Werror -I/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/include -I/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/include/acl/dvpp /补丁目录/ascend_audio_output.c -L/usr/local/Ascend/ascend-toolkit/latest/aarch64-linux/lib64 -lacl_audio_mpi -lacl_dvpp_mpi -o libguardian_audio.so
```

将 `ascend_audio_output.py` 放入相同源码目录。沿用业务现有 CANN `LD_LIBRARY_PATH`。编译文件属于本机产物，不进入 Git。回滚恢复原始语音文件，移走新增 Python 模块和 `.so` 后统一重启。

## 验证证据与边界

2026-09-08 板端原生编译通过 `-Wall -Wextra -Werror`。独立静音探针 SYS init、AO open、AO send 均返回 0。新 Python 播放线程实机连续发送约 1 秒、51 帧低幅度 660 Hz 提示音，无发送错误。以上是驱动接受数据的证据；音响实际可听、手机到音响通话仍需现场和端到端确认。测试没有改 USB 输入、重启板端业务或调用 SYS exit。

参考：[香橙派官方外设示例](https://www.hiascend.com/developer/techArticles/20240307-1)、[CANN 7 SYS 初始化约束](https://www.hiascend.com/document/detail/zh/canncommercial/700/inferapplicationdev/aclcppdevg/aclcppdevg_03_0306.html)。
