# 板端连续运行与重启复验记录（2026-11-19）

基线：zy@dc74e78，生产代码未修改。用户授权继续板端验收，并先后确认可以配合和已坐好；控制链路异常后已明确告知无需继续保持坐姿。

## 五分钟off连续采样

14:01:22至14:06:21（北京时间），原工具baseline-resources后台独立执行300秒，实际首尾间隔299.462秒。293个样本，读取错误0；摄像头始终在线，帧数2005→4245且各样本持续增加；fps最小6.9、最大8.0、均值7.488。采样前后实际MainPID均10712，NRestarts为0。

RSS从559.43MiB增至612.31MiB，区间最大613.17MiB；线程16–18。没有取得温度传感器值。该记录支持五分钟服务/画面连续运行检查，不证明数小时稳定、无内存泄漏或满足尚未定义的资源SLA；内存增量52.88MiB需另做较长观察和归因。

私有原始数据和摘要已取回.tmp/board-stability-20261119/off-resources.json与off-resource-summary.json。未把formal step6标为完成。

## 静默影子与重启前置检查

新独立会话care-restart-20261119使用FastDemo 2/3/5秒、shadow、sync=false，不启用演示语音。现场确认后Mark seated绑定真实P2；19个采样无读取错误、live outbox为0，P2已达到L0一次/L1两次，但末样本为TARGET_LOST/PAUSED、recognized_roles为空。

随后只安排在同一人员真实可见且正计时、次数达到上限时才调用原restart_case的辅助脚本，不修改原判定。控制通道中断，尚未取得restart-short.json；不将短停记为通过。长停测试没有下发，不推进完整第2步及后续门禁。

## 控制链路与收尾

本机直连、代理及云端中转均曾出现握手超时或关闭；云端frps保持active，6022端口监听，部分探测可读到开发板SSH响应。近15分钟穿透日志出现48条timeout、16条client exit相关记录，不能仅凭这些计数断定具体根因。

云端/root/guardian-frp-recovery-20261119保存服务单元、重启前状态及私有日志后，短重启frps，实际is-active为active；未修改其配置或wenxin业务服务。此后一次中转重新读到板端MainPID14162、active/running，未取得短停报告。本会话RecoverOff返回PASS。14:22:41最终Probe PASS：service active、care off、无关怀配置、camera=true/fps7.4，31项指纹通过；实际进程MainPID16486。之后确认没有本轮restart-probe.py残留进程，也没有restart-short.json或preflight-short.json；未取得短停执行结果，不倒填报告。

当前结论：五分钟连续画面/服务检查通过；内存趋势待查；短停/长停验收未完成。不能用30分钟保护定时器推测off恢复成功。

最小证据已取回.tmp/board-stability-20261119/evidence.tar.gz，含完整资源采样、摘要、19条匿名现场采样、最终Probe、恢复off结果和演示参数，不含私有token/身份配置/数据库/麦克风音频。下一步先稳定穿透连接并观察内存趋势，再重新约定真人重启验收。
