# 开发板本地反馈与个人常态库

## 范围与已确认规则

仅使用本机 SQLite 和 Python 标准库；独立数据库，不修改录像历史数据库，不依赖云端、网络或真实设备。用户已确认以下默认规则并要求直接实现：

- 反馈键：人物、模型版本、目标标识、事件发生时间所在的固定 300 秒窗。窗口按 UTC Unix 秒向下取整；重试使用原事件时间，不用提交时间。窗口边界不做模糊合并。
- 同键重提覆盖 payload，保留创建时间；撤销后重提仍保持撤销，必须显式恢复。
- 常态样本分类限定 posture（姿态）、activity（活动）、routine（作息）。

采用独立存储模块，而非扩展录像表，防止混用全局 history user_version 或破坏已有数据；反馈与样本在同库内，但每个存储实例绑定不可变人物/模型作用域。所有业务 SELECT/INSERT/UPDATE 和主键/索引均包含这两个维度。SQLite PRAGMA、建表及结构检查是数据库级操作，不是跨用户数据查询。数据库文件访问者仍可用原生 SQLite 读取内容，本接口不取代操作系统权限控制。

## 表与操作

- feedback：复合主键 (person_id, model_version, target_id, window_start)，JSON 对象 payload，首次 event_at、created_at、updated_at，软撤销标记、撤销时间/原因，revision。UPSERT 不使用 REPLACE，避免删除再插入破坏创建时间或审计关联。
- feedback_audit：复合主键包含上述四字段与 revision；保存 submit/revoke/restore 的完整快照，复合外键指向同一作用域的反馈。审计与当前行同事务提交，审计失败则当前行也回滚。重复撤销/恢复不新增无意义记录；每次提交都可审计。
- baseline_samples：复合主键 (person_id, model_version, sample_id)，合法 category、JSON 对象 payload、采样时间、创建/更新时间。样本 ID 由调用方提供，同一作用域同 ID 重提更新、不增加行；不同作用域允许同 ID。
- 每个查询/统计默认 status=active，反馈另支持显式 revoked/all；审计读取必须指定 status，按当前撤销状态选择反馈，再取其完整审计历史。不存在于当前作用域的写操作抛出 LookupError；查询返回 None/空集合，不探测其他人物/版本是否存在该键。
- 普通提交只替换 payload，首次发生时间、创建时间和撤销元数据不变。updated_at 使用注入时钟的 UTC Unix 秒，并保持不回退；时钟精度相同或回拨时 revision 保证操作顺序。恢复清除当前撤销标记，旧撤销时间/原因可从审计快照追溯。
- 键不允许空白/控制字符；payload 必须是可序列化的有限值 JSON 对象，编码不超过 64 KiB；分类和状态在执行 SQL 前校验。

## 事务与迁移

所有写操作使用 BEGIN IMMEDIATE、COMMIT/ROLLBACK；连接短开短关，busy_timeout=5000，synchronous=FULL，启用外键。保留 SQLite 默认持久回滚日志，不依赖后台同步服务。多个线程/进程通过 SQLite 写锁和唯一约束去重，不采用“先查再无锁插入”。异常向调用方传播，不假装写入成功。

专用数据库用 application_id 标识，PRAGMA user_version 记录结构版本，不建立无作用域的元数据表。拒绝未知数据库、未来版本及结构不完整的已标记数据库。SQL 文件按顺序在一个显式事务里执行，不用隐式提交的 executescript。

001_initial.sql 建立三表、复合唯一约束和作用域索引；002_baseline_source.sql 添加可空 source 字段。后者不更新、删除或重新插入任何旧行，旧字段保持原值，新字段为 NULL。允许先建 v1 再升级，重复执行幂等；失败全部回滚。后续迁移追加编号文件，不修改已发布脚本；采用增量兼容变更，不复用录像库版本号。迁移先取得写锁，再在同一一致状态下识别版本并决定备份。升级既有数据库时自动通过独立读连接使用 SQLite backup API 备份；写锁期间尚无数据改动，其他写者被阻止，备份含原有已提交数据。禁止直接复制可能有未提交日志的数据库文件。

## 验收

反馈重复提交只有一行、创建时间不变、payload/更新时间更新；撤销默认不可见、显式撤销查询可见、重提不复活、显式恢复生效；审计保留各次变更；样本分类筛选、非法分类拒绝；人物/版本四组合相同业务键互不干扰；重启持久化；并发重复提交一行；写入或迁移中途失败回滚；v1 升 v2 数据保持；禁用 socket 下全部核心操作可用。

不部署到开发板，不自动采集人脸或其他敏感原始素材。样本内容和“正常”判定由调用方负责，分类不等于自动证明样本正常。

## 运行与调用

```powershell
python3.11 -m unittest test_local_care_store -v
python3.11 tools/migrate_local_care.py .tmp/care.db
```

只需 Python 标准库。可用环境若命令名为 python，替换 python3.11 即可。迁移工具可加 `--target-version 1` 验证旧结构；升级时自动在原数据库旁生成唯一的 `.backup.db` 文件，终端报告备份文件名。备份失败则不升级。重复执行不创建多余备份；禁止降级。部署时保留 Python 模块和相邻 SQL 文件的目录结构。

```python
from src.local_care_store import LocalCareStore

store = LocalCareStore('.tmp/care.db', 'person-demo', 'model-v1')
store.submit_feedback('event-demo', 601, {'label': 'false_alarm', 'note': 'demo'})
store.submit_feedback('event-demo', 601, {'label': 'normal'})  # 同键只更新
store.revoke_feedback('event-demo', 601, reason='changed mind')
assert store.get_feedback('event-demo', 601) is None
revoked = store.get_feedback('event-demo', 601, status='revoked')
history = store.feedback_audit('event-demo', 601, status='all')
store.restore_feedback('event-demo', 601)  # 显式恢复
store.put_sample('sample-demo', 'posture', {'duration_seconds': 10},
                 sampled_at=601, source='manual-confirmation')
samples = store.list_samples(category='posture')
```

示例路径仅供离线开发；正式板端由调用方传入受设备文件权限保护的私有持久目录，不放到临时目录。DB、备份和日志不进入 Git。反馈的反馈目标需稳定；“同目标在相邻时间窗”有意视为不同记录，调用方重试必须保留原发生时间。

断网验收通过屏蔽 socket 构造与网络连接函数执行提交、样本写入、重开、撤销、显式查询和恢复；持久性使用文件数据库验证，不用仅内存数据库代替。数据库断电恢复依赖本地文件系统和 SQLite 持久日志；本次未做真实设备断电破坏试验。
