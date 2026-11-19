# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

## 2026-11-19 · codex · T-20261119-03 · 缓存死锁修复上板，内存阶段观察完成

> 来源zy@75a80a5；功能65c14dd/整合fc442e4已推送并上板。代码和31项指纹实际核验。

- 修复：停止后的迟到画面在普通Lock内二次加锁；真实线程先复现卡住，再最小拆分持锁拒收。原板Python3.9.2相关31项全部通过，独立审查无阻断。
- 发布：只安装guardian_event_cache.py，其他30文件不变；原件/配置状态私有备份board-health-20261119/cache-fix-backup。SDK/模型/数据库不动。
- 内存：同一进程120样本/598.373秒/零错误，摄像头持续正常；RSS约637.0→640.7MiB，后半段略降，无持续单向增长证据，不证明排除长期泄漏。
- 未解：新代码off停机仍32.21秒/Result=timeout，MainPID0且ControlGroup空后已恢复；FRP工作连接超时仍需查，不能把缓存修复等同于全部停机/网络问题解决。
- 用户临时要求听音后取消，未触发语音；14:54:43已实际CLOSED/Probe PASS：off、无配置、camera7.7fps、31指纹通过。
- 影响：缓存模块、新线程回归、实际指纹基线及docs/board-health-cache-stop-2026-11-19.md；证据.tmp/board-health-20261119/evidence-cache-fix.tar.gz私有不提交。
- 下一步：继续验证HTTP长连接与退出等待，T-20261119-04；真人短停/长停和长期验收保持待验。

## 2026-11-19 · codex · T-20261119-02 · 五分钟连续运行完成，重启未完成，已off

> 分支：codex/zy-care-audio-integration-20261118；基线zy@dc74e78，未修改生产代码。
> 用户两次确认可配合；控制链路异常后已明确告知无需继续保持坐姿，长停不再执行。

- 运行：14:01:22–14:06:21，293样本/299.462秒/零读取错误，camera全部在线、帧2005→4245持续增加、fps6.9–8.0，MainPID10712和NRestarts0保持。
- 资源：RSS559.43→612.31MiB（峰值613.17）、线程16–18，无温度值；只完成五分钟冒烟，不证明长期稳定或无泄漏，内存趋势待查。
- 真人：静默FastDemo独立shadow，P2已达L0一次/L1两次；19样本末次TARGET_LOST且无可见角色，outbox全0。之后穿透断连；无short/preflight报告或残留探针进程，短停不报通过，长停未下发。
- 控制恢复：云端备份frps单元/状态/私有日志后仅重启frps（active），未改配置或wenxin；中转重新连板。14:22:41 RecoverOff及Probe PASS：active/off/无配置、camera7.4fps、31指纹通过。
- 影响：docs/board-stability-restart-2026-11-19.md、TASKS、本人STATUS及归档；最小私有证据.tmp/board-stability-20261119/evidence.tar.gz不提交。
- 待续：穿透链路反复中断原因、RSS增长归因、真人短停/长停和完整顺序验收；不推进第2步/第6步门禁。其他端工作保持原待办。

## 2026-11-19 · codex · T-20261119-01 · WebSocket对讲抢占与恢复实测通过

> 分支：codex/zy-care-audio-integration-20261118；板端代码基线zy@7464b04，未改生产代码。
> 用户已现场确认：对讲清楚，后续提醒也恢复了。

- 真实输入：独立AudioDemo识别后L0事件约0.488秒插入“这是对讲测试”，经原/ws/intercom发送114帧/2.28秒；后续同轮两次L1。未录制麦克风。
- 证据：私有传输结果与用户听音确认分开保存；不宣称自动测得物理中断延迟。输出缓冲约180ms边界保留。
- 收尾：13:57:03 Probe PASS；service active、care off/无配置、camera=true/fps7.3、31指纹通过；临时环境撤销、独立care outbox=0。
- 影响：仅语音交付文档、TASKS、本人STATUS及旧记录归档；私有证据.tmp/care-arbitration-20261119/evidence.tar.gz与listen-confirmation.json不提交。
- 未验：UDP实际抢占、完整长时间/顺序验收、App回执与公网页面；原服务退出慢独立待办保留。下一步继续板端剩余验收，当前保持off，无需用户继续配合本轮。
