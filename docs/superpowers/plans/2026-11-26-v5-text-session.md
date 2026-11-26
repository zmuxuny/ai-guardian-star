# v5隔离文字闭环实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans，逐项实施并记录实际验证，不自动部署或合并。

**Goal:** 实现已授权的v5文字闭环，接收提醒、展示固定问候、用现有1.5B策略理解文字、持久化并回传正式载荷，覆盖故障和恢复。

**Architecture:** 新建隔离协议/事务存储、问答状态机、回环HTTP与命令行入口。复用本地SQLite连接及路径校验，分类复用V3和SemanticIntentClient；现有DeliveryStore是person/model/mode监护反馈协议，不能把v5结果当反馈写入，故使用专用数据库。提供模拟个性化发送/接收端验证HTTP、乱序和重复，不实现对方作息规则或报警决策。

**Tech Stack:** Python标准库、SQLite、现有Qwen2.5-1.5B语义JSON客户端，无新增依赖。

**Spec:** docs/personalization-message-format-v5.md；用户已批准先隔离文字闭环、异常场景，再双方板端联调。

## Global Constraints

- 文档v5，wire schema_version="2"，正式response=ok/needs_help/unclear/no_response；error独立。
- 单设备单老人，回环HTTP；不访问生产DB/状态，不修改报警、阈值、语音和App。
- 固定问候为本轮默认，generation不存在阻塞；分类5秒、最多2次问候、每次20秒、整轮90秒，迟到窗口300秒。
- 分类复用冻结V3，已知有限否定边界及两条安好弃权保留；协议通过不能解释为模型理解或生产验收通过。
- 接收/名额原子保存，结果/版本/outbox同事务；原载荷补发；重启可能启动者interrupted，不重复问候。
- 结果5/15/30后60秒、提醒5/15/30后30秒补发；24小时版本期限及事件expires+24h6m35s截止同时约束；记录至少7天且有待处理内容不清除。
- 字段/设备/版本/枚举校验、时区语义去重、回执校验、求助事实不可被后续状态清除。
- 先本地验证、独立PR到zy；不部署生产、不自动合并、不代发Issue评论。

## Review Focus

- 求助与总超时竞争：先持久化超时仍允许时限内已收到的求助升版本；已保存求助不降级。
- 接收回执丢失：结果可先到已登记事件；迟到提醒回执不能倒退结果状态。
- 两个线程/进程抢名额及版本：SQLite BEGIN IMMEDIATE、唯一键、持久化后回执。
- 故障/空输入与老人无回答区分；输入收取时刻和分类完成时刻区分。
- 重启、截止到达、低版本求助和错回执：保持原版本/载荷，保留人工处理记录。

## Tasks

- [x] 1. 写失败测试：载荷校验、去重/名额、结果乱序/求助粘滞、outbox/期限/重启；实现 src/personalization_v5.py 与 test_personalization_v5.py，运行并提交。
- [x] 2. 写失败测试：2次问候/20秒等待/90秒总时限、5秒分类、迟到回答/恢复；实现 src/personalization_v5_session.py 与 test_personalization_v5_session.py；不改变V3，运行并提交。
- [x] 3. 写真实回环HTTP测试：两个入口、3秒发送、错误回执、忙/错误码、重复/断连补发；实现 tools/personalization_v5_text.py 与 test_personalization_v5_http.py，提供交互文字及合成演示入口。
- [ ] 4. 对照v5的18项逐项验收，记录模拟/真实模型/设备边界；独立审查、相关回归与CI，更新TASKS/STATUS，push任务分支并提PR到zy。

工作状态工具本会话未暴露，进度临时记录于忽略的.tmp/v5-text-session-20261126/work-state.json；本文件是可审阅实施计划。
