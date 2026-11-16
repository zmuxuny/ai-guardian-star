# 关怀链路本地集成交付、部署和回退

## 交付边界

本版本只在本机用模拟事件验收，不连接开发板、摄像头、真实 Broker 或云端。默认不设置 `AI_GUARDIAN_CARE_CONFIG`，功能关闭；示例配置 mode=off，sync_enabled=false。原有告警发布路径保留。代码回退基线为 **2499d1d**。

重要输入语义：当前检测器 `_is_long_sit_state` 使用持续静止计时，`is_sitting` 不是经过真实坐姿分类验收的结果。静止站立可能被视为该代理输入。本地“可信 SIT”模拟成功不代表真实坐姿正确；在完成下方静止站立/真实起身验收和输入语义决策前，只能关闭或使用 shadow，不能批准 live 久坐提醒上线。

现有平铺部署使用 [原环境适配说明](board-environment-adaptation.md) 的专用工具；以下src目录安装流程仅适用于符合其基线的目录，不能直接覆盖平铺设备。

## 配置（私有文件，不提交实际配置）

- AI_GUARDIAN_CARE_CONFIG：设备私有 JSON 文件路径；缺省关闭。字段仅限 deploy/care-config.example.json 与 machine 阈值配置，拒绝未知字段。
- mode：off / shadow / live；shadow 与 live 分开保存会话，不相互继承计时与事件。
- db_path：相对私有 JSON 所在目录或本机绝对路径，必须为本地持久 SQLite 文件，不能是内存或 URI。目录需有足够空间，仅运行账户可读写；不要放临时目录或 Git 工作树。
- person_ids：1..32 个稳定人物标识，必须与 known: 后的身份一致，或由上游提供明确的 care_person_id；不会把跟踪框 id 自动当成稳定人物。未知/未登记目标不绑定到其他人的会话。
- model_version：实际部署模型 checkpoint/OM 的版本或校验标识；切换版本必须更换该字段，不能沿用旧计时或反馈。
- region_id：区域标识；未有映射时使用显式 unknown，不猜测位置。
- machine：沿用 Config 默认值（30分钟 L0、5分钟升级/重复、观测30秒失效、不可靠120秒作废、回应10分钟、22:00–07:00静默）；本次五场景没有缩短默认阈值。
- sync_enabled：仅 live 可设 true。仅在显式启用后启动独立 DeliveryWorker，不控制旧告警 client。
- AI_GUARDIAN_CARE_API_TOKEN：仅通过服务进程私有环境注入，不能放入 JSON、数据库、示例、Git、命令行或日志。缺失时 care API 返回503；错误凭据返回401。

## 依赖与本机复跑

本次核心新增存储/状态/影子模块只用标准库；认证 API 复用原服务 FastAPI，录像复用原 HistoryStore/EventClipCache，补传复用原 Paho client，不引入第二个摄像头或 Broker。

运行前必须 Python >=3.9、SQLite >=3.24。环境适配补丁使用Optional注解及兼容的文件导出API，适配开发板原Python3.9.2；详细版本与实测结果见board-environment-adaptation.md。3.11仍是本机固定复跑环境，不要求替换设备解释器。开发板现有 CANN、ACL、OpenCV、音频和 SDK 不在此次升级范围，不应为跑本地测试自动更新它们。既有边端依赖见 requirements-edge.txt；建议记录部署时的实际版本并保存在私有备份，不贴完整环境或凭据。

本机模拟固定主依赖：numpy 1.26.4、FastAPI 0.115.12、httpx 0.28.1；测试安装清单 requirements-care-validation.txt。只安装到隔离环境，不修改系统 Python：

```powershell
uv pip install --python python3.11 --target .tmp/care-validation --cache-dir .tmp/care-cache -r requirements-care-validation.txt
$env:PYTHONPATH = Join-Path (Get-Location) '.tmp/care-validation'
python3.11 tools/run_care_delivery.py --output .tmp/care-delivery-results.json
python3.11 -m unittest test_care_delivery test_care_release test_local_care_store test_sedentary_care test_shadow_mode -v
```

