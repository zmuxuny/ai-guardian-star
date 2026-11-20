# 板端个人常态与影子对比 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 完成已确认的 Issue23 优先级②板端部分。
**Architecture:** 纯Python特征提取与静态匹配；schema5增量表和事务反馈派生；有界后台采集，不改告警判定。真实录像入口生成ID后接入shadow采集，模拟记录单独标识。
**Tech Stack:** Python3.9+、SQLite、unittest、现有FastAPI鉴权。
**Spec:** docs/superpowers/specs/2026-11-20-personal-baseline-design.md（用户2026-11-20确认）

## Global Constraints

- 板端范围；App/云端继续#25；仅本地提交、不部署、不启用live。
- 特征/样本/直方图不出板，未知保护证据不放行；首版仅静态建议。
- 保留无关修改；独立worktree；不使用git add -A。
- Python3.9与平铺导入兼容；事务迁移/备份，无覆盖式降级。

## Review Focus

- 录像失败或care失败时原告警仍执行，不能产生第二个可反馈事件ID。
- 反馈先到、撤销后补特征不能复活样本；审计故障整体回滚。
- 删除与在途队列竞态，删除后不得重新写入。
- 长期直方图、队列、报告必须有界；跨模式/摄像头不混合。
- 缺测、布尔假值、非有限特征和重复事件不得虚增影子收益。

### Task 1: 纯特征与静态匹配

Files: src/posture_features.py、test_personal_baseline.py。
Interfaces: extract_posture(box,kpts,frame_shape,region_id,at) -> dict；eligible_label(payload,revoked) -> str|None；evaluate(feature,normal,risk,guards) -> str。
- [x] 先写测试：尺度归一化、0.4阈值、截断/NaN拒绝、原因白名单、3个不同正常事件、正样本/未知保护、匹配边界。
- [x] 运行 python -m unittest test_personal_baseline.FeatureTests -v，确认缺模块失败。
- [x] 实现固定posture_v1与无网络依赖纯函数，保持原跌倒函数不变。
- [x] 同命令通过后，选择性提交本任务。

### Task 2: 事务存储、直方图与生命周期

Files: src/personal_baseline_store.py、src/migrations/local_care/005_personal_baseline.sql、src/local_care_migrations.py、src/care_delivery_store.py、src/weekly_store.py、test_personal_baseline.py。
Interfaces: PersonalBaselineStore(WeeklyStore).capture_event(mode,event_id,feature,camera_revision)、samples(mode,camera_revision)、observe_histogram(...)、personal_report(...)；DeliveryStore事务内派生反馈hook。
- [x] 先写失败测试：v4→v5无损/备份/迁移失败回滚、三态与撤销恢复、先反馈后特征、错域拒绝、事务故障、直方图固定计数、TTL与删除、断网重启。
- [x] 运行 StoreTests 确认失败，再实现增量schema和事务hook、直方图/报告、生命周期清理。
- [x] 运行 FeatureTests+StoreTests 与原存储/周报专项，通过后选择性提交。

### Task 3: 有界采集与真实事件接线

Files: src/personal_baseline.py、src/care_runtime.py、src/care_api.py、src/ascend_board_server.py、src/ascend_main_other.py、test_personal_baseline.py。
Interfaces: PersonalBaselineWorker.submit/flush/close；RuntimeConfig.personal_baseline_enabled=False、camera_revision=None；CareRuntime.observe_recorded_event(kind,alert,record)、personal_report(person)。
- [x] 先写失败集成测试：实际HistoryStore/EventClipCache原ID反馈一致；shadow不反向触发录像；off零新副作用；原告警不变；队列满/存储异常隔离；删除清队列；节流与关停flush。
- [x] 实现真实入口先完成现有录像触发，再用返回的原ID只读通知runtime；已存在live ref仍复用。新增输入仅限内部frame_shape。
- [x] 采集队列最多32项，后台逐项持久化；每秒至多一次无告警直方图提交，报告仅版本/计数；缺失原ID不猜测。
- [x] 增加既有鉴权下聚合报告端点，测试401/404/禁用与不泄漏特征。
- [x] 运行新集成测试及原delivery/runtime/shadow/隐私/录像回归，通过后选择性提交。

### Task 4: 回归、独立审核与交付记录

Files: docs/personal-baseline-runbook.md、协作TASKS/STATUS及本计划。
- [x] 使用独立测试环境补齐fastapi/httpx，复验受影响专项；不把依赖缺失当代码通过。
- [x] Python3.9 ast语法与平铺import检查；核对新增文件迁移打包入口。
- [x] fresh reviewer审核全分支；重要问题按失败测试→修复→回归完成。
- [x] 写运行开关、相机换位、报告解释、隐私删除/保留、schema5回退与实际未验项。
- [x] 更新自己的协作文档，记录精确SHA与测试结果，保持本地WIP不推送。

## 执行记录

用户已明确“确认设计，继续实现”，本计划在同一会话直接执行，不再增加确认轮次。
work_state工具未暴露，暂以本计划的执行记录保存进度，待工具可用再同步。

- Task1完成：d0e522a；5项特征RED→GREEN。
- Task2完成：5da0f37；新存储及原存储/周报52项通过。
- Task3完成（32c35fa/f640bce）：真实HistoryStore/EventClipCache影子原ID贯穿，live引用和outbox隔离、后台队列/认证测试通过；Task4回归和审核继续。
- Ruling：在服务入口传实际frame_shape，保持检测器源文件不变；入口已持有同一帧，能避免覆盖设备上的检测器独立增强，代价是调用方缺少shape时特征不可用（保守跳过）。
- Ruling：关闭采集后既有事件反馈仍刷新已存派生资格，避免再开启时撤销记录复活；只关闭采集不屏蔽撤销事务。
- 独立审查：3项重要问题（后台写锁延迟、无人TTL、trusted带原因丢正样本）和2项删除/关闭边界均补失败用例后修复。
- Ruling：检测和tick不等待附加存储锁，争用时跳过当前关怀附加帧并记错误计数，原录像/告警继续；代价是极慢存储时关怀状态更新可能推迟，不能当作无损采集。
- 删除同步清除该人物排队快照；线程处理完清除私有局部变量。close返回排空结果并允许重试，服务明确记录未排空。
- 修复后组合回归223项运行，222通过/1项Windows不适用的POSIX停机测试跳过；另追加服务关停失败提示用例已RED→GREEN。最终源码变更后的相关专项复核继续。

- Task4完成：独立审查重要项已修复；最终36项新专项通过，最后入口86项运行85通过/1跳过；69文件兼容性检查通过。证据与本地交付边界见docs/personal-baseline-evidence-2026-11-20.md。
