# 本地反馈与个人常态库实施计划

**Goal:** 在 zy 实现可离线使用、可迁移、严格作用域隔离的 SQLite 存储。

**Architecture:** src/local_care_store.py 暴露绑定人物/模型的存储实例；src/local_care_migrations.py 管理专用数据库与事务迁移；src/migrations/local_care/*.sql 提供可检查脚本；工具提供备份迁移入口。

**Spec:** ../specs/2026-11-16-local-care-storage.md

用户已确认默认规则并要求无需另行确认设计，直接在当前 zy 实现。基线已备份。work_state 工具未出现在可用目录，不使用其他内置待办工具替代。

## 执行顺序

1. 写 test_local_care_store.py 业务与迁移断言，观察缺少模块时的预期失败。
2. 实现事务迁移、SQL 文件与作用域绑定 API：submit_feedback/get_feedback/list_feedback/count_feedback/revoke_feedback/restore_feedback/feedback_audit、put_sample/get_sample/list_samples。
3. 验证去重并发、更新/撤销/恢复审计、跨人物版本、分类、重启、禁网，以及审计和迁移失败回滚。实现 tools/migrate_local_care.py 备份迁移入口并验证备份保持旧结构与数据。
4. 独立代码审查，执行专项与项目全套回归，记录基线既有失败；尝试 OpenWolf 扫描；更新自己的协作记录；仅暂存相关文件、提交、fetch 并只推送 zy。

## 重点复查

同键撤销后重试不复活；时间窗用事件发生时间；审计和当前值不能部分提交；SQL 外键和所有自动主键索引包含双维度；迁移脚本不能隐式提交或改写旧行；未来版本不能自动降级；无任何云数据库依赖。

## 验证结果（2026-11-16）

- 专项 unittest 26 项通过；包含并发反馈 24 次仍一行、禁用 socket 后重启/读写/撤销/恢复、默认隐藏撤销记录、审计故障事务回滚、迁移失败 DDL 与版本号回滚、WAL 中已提交数据完整备份。
- 独立审查指出的迁移并发及结构校验问题已复现并修复：先 BEGIN IMMEDIATE，再识别版本和结构；持保留写锁时通过独立读连接备份；检查必需索引、所有索引双维度及复合审计外键。
- 独立复核：50 个新库各 8 线程并发初始化，0 异常；10 个 v1 库各 8 线程并发升级，每库只一次实际升级且备份完整。无待修复审查项。
- 全套回归 206 项，1 项既有失败、18 项环境跳过。失败项 `test_cloud_json_contract_fields_are_preserved_in_release_obfuscation` 缺少 hint/photoCount/recognitionStatus 混淆保留；在此前干净 zy 快照已复现，本次未改 entry 或该测试。
- CLI 的 v1 建库、升级与备份、降级失败退出码通过；py_compile 通过。
- OpenWolf 扫描已尝试，命令不可用。没有设备部署或真实断电测试。