全套后端回归还需项目原有 requirements-production.txt 环境；使用原测试环境执行 `python -m unittest discover -v`。本地模拟编码器明确写入 FAKE NOT VIDEO，只证明缓存、事件索引和多事件关联，不证明 MP4 编码或真实视频播放。

## 本地 API 与传输契约

认证头只接受 Bearer，所有路径明确模型版本与人物：

- GET /api/care/{model_version}/{person_id}/events：返回 event_id、原发生时间和状态快照。
- POST /api/care/{model_version}/{person_id}/events/{event_id}/feedback：body 为 payload 或 operation=revoke/restore、reason；拒绝替换 event_id/发生时间。目标不存在于人物/模型/模式作用域则404。
- GET /api/care/{model_version}/{person_id}/feedback：默认 active；审计时显式 status=revoked/all。
- GET /api/care/shadow-report：认证后的本设备最近至多约100条影子报告，不等于持久历史或跨设备接口。

事件首次生成即写入 care_events；反馈 target_id、历史录像 events.id、event_recordings.event_id 及 outbox.event_id 使用同一值。反馈更新、审计和 outbox 入队同一事务。重复提交一条反馈行，revision 增加。撤销保留审计，并排队携带 is_revoked=true 的新版本。

新链路主题固定为 ai_guardian/care/reminders、ai_guardian/care/feedback，不能借用旧 fall/sit/stranger 主题。QoS1并等待发布确认，未 ACK 不标记成功；断网保留本地队列。message_id=原event_id:类型:revision，person_id/model_version 同时携带；接收方必须按幂等键去重、按同目标 revision 拒绝旧版本覆盖新版本。此处提供的是至少一次投递，不承诺远端正好一次。实际接收端尚未在本次连接或验收，未配置订阅端时不能宣称云端补传完成。

## 部署步骤（由操作者在设备执行，本次未执行）

1. 本机全套测试及五场景通过、工作树提交干净后生成包：

```powershell
python3.11 tools/care_release.py pack --bundle .tmp/care-release.zip
Get-FileHash .tmp/care-release.zip -Algorithm SHA256
```

包内 manifest 含源提交、回退基线、每个文件 SHA-256、原始基线副本。只收录白名单源码/SQL/测试/说明，不打包模型、签名、数据库、日志、实际配置或凭据。将包和独立的 care_release.py 工具传入设备待部署目录，校验 SHA-256 与本机记录相同。

2. 在设备设置 APP_ROOT 为实际应用目录、STAGING 为包目录、BACKUP 为新的私有备份目录、CARE_DB 为实际 care DB 文件。先记录当前服务状态、代码和私有配置的备份位置；不能假设设备部署副本等于 Git 分支。
3. 运行版本检查，再检查所有基线文件哈希；遇到设备独立改动会停止，先人工评审差异，不强行覆盖：

```sh
python3 -c 'import sys,sqlite3; assert sys.version_info >= (3,11); assert sqlite3.sqlite_version_info >= (3,24)'
python3 "$STAGING/care_release.py" check --bundle "$STAGING/care-release.zip" --app-root "$APP_ROOT"
```

4. 关闭新增 care 功能并停止服务，确认进程退出。备份私有 systemd 环境文件及原配置，勿打印其内容。执行安装工具：

```sh
systemctl stop guardian-board.service
python3 "$STAGING/care_release.py" apply --bundle "$STAGING/care-release.zip" --app-root "$APP_ROOT" --backup "$BACKUP" --care-db "$CARE_DB"
```

工具先完成全量哈希检查，再备份旧代码与 SQLite backup API 一致性快照，最后逐文件原子替换。整个多文件安装不是单个文件系统事务；若中断，保持服务停止，使用已生成 backup.json 执行回退。不要直接复制可能带 WAL 的 DB 文件。
prepared 回退清单在覆盖代码前写入，之后不再截断重写；安装命令成功退出才代表完成，清单的 prepared 状态也可直接回退。
重复部署或中断后的重试，应先用第一次的备份恢复基线，再使用新的备份目录安装；工具拒绝把已安装的新版本误当成2499d1d回退点。
5. 先保持 mode=off 启动服务，确认旧检测/录像/告警正常。再以私有配置启用 shadow，token 由私有服务环境注入；`systemctl daemon-reload`（仅修改了 unit/drop-in 时）后重启。初始化自动备份并增量迁移 care DB 至 v4，原反馈/常态样本不改写。
6. 按清单逐项验收。不能把本机结果当作板端结果；live 和 sync_enabled=true 必须另获实际场景及接收端验收准入，默认不开。

