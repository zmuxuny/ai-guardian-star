# 区域周报本机验收记录

日期：2026-11-16。基线：zy / 8c1ab28。仅本机、虚拟时钟和构造输入，无真实传感器、音频、MaaS、线上告警或设备部署。

## 结果

`python tools/run_weekly_scenarios.py --output .tmp/weekly-results.json`：14项专项测试通过；JSON含各存储场景 expected/actual 和完整聚合输出。连续两次独立临时库运行，JSON SHA-256 同为 `f1c9257c47091939c4f3f51ccf6f1671edf91521ba9c81c0d6a78cc6e4a3b9d0`。输出不含数据库路径、随机事件ID或生成时间，因此可直接比对。

`python -m unittest discover -v`：265项，无失败；247项通过，18项设备/MQTT条件测试跳过。本机使用 Python3.11.15、SQLite3.53.1；统计/存储无新增第三方依赖，API测试使用 requirements-care-validation.txt。`git diff --check` 通过。OpenWolf扫描已尝试，但操作机没有 openwolf 命令，未完成索引刷新。

| 场景 | 预期 | 实际及测试位置 |
| --- | --- | --- |
| 跨周 | 周一零点划新周；跨界观测按重叠时长分配；事件只归开始周 | 新事件night计1，周日前一秒事件归上周evening；跨界有效观测新周60秒，符合；test_cross_week_duplicate_and_threshold |
| 重复事件 | 同一稳定ID重复5次仍计1 | 1，符合；test_duplicate_events |
| 反馈撤销 | 明确确认由1变0，原感知事件仍为1 | 符合；test_feedback_revoke |
| 时区 | 同一UTC周日17点在UTC属于前周、UTC+8属于本周 | 本周分别0和1，符合；test_timezone |
| 过期清理 | 短保留期清源事件/反馈/观测，统计立即为空，不动其他人 | 符合；test_expiry_and_personal_delete |
| 无观测与零事件 | 无观测标no_observations、率和趋势null；有有效观测无事件的率为0 | 符合；test_missing_and_observed_zero_and_trend |
| 最小样本与趋势 | 任一周不足阈值趋势null，两周达标按有效小时比较 | 阈值2不输出；阈值1输出up、差30/小时、相对差1；test_trend_rate_threshold_and_boundary |
| 质量与重叠 | 重复/重叠不加时长；质量取重叠有效源较低分后按时长加权 | 60秒、1样本、质量0.4、有效比例0.5；test_union_quality_and_invalid_observations |
| 隔离/删除 | 同人物不同版本、同版本不同人物、live/shadow不交叉；删除后不留派生结果 | 符合；test_scope_version_mode_and_delete_derived、test_cleanup_is_mode_scoped_and_preserves_active_event |
| Runtime | 实际on_detection/tick入库，TTL30秒、重启不补算、删除后不重建、恢复后采集 | 符合；test_runtime_ttl_restart_delete_resume_and_automatic_cleanup |
| API | Bearer保护、scope隔离、只有结构化字段、策略与删除/恢复可执行 | 符合；test_authenticated_structured_api |
| 迁移 | v3到v4新增表，事件历史字节值不改写，升级前备份可打开 | 符合；test_v3_migration_preserves_history_and_backup |

## 接通与审查

- 检测入口沿原 `dispatch_care_detection → CareRuntime.on_detection → _weekly_observe → WeeklyStore.coverage` 保存观测；`tick → _weekly_observe → maintain` 为无检测帧时的观测封口和维护入口。
- `create_care_router` 的 weekly GET 调用 `CareRuntime.weekly → WeeklyStore.weekly → aggregate`；读取相同作用域 care_events 与未撤销 feedback，不另造事件ID，不接文字生成。
- `WeeklyStore.maintain` 事务清原始源及依赖，当前活动事件保护；`erase_person → erase` 清两个模式和个人库后清影子缓存；每次查询重新计算，无派生持久缓存残留。
- 按 requesting-code-review 流程完成独立只读审查及修复复核。修复了原区间算法的平方级扫描、统计占用检测锁、删除后影子缓存残留；复核未发现剩余严重问题。审查使用1000组随机重叠/无效/未知质量区间对独立参考算法比对，一致。本机21600条观测单次metrics约0.027秒；此值不代表板端吞吐。

仍待板端验收：设备时间、实际区域映射、持续运行写入开销、断网查询、现场保留清理和部署/回退。按 weekly-report-contract.md 的勾选清单执行；本次不将本机测试作为板端通过证据。无需App侧改动，未新建App协作issue。
