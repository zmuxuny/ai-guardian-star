# 关怀链路接通核对与本机集成结果

基线2499d1d。验证边界：本机、模拟检测帧、虚拟时间、进程内 API、模拟 MQTT 接收确认、真实 SQLite/状态机/录像缓存，编码器为明确的假后端。未启动真实服务或连接设备、Broker、云端。

## 三项核对：修改前 → 交付代码

### 1.1 检测入口调用状态机：未接通 → 已接通（显式配置启用）

真实调用点 `src/ascend_board_server.py:1103`：inference_loop 在原 AlertEpisodeTracker.update 后调用 dispatch_care_detection；默认无配置时走 off，保持旧流程。启用后沿 `dispatch_care_detection:77` → `CareRuntime.process_frame:89` → `on_detection:159` → `_step:113` → `CareMachine.handle`。

返回快照写入 care_sessions；播报先记录，再在 live 时事务入 care_outbox；event_refs 被 trigger_history_event:88 使用，不能把返回值丢弃。未推理/缺帧的分支调用 poll_care_without_observation → tick → handle(TIMEOUT)，不会用原始空帧伪造起身。普通检测帧先处理输入，不抢先 tick 播报。

证据：test_care_delivery.production_entry 从真实服务文件提取并执行上述入口函数，调用真实 CareRuntime 与 CareMachine，未改为 stub；observe 使用真实 AlertEpisodeTracker 生成 new_events。15项集成检查包含默认1800秒 L0、重启、长间断、tick和故障。

结论仅是工程调用接通。检测器目前 is_sitting 表示持续静止代理，不证明真正坐姿；真实输入参数的临床/场景语义尚未认证，live准入受运行手册限制。

### 1.2 事件 ID 贯穿反馈链路：未接通 → 板端与本地 API 已接通；真实 App 未接通

`CareRuntime._step` 首次坐下生成 UUID，事件及会话在 DeliveryStore.save_step:57 同事务保存。短重启恢复原 active_event_id；长未知间断旧轮结束，新轮换新 ID，不允许新轮 revision=1 被旧幂等键吞掉。

`record_event:268` 明确以该 ID 调用 HistoryStore.add_event(event_id=...) 及 EventClipCache.trigger(event_id=...)；录像关联使用原 event_id。录像 IO 失败保留已处理状态和 event_refs，记录 recording_errors，不为同一 care 事件降级重生另一个 ID。

`care_api.feedback:39` 取 URL 中的原 ID，拒绝替换 ID/发生时间；`CareRuntime.feedback:225` → DeliveryStore.event_feedback:77 → LocalCareStore._submit_in:144 → feedback + audit + outbox 同事务。反馈时间窗使用保存的原发生时间，重试不移动到提交时间。

`DeliveryStore._enqueue:50` 的 message_id 为 event_id:类型:revision；`CareRuntime.flush:232` 未确认不完成。短重启和断网重试继续使用原消息 ID；跨人物、模型、模式不能回写到其他事件。真实 App 尚未采用新 API/稳定 ID，已交给 Jianyuanxi 的 issue #25：https://github.com/zmuxuny/ai-guardian-star/issues/25 。此项不能写成已做真实 App 到设备的端到端认证。

### 1.3 影子与线上告警隔离：仅离线工具隔离 → 服务入口中已接通并验证隔离

CareRuntime.process_frame/on_detection 调用既有 ShadowRunner、TrackerBaseline 和 region_candidate；结果在独立报告中，历史只保留有界最近记录。mode=shadow 不生成新 care outbox、不触发新 care 录像；sync_enabled 与 shadow 组合直接拒绝。

原服务 publish_fall_alert/publish_sit_alert/publish_stranger_alert 等调用保留在原循环中，不使用影子判断替换。新 MqttCareSender 只接受 live 数据和 care 专用主题，拒绝 shadow；它不调用旧告警主题。功能关闭时不会导入/构造新 care 依赖。

证据：test_shadow_cannot_trigger_recording_or_live_queue 用禁止访问新录像存储的陷阱及录制型发送替身核验；旧录像 trigger 仍能按原逻辑调用。test_mqtt_transport_only_new_topics_and_ack_required 校验主题、QoS1和确认。本次没有向任何真实告警通道发布。

## 五个指定场景：预期与实际

完整机器可读 JSON 由 tools/run_care_delivery.py 导出；每项含 expected、actual、passed 和实际生成的 event_id/message_id/recording_id，未通过会非零退出，并保留失败项。默认30分钟阈值，没有直接设置 phase 或提前制造播报。

1. 重启后恢复：先900秒可信坐姿，停机间断5秒，单调时钟归零重建，再900秒可信坐姿。预期同ID、可信累计1800秒、L0一次、待投递一条；实际全部相符，再重启也不重复L0。
2. 重复反馈：原ID两次提交。预期一行、target_id不变、created_at不变、新payload可读；实际一行且新值正确，跨人物/模型404。
3. 撤销：原ID提交后撤销。预期active=0、revoked=1、审计2行，补传携带撤销新版本；实际相符。只按反馈类型/revision核验，不假设队列最后一项必然为反馈。
4. 断网补传：模拟 ConnectionError，重启，再模拟无ACK与有ACK。预期未确认保留原消息ID、确认后两条完成、pending=0；实际相符。这里是模拟接收确认，不代表远端业务已落库。
5. 多事件同段：两个人分别完整计时，录像缓存于触发时可用；同时L0。预期两个不同事件ID、一个已完成录像索引、两条关联，反馈仍各指向原ID；真实 HistoryStore/EventClipCache 的实际结果相符。FAKE NOT VIDEO 产物不冒充真实MP4。

## 异常定位及处理

- 起初入口、ID回写、重启和outbox缺失：新增受控集成层、认证API、增量v3表与事务消息队列，已修复。
- 长间断后状态机内部reset但外层沿用旧ID：先复现新L0被去重吞掉，再按 uncertainty_expired trace 结束旧事件并换ID，回归通过。
- tick播报遗漏录像：统一调用同一 record_event 函数，1790→1800 tick 回归通过。
- 录像IO异常丢弃整帧结果：隔离为 recording_errors，保留稳定refs/反馈与队列；故障注入通过。录像失败不假装媒体可用，需操作者检查存储/编码状态。
- 安装后重写回退清单可能截断：prepared清单保持不变，模拟第二次写入磁盘故障后仍可回退；验证通过。
- 影子检查不能等同线上认证，静止代理不能等同坐姿识别，真实接收端与App对接未认证：均保留明确准入门槛和责任，不用本机测试替代。

部署、配置、依赖、逐项板端清单与回退命令见 care-delivery-runbook.md。当前板端清单全部待实际操作者验证，不预先勾选。

冻结验证结果：251项测试，无失败，18项设备/MQTT条件跳过。五场景报告全部 passed=true；expected 与 actual逐项一致。安装/回退四项本机演练通过。故障注入用例中的 recording_failed OSError日志为预期；它证明异常定位与原ID保留，不代表真正触发了设备故障。
