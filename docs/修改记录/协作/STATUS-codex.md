# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

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

## 2026-11-19 · codex · T-20261118-07 · 已部署并实测自动语音，已恢复off

> 分支：codex/zy-care-audio-integration-20261118；来源zy@2131ee2，功能d4a1a9f。
> 用户授权继续部署，并现场确认自动语音“听到了，正常”。

- 部署：核对原28项指纹后，备份全部基线代码、私有服务/环境及1份SQLite快照；原3.9.2编译通过，只安装入口、care_audio.py及两段PCM语音。实际入口独立增强保留。
- 真实验证：AudioDemo独立shadow、sync=false、2/3/5秒；登记P2同轮L0一次/L1两次，24采样无错误、live outbox全0，用户听音正常；没有用手动重播代替。
- 收尾：13:30:43 Probe PASS，service active、care off、无关怀配置、camera=true/fps7.5，31项指纹全部通过；临时阈值/音频覆盖已撤销。
- 影响：deploy/board/care-validation-baseline.json、语音交付说明及本协作记录。生产备份/root/guardian-care-staging/care-audio-deploy-20261119/backup；本地私有证据.tmp/care-audio-deploy-20261119/evidence.tar.gz，不提交语音/数据库/环境。
- 过程：首轮包路径预检在停服前退出，修正payload前缀后完成；恢复时SSH断连，随后核对实际恢复记录和进程并复验通过。
- 未验：真实对讲抢占、完整长时间验收、App回执/公网页面。下一步按需继续这些项目，当前保持off；未改主工作区或其他成员分支。