## 回退步骤

1. 停止 guardian-board.service；从私有环境移除新增 AI_GUARDIAN_CARE_CONFIG 或将原私有配置恢复为 off；保留新增数据库和补传队列，防止丢反馈。
2. 如安装后还有新反馈，先用 SQLite backup API 另存当前 DB；不要先用旧 v2 快照覆盖 v4 DB。
3. 使用安装时那份独立工具执行代码回退（工具不启动服务、不删除数据库）：

```sh
python3 "$STAGING/care_release.py" rollback --app-root "$APP_ROOT" --backup "$BACKUP"
systemctl start guardian-board.service
```

被替换文件恢复安装前的基线字节（准入要求2499d1d），新文件只按白名单逐个移除；若安装后代码又被独立修改则拒绝覆盖，需人工核对。v4 DB原样保留，但旧程序不得用 v2 store 打开它；旧服务默认不引用新 care DB，因此可保持隔离。只有确需旧数据读取时，才在另一路径打开迁移前备份，并保留 v4 新数据供后续前向恢复，不能自动降级。
4. 复验：旧服务启动、检测帧/推理状态、旧告警开关及主题、原录像查询和播放、care API 不再注册、无 care 补传线程、未删数据库/模型/配置。确认没有新增外发。回退不代表新 care 功能仍可用。

## 板端验收清单（待设备操作者逐项勾选）

- [ ] Python/SQLite/既有依赖版本已记录，模型版本与实际 OM/checkpoint 一致。
- [ ] 设备代码哈希通过；独立改动已评审；代码、私有配置与 SQLite 一致性备份可读。
- [ ] mode=off 保持旧检测、录像和告警行为；新增功能默认关闭。
- [ ] shadow 下出现 L0/L1 与差异报告，旧线上告警仍独立；无新 care 主题发送、无影子录像触发。
- [ ] 身份丢失/遮挡/未推理进入未知处理，不把框 ID 当人物；多人不会串计时。
- [ ] 静止站立、实际坐下、坐着移动、真实起身分别验证。当前静止代理的语义风险已解决或产品策略已明确；未满足则不准 live。
- [ ] 重启短间断保留计时/次数/ID，长间断作废并换新 ID；无重复 L0。
- [ ] 同事件重复反馈一行；撤销默认隐藏、审计可见；跨人物/模型/模式不能回写。
- [ ] 断网重启后队列仍在；有 ACK 才完成；接收方幂等/版本保护已验证，未接收不能宣称成功。
- [ ] 多事件共用真实 MP4 段，关联 event_id 与反馈 ID 一致；播放真实媒体验收单独记录。
- [ ] 实际演练代码回退，旧服务恢复且新数据库、模型和私有配置仍保留。

此清单当前未在开发板执行；不得预先勾选。OpenWolf 工具若未安装只影响辅助源码索引，不替代上述验收。

## 真实 App 对接待办

板端管理 API 与本地进程内回写已接通；真实 App 的事件 ID 获取、反馈入口与账号/设备安全授权尚未接通，已交给 Jianyuanxi： https://github.com/zmuxuny/ai-guardian-star/issues/25 。旧 MQTT 通知未加新字段，不得用旧跟踪框 ID 代替 care event_id。issue 明确了 App 修改范围、401/404/422/503处理、撤销/恢复和不处理的影响；本次不会把真实 App 回写、云端落库或真实设备效果标成已验证。

区域周报新增配置、接口、保留策略及回退至8c1ab28的特殊处理见 [weekly-report-contract.md](weekly-report-contract.md)。schema3旧运行时不能直接打开schema4库。
