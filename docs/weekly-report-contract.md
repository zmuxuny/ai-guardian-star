# 板端区域聚合与周报数据 v1

本接口只提供结构化聚合，不调用云端、不生成文案、不评估风险。云端 MaaS 或固定模板读取同一份 JSON。默认关闭，新配置中显式设置 `weekly_enabled: true` 和 `weekly_regions: ["room", "unknown"]`；`region_id` 必须在声明列表内。沿用 `AI_GUARDIAN_CARE_CONFIG` 配置文件入口，不修改既有告警/影子隔离开关。

## 调用与字段

所有接口复用现有 Bearer 认证，凭据见设备上的私有配置。路径中的 `model_version/person_id` 必须属于本 Runtime；live/shadow 由 Runtime 配置确定，调用者不能通过查询参数越权切换。

- `GET /api/care/{model_version}/{person_id}/weekly?week_start=2026-11-09&offset_minutes=480`：week_start 为周一 ISO 日期，固定时区偏移默认 UTC+08:00，支持 -840..840 分钟、15 分钟整数倍；不支持夏令时。无效参数 422，功能关闭 503。
- `PUT /api/care/{model_version}/{person_id}/weekly-policy`：JSON 必须恰为 `{"retention_days":90,"min_samples":30}`，分别允许 1..3650、1..10080 的整数；持久化保留策略，重启不覆盖。
- `DELETE /api/care/{model_version}/{person_id}/data`：删除该人物、该模型的 SQLite 数据（包含两种模式），返回 `{"status":"erased"}`。
- `POST /api/care/{model_version}/{person_id}/data/resume`：显式恢复采集，返回 `{"status":"resumed"}`。

周报顶层固定字段：`schema_version`(int=1)、`person_id/model_version/mode/week_start`(str)、`offset_minutes/min_samples`(int)、`start_at/end_at/retention_cutoff`(float UTC 秒)、`groups`(array)。半开周范围 [start_at,end_at)，周一零点开始；previous 为前一周。输出不含原始反馈、坐标或文案。

每个已声明粗区域 × 四时段 × 三事件类型输出一行，包括零计数行。未知来源区域折叠至 `unknown`，必要时追加这一粗区域。时段 `night/morning/afternoon/evening` 分别为当地 00–06/06–12/12–18/18–24，类型 `fall/sit/stranger`。分组字段 `region_id/period_id/event_type`；`current/previous` 的字段和类型完全相同：

| 字段 | 类型/口径 |
| --- | --- |
| event_count | int，唯一事件 ID 按开始时刻计一次，跨周持续事件归开始周 |
| human_confirmed_count | int，相关事件最新未撤销反馈 confirmed 严格为 true 或 label=confirmed；撤销不删除原始感知事件 |
| effective_observation_seconds | float，有效观测区间并集，按周/时段切分 |
| sample_count | int，某分钟有效观测并集达到30秒算1个样本，重复帧不增加样本 |
| observation_status | str，no_observations / unusable_observations / observed |
| event_rate_per_hour | float 或 null，事件数/有效观测小时；无有效观测 null，有观测无事件为0，二者都不是风险结论 |
| perception_quality.valid_fraction | float 或 null，有效时长/全部观测并集；完全无观测 null |
| perception_quality.score | float 或 null，对已知质量分数按有效时长加权；重叠取有效源最小分；未知质量不假设为1 |
| perception_quality.score_coverage | float 或 null，有分数有效时长/有效时长 |

`trend_status` 为 no_observations / insufficient_samples / ready；只有两周该分组的 sample_count 都达到阈值才输出 `trend` 对象，否则 null。对象字段 `direction`(up/down/flat)、`rate_delta`(float，每小时事件率差)、`relative_delta`(float 或 null，上一周率为0时 null)。不能把 no_observations 或不足样本解释为改善/安全。感知事件计数与人工确认数量分别提供，不将未确认事件自动当作误报。

## 观测接通及生命周期

