# v5隔离文字闭环：用法与验证记录

本轮完成本地模型侧v5文字试验入口，以及**模拟个性化模块**的提醒发送/结果接收端。使用两个真实回环HTTP服务、专用SQLite数据库和现有V3分类器适配；没有修改生产服务、检测、报警、反馈、基线、语音或App。基于zy@5373e6e，代码提交13fb438/c54e0b6/1eeb49d/6352210/717f7ff，交付为 [PR #33](https://github.com/zmuxuny/ai-guardian-star/pull/33)，不自动合并。

协议遵循项目已采用的 [消息格式v5](../personalization-message-format-v5.md)，wire `schema_version` 为字符串`"2"`。实验`okay`经适配才成为正式`ok`；`no_response`与流程`error`独立，不靠模型猜测设备故障。2026-11-26读取Issue #28/#29及feature/jyx-home分工文档时，两Issue没有新评论；这不证明对方已采用本次模拟端实现。端口、参数和对方真实模块仍需双方确认。

## 本轮实际实现

- `src/personalization_v5.py`：定义字段校验与时区规范化、绑定设备/角色、原子接收及唯一主动问答名额、结果历史/版本、持久化迟到窗口、求助标记和一次待处置记录、原载荷outbox及回执校验。SQLite使用现有耐久连接辅助，数据库独立且拒绝接管未知库，不把v5消息写入现有care反馈库。
- `src/personalization_v5_session.py`：默认固定问候、两次共用问候预算、20秒等待、90秒整轮单调时钟、5秒分类、求助优先、窗口内更新与重启恢复。非协作分类函数也被5秒外层等待限制，旧任务未结束前不叠加工作线程。校时回退不能延长进程内迟到窗口；恢复时检测到时间不可靠则要求独立求助/人工路径。
- `tools/personalization_v5_text.py`：`POST /personalization/v2/reminders`、`POST /personalization/v2/results`，本机文字输入辅助端点`POST /text/v1/answers`，操作系统级单runner锁，后台补发与问答时钟分开执行。问候打印并flush完成后才确认展示；HTTP回执仅代表落库，不代表老人回答或App收到。
- 传输与补发：HTTP发送预算3秒；提醒5/15/30后30秒、结果5/15/30后60秒退避；版本24小时及事件补发截止同时约束。保留所有历史、未确认和失败记录，本版没有自动删除记录，因此满足至少7天保留，但尚未实现长期容量管理。

默认固定问候直接可用，**本轮没有模型生成问候功能**，也没有生成超时试验。分类可指定现有回环模型服务，用SemanticIntentClient读完整SSE；本轮集成测试用SSE测试替身验证适配，并非新一次真实权重推理。模型选择与性能依据仍是此前PR #31/#32的研究证据。

## 一条命令复现

下面在PowerShell 7中整块原样执行；每次使用新目录，避免覆盖旧数据库和结果。只产生合成数据，不启动开发板或生产服务。

```powershell
Set-Location 'C:\Users\Yang\.codex\worktrees\board-llm-retest-20261126\zhihuixing'
$env:PYTHONUTF8 = '1'
$demoDir = Join-Path (Get-Location) ('.tmp\v5-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
python -m tools.personalization_v5_text demo --workdir "$demoDir"
```

预期依次看到三个合成事件：明确安好回`ok`、当前起不来回`needs_help`、含糊协助表达在两次问候后回`unclear`。终端输出完整结果，并在`$demoDir\result.json`保存；两个本地数据库留在同目录，不提交仓库。若命令报错或模式不为`text_rules_with_stub`，停止据此判断验收成功，查看实际输出。

已准备好经过核验的隔离模型服务时，可在**另一个新目录**测试HTTP模型适配：

```powershell
$modelDemoDir = Join-Path (Get-Location) ('.tmp\v5-model-demo-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
python -m tools.personalization_v5_text demo --workdir "$modelDemoDir" --model-url 'http://127.0.0.1:18081' --model-id 'qwen25-15b-q4km'
```

这个命令不会安装或启动模型。`text_with_HTTP_model_backend`只说明配置了HTTP后端；必须检查`backend_attempts`、逐条`policy_decisions`中的`model_called`/`source`及模型资产核验，才能认定实际推理。连接失败会走澄清，不应把有合法v5结果当成真实模型通过。首次提示约15秒的旧实测成本仍存在，5秒截止可能触发澄清。

需要持续运行时使用`serve --role model|peer --db ... --device ... --port ... --peer-url ...`；模型侧加`--simulate`明确使用规则与固定unclear替身，省略时使用配置的SemanticIntentClient。`send`先保存模拟事件后发送提醒，`answer`必须显式指定事件ID和文字。各命令参数见`python -m tools.personalization_v5_text -h`及子命令`-h`。服务只绑定127.0.0.1，不提供公网入口。

## 验证证据与18项对照

本地新增40项回归，加原模型相关65项共105项；覆盖真实SQLite事务、线程竞争和回环HTTP，不读取生产数据库。合成三事件演示及两个独立CLI进程闭环均实际执行。证据在 [evidence/v5-text-2026-11-26](evidence/v5-text-2026-11-26/)，仅保存合成结果及复现脚本，不含数据库/锁文件/密钥/真实音视频。

下列编号对应v5第10节。时限与重启边界用注入时钟或重新实例化状态机验证，不能解释为开发板断电实测。

1. 明确安好：`test_okay_maps_to_formal_ok_and_does_not_prompt_twice`；HTTP/CLI演示同时验证字段及事件关联。
2. 当前求助/重复：`test_real_http_text_closed_loop_and_duplicate_help`，结果落库后只登记一次模拟待处置任务，不触发真实报警。
3. 两次含糊：`test_two_unclear_or_mixed_timeouts_share_prompt_budget`。
4. 两次健康静默：`test_healthy_silence_is_no_response_and_first_timeout_then_unclear_is_unclear`。
5. 无回答后含糊：`test_silence_then_answer_does_not_get_third_prompt`。
6. 分类超时/故障：`test_classification_failure_is_unclear_not_input_failure`、`test_classification_exceeding_five_seconds_cannot_confirm_help`及非协作后端实等5秒测试。生成问候使用固定话术，未实现模型生成及其超时测试。
7. 展示/输入故障、抢占和总超时：`test_input_failure_prompt_failure_and_preemption_are_errors`及单调时钟测试；抢占为显式interrupt调用，不是音频设备实测。
8. 到期后的重复/冲突：存储时区去重测试；重启时标记已写但未显示、已显示但未保存结果均回interrupted，不重复问候。
9. 窗口内迟到求助、低版本/乱序/重复：窗口输入时刻测试与`test_lower_version_help_is_sticky_and_task_is_exactly_once`；HTTP到达时间不反推回答时刻。
10. 丢失提醒回执、结果先到：`test_lost_ack_can_arrive_after_result_without_reverting_progress`及先登记事件测试。
11. 首次到达过期与接收后启动过期：`test_expired_before_accept_and_expired_before_start_differ`，启动前过期的prompt_count为0。
12. 求助待发送跨重启、原载荷/版本和截止失败：原子版本outbox测试、版本期限与事件期限测试。
13. 未知提醒类型使用同一通用固定问候；协议版本拒绝由校验/HTTP测试覆盖。本版不根据类型构造事实。
14. 提醒与结果同ID、不同角色各自接收：真实回环闭环测试。
15. 错ID/版本/接口disposition回执：`test_result_ack_must_match_event_revision_and_endpoint_disposition`；不误清待确认队列。
16. JSON顺序/空白、等价时区、额外字段忽略；reason变化和device字段有无变化冲突：存储语义去重测试。
17. 并发仅一个获准、重复优先返回、等待期间输入失效：并发名额测试、HTTP忙测试、输入故障测试。
18. 求助先保存/超时先保存、输入仍在5秒内可升版本、重启截止后保留：状态机竞争及存储事件截止测试。结果与outbox故障注入验证同事务回滚。

独立审查复现了深层JSON回执导致后台补发线程退出，已转为可重试解析失败并加真实HTTP回归。首次超大请求测试在Windows遇到客户端写入与服务关闭竞争，改为声明超限长度且不写入正文，验证服务立即413拒收。

## 尚未验收及后续对接

- 真实1.5B权重与新问答流程的板端联合运行；本轮SSE后端是测试替身，未重新测模型性能或检测服务影响。
- gufeng的真实个性化服务、实际提醒来源、现有care稳定事件ID/模式门禁适配、App和生产处置链路；当前peer只是协议模拟端，待双方确认参数后独立联调。
- 模型生成问候、真实语音/音频抢占、物理断电、拔网线演示、长稳和容量维护。
- 超出迟到窗口或无法关联的求助返回410并明确要求独立求助/人工入口，**该入口尚未实现**，不能宣称支持任意时刻求助。
- V3仍是有限规则：本轮再次确认“我没有说我需要帮助”会被误报为求助；此前两条安好弃权也保留。没有修改冻结策略或用这些样本宣称新理解能力通过，不能据此部署无人值守分类。

下一步先审阅本PR，确认模拟协议双方一致，再开展真实个性化接收端与板端模型联调；分类边界修正另建样本与验证任务。
