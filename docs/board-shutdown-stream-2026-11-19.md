# 视频长连接关停修复及实机验证（2026-11-19）

## 问题与范围

缓存迟到帧死锁已由65c14dd修复，但随后真实off停机仍32.21秒，Result=timeout。主线程等待在ep_poll，SIGINT既未阻塞也未忽略，并存在3个5000端口连接。

板端原Uvicorn为0.39.0。其实际源码和[同版本官方源码](https://raw.githubusercontent.com/Kludex/uvicorn/0.39.0/uvicorn/server.py)表明：先等待现有HTTP连接/任务结束，再调用lifespan shutdown；原入口没有配置连接排空超时。无限视频流可一直占住连接，使硬件和录像清理尚未开始就达到systemd的30秒停服预算。

## 最小修复与复现

仅在原uvicorn.run增加timeout_graceful_shutdown=5。此上限适用于重启时所有未完成的ASGI请求/任务，包括下载；超过上限会取消它们，然后继续lifespan清理。它不限制lifespan内部清理耗时，也不证明任意异常驱动都能及时退出。

新增tests/test_server_shutdown.py，读取实际入口的运行选项，以真实FastAPI/Uvicorn子进程保持HTTP流，发送SIGINT后要求正常退出并产生lifespan清理标记。测试不导入硬件入口、不打开摄像头/NPU。

原板Python3.9.2、Uvicorn0.39.0：原实际入口RED，在8秒后仍无法退出；候选GREEN，1项测试6.73秒完成、正常退出、清理标记存在。候选整文件在原解释器编译通过。独立审查无阻断项；Windows不具备该POSIX/ASGI环境时明确跳过，不把跳过计作上板通过。

## 交付和实际安装

功能cc55ca5，合并7877164，先交付zy再部署。候选从实际板端入口bb730bfd6b2a968fdaf6844d951a3b66c61e454eeae9ae6420742b3167f8da44作唯一运行参数替换，保留实际入口全部独立增强。安装后2ec73e2aa5a9d0c9dbc467a5b597bf9444e4631169ed25bbb77ffd49fc663587。

原件、实际基线、服务单元和进程环境备份于/root/guardian-care-staging/server-shutdown-20261119/backup；本地回退backup/zy-before-stream-shutdown-20261119@8075691。只安装ascend_board_server.py，其他30项实际文件不变。没有修改服务预算、SDK、模型、音频库、数据库或系统依赖。

## 实机持流停机验收

部署原实例停止仍耗30.28秒，属于改前进程，不用它评价新参数。新入口启动并出帧后，独立控制器实际连接/video_feed，读取一个multipart边界字节证明流已开始，并保持该连接直到业务进程退出；不保存图像。

新进程停止12.275679秒，Result=success、ExecMainStatus=0、MainPID=0、ControlGroup为空，未以systemd超时强杀结束。随后启动服务，15:08:03（北京时间）最终Probe PASS：care off、无关怀配置、camera=true/fps7.7，31项实际指纹全部通过。

这是当前off且持有真实视频流场景的完整服务退出/恢复证据。不能替代任意满载录像、异常SDK条件或整板断电验收，也没有把真人短停/长停计时门禁改为通过。

## 证据与下一步

私有证据.tmp/server-shutdown-20261119/evidence.tar.gz含RED/GREEN日志、候选结果、备份/安装摘要、真实停机结果和最终Probe，不含token、私有配置、数据库或图像。实际安装字节已更新到care-validation-baseline.json；后续验证工具应使用更新后的包，不能沿用旧指纹包。

关怀继续off。本次HTTP退出阻塞已复现、修复并在上述实机场景通过；真人短停/长停计时、完整第2步和更长运行验收保持原待办。连接仍需按实际可用的直连/本地代理路径选择，不把本次代码修复宣称为穿透网络问题已解决。