`CareRuntime.on_detection` 将稳定人物匹配的检测变成区间来源；可选 `care_region_id` 指定声明的粗区域、`care_quality` 为 0..1，未知质量保留 null。多个候选/明确姿态不可靠标成无效观测。上一次检测最多有效30秒，下一次检测或 tick 将实际间隔写入SQLite；缺失检测停止覆盖。重启不补算停机时长。连续区间合并到最长1小时记录，避免按帧长期积累。外部数据源也可通过 `WeeklyStore.observe` 提交明确 ID 的区间；同ID同内容幂等，不同内容拒绝。

实际检测和tick驱动 `WeeklyStore.maintain`，至多每小时清理一次；无后台服务依赖。设备停止期间不执行，恢复后的首次调用补清；查询始终按当前保留期限裁剪，不必等待清理。UTC 时钟需本机正确配置（2020年之后）；倒退至上次清理前跳过清理。错误向前跳时仍可能过早清理，部署验收必须检查设备时间。默认90天；只清当前人物/模型/模式的过期事件、对应反馈及审计/发件箱、过期观测，保留 checkpoint 当前活动事件。跨截止点观测裁剪，跨期活动事件按其开始时间参与查询，早于截止点不展示。

个人删除在事务中清除该人物/模型的观测、策略、反馈/审计、常态样本、两模式事件/会话/队列。周报每次从源表计算，无缓存，撤销/到期/删除后即时反映。保留仅含人物/模型和删除时刻的最小 tombstone，阻止仍在运行或重启后的 Runtime 重新采集，直至显式 resume。删除等待正在执行的发送完成，并清空后续待发项。

此接口是当前 SQLite 范围的删除，不是全设备/云端擦除；不物理删除共享录像、人脸目录或已发云端副本。共享录像可能关联其他人物，不应从本接口连带删除。API应限设备管理员使用。混合人物的临时影子比较缓存一并清空，后续不再向影子逻辑输入已删除人物；其他人物的SQLite源记录不受影响。

## 本机验证、升级与回退

Python 3.9+ / SQLite 3.24+（原板端3.9.2的适配验证见board-environment-adaptation.md），统计和存储只用标准库。API复用现有 FastAPI；安装本机验证依赖：`python -m pip install -r requirements-care-validation.txt`。一键运行 `python tools/run_weekly_scenarios.py --output .tmp/weekly-results.json`，失败非零退出。输出含 expected/actual 和每个存储场景完整聚合结果；覆盖跨周、重复、反馈撤销、时区、过期及无观测、阈值、质量/重叠、作用域、删除、Runtime/API。全仓回归：`python -m unittest discover -v`。

迁移004为增量新增3张表，历史行不重写；原1/2/3脚本不变。使用 `python tools/migrate_local_care.py <设备私有数据库路径>` 或首次Runtime初始化自动迁移，升级已有库时先生成一致性备份。一起部署两个 weekly 模块和004 SQL，已有 `tools/care_release.py` 的文件清单已包含，部署前停止服务并备份代码/配置/数据库，按原 care-delivery-runbook 操作。

回退目标为引入本功能之前的 zy 提交8c1ab28。旧代码不支持schema4，不能仅切换旧模块继续打开新库。若只停用功能，将 weekly_enabled=false，保留当前代码和数据库；若必须完整回退，先停服务、另行备份当前schema4库（包含升级后新数据），恢复8c1ab28代码及升级前schema3备份，然后启动；该恢复会舍弃运行期间新增数据，需先决定导出保留，禁止悄悄覆盖当前库。复验关怀事件恢复、反馈/撤销、影子隔离、发件箱和认证；周报接口在旧版本不存在。

板端待验（本次只在本机模拟，未连接设备）：

- [ ] 本地时间/固定时区正确，断网仍能查询JSON。
- [ ] 文件及004迁移齐全，升级前备份可打开。
- [ ] 检测/tick产生有效观测，遮挡/丢失不无限累计。
- [ ] 配置的粗区域与实际映射一致，未知值进入unknown。
- [ ] 人物/模型/模式隔离，认证失败不返回数据。
- [ ] 配置短保留期后自动清理源数据，周报同步变化。
- [ ] 个人删除后统计为空且重启不重建，resume后才采集。
- [ ] 演练停用与完整回退，保留回退前数据库副本。
