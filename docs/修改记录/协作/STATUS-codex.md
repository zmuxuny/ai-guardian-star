# Codex 状态

> 由 Codex 维护；DeepSeek 不代写。
> 只保留最近 3 条，最新在上；更早条目移到 `archive/YYYY-MM/`。
> 格式见 `TEMPLATE.md`。

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

## 2026-11-18 · codex · T-20261118-07 · 已合并交付，部署留待明日

> 目标：origin/zy；功能提交d4a1a9f，合并提交f884fda；来源为已验证的语音/演示代码3dd0ff1及其演示档依赖。
> 用户明确：今天只交付合并zy，其他明天继续；不执行板端部署，不改主工作区未提交文件。

- 范围：快速演示2秒静止确认与2/3/5秒提醒、多人员测试选择、关怀语音适配及对讲优先，配套测试和说明；不纳入care_demo_web.py及网页原型文档。
- 整合：独立交付分支基于最新origin/zy的0ca3f38，选择性引入相关文件，再创建合并提交；没有合入main或其他成员分支。
- 验证：交付的运行代码、工具和测试与此前已验证源逐文件一致；57项专项、36项回归、原板隔离7项和真实听音结果沿用，不重复执行未变化检查。合并无冲突。
- 回退点：backup/zy-before-care-audio-20261118@0ca3f38。源WIP工作区和私有原件/语音包保留；原主工作区zy@df6d71c及其未提交改动保持原状。
- 部署：4文件最小候选包已备，保留实际原板入口增强；真实自动关怀联动仍待明日安装后验证。当前生产主入口未替换、关怀off；本轮交付阶段没有SSH连接开发板或重启服务。
