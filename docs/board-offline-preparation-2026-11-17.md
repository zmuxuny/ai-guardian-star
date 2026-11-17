# 2026-11-17 离线准备记录与复连执行清单

适用基线：已交付的 `e463172`，入口适配来自 `063ea04`。本轮开发板离线，未尝试 SSH、未部署、未改变设备代码、配置、数据库或硬件布置。以下历史实测与本轮离线结果分开记录。只交付 zy，不开 PR。

## 一、本次验证情况

| 检查项 | 已发生的事实 | 结论／遗留 |
| --- | --- | --- |
| 昨日第1步备份及环境适配 | 原 Python 3.9.2、SQLite 3.40.1；代码/配置/模型归档和两个数据库在线快照已完成。063ea04 在原解释器101项模拟通过；平铺安装/回退演练通过 | 昨日适配部署准入通过；今天设备状态未知，需重新 Probe |
| 昨日关闭模式旧功能 | 原服务启动方式及依赖未替换；camera=true、约7.5推理帧/秒、帧递增、JPEG有效、MQTT连接；原视频时间戳增强保留 | 昨日 off 冒烟通过，不代表今天在线 |
| 昨日身份映射 | 登记姓名与用户ID不同，原检测输出姓名；e463172 用私有姓名→ID映射接通关怀身份，保留原检测标签与线上输出；34项专项在板上原3.9和本机通过 | 代码适配已修复；最近一次实际采样 recognized=P2 |
| 昨日真实动作观察 | 用户确认坐好后，最后取回的样本：camera=true、detections=1、身份已映射；两人的状态仍IDLE，seated_seconds=0，L0/L1记录均0，live outbox=0 | 第2步未通过也未判定故障：尚未取得随后50秒观察结果；不能说已完成久坐计时/升级 |
| 昨日遮挡／身份丢失／重启／静默 | 尚未取得完整动作序列和恢复结果。曾有摄像头短暂断开后自行恢复，但没有受控动作证据 | 第2步仍需逐项实测；不能拿一次摄像头抖动代替遮挡测试 |
| 昨日自动恢复off | 旧会话曾安排30分钟自动清理；设备离线后没有回读进程环境 | 未确认。复连必须先恢复本工具拥有的旧override并回读，不能假设已经off |
| 第3–6步 | 第2步尚未确认通过 | 未进入；App反馈仍依赖 #25，真实关怀音频未接入，输入仍是静止代理 |
| 本轮离线核对 | 使用本机独立 Python 3.9.25，64个板端相关Python文件实际 py_compile；另做3.9语法/API扫描 | 通过；Windows x86_64只证明Python兼容，不证明ARM64 SDK ABI或外设 |
| 本轮工具验证 | 新工具20项覆盖步骤门禁、live拒绝、SQLite备份不覆盖、包可复现、回退层次、恢复失败重试、看门狗先启动、人员/会话不能拼接通过、采集错误不能自动通过；连同既有纯模拟核心用例共108项通过；验证包独立解包后周报12项通过 | PowerShell7语法解析通过；未运行任何SSH命令 |

历史证据：`docs/board-environment-adaptation-evidence.md`、`docs/care-delivery-evidence.md`。旧全套279项无失败、18项设备/网络依赖跳过是昨日结果，不是本轮重新上板结果。

## 二、逐项适配结论

“适配”仅指当前冻结部署代码继续使用原环境；“必须在线确认”不算已经验收。

| 核查项 | 离线结论与依据 | 在线确认／动作 |
| --- | --- | --- |
| 芯片型号与目标 | 适配现有Linux aarch64/Ascend部署，不新增MCU固件。历史记录没有准确SoC型号和原ATC转换命令；不能据此批准重新转换OM | Probe采集可得的NPU元信息；准确SoC/原ATC记录缺失，替换模型前须取得，不能猜型号 |
| 模型 | 适配冻结的best.om，7790030字节，SHA256 `3521835ffa0cc4d68990d37204ead5ca43b9722d8a5917ec21f28b82df9a0a87`；原检测输入640×640，不改变模型/布局 | 核对文件指纹并用原入口实际推理，不能用Windows编译代替 |
| Python与SQLite | 昨日两项不适配已由063ea04修正：time与None的联合注解改Optional；Path.write_text(newline=...)改open写入。本轮未发现新的核心不兼容；3.9.25编译通过 | 原板Python3.9.2在昨日已运行测试；复连核对解释器和SQLite，不升级系统依赖 |
| 平铺部署 | 原板入口和音视频模块含仓库没有的增强，直接复制src会覆盖原功能；063ea04已改为指纹准入+三方合并。适配当前冻结字节 | 本轮只上传验证工具到隔离staging；**不重新覆盖src或整个应用目录** |
| 引脚／GPIO／pinmux | 适配：这些Python改动没有新增引脚定义、GPIO或设备树配置，沿用原外设接线 | 保持现有插线；实际摄像头/音频设备枚举仍须在线确认 |
| 时钟／波特率 | 适配：未新增UART、晶振、PLL或串口烧录参数；音频48kHz、S16、960采样/20ms沿用原值。系统时间影响静默及周报 | Probe比较操作机UTC，偏差超过120秒停止；不自动校时，不改串口波特率 |
| 摄像头与推理 | 适配：沿用V4L2扫描与原摄像头控制，不另开摄像头/NPU。请求30fps不等于实际推理30fps | 检查camera_connected、实际fps、frame_count和动作响应；设备离线不能确认遮挡质量 |
| 音频外设／本地C桥 | 适配原配置：AO device2/channel0是音频设备号，不是GPIO2；保留原C桥和libguardian_audio.so，不改变原声道实现 | Probe读取ELF头；Windows无CANN头文件/ARM工具链，本轮未重新编译该既有C桥，不能宣称真实关怀播报通过 |
| 服务／网络／调试 | 适配：guardian-board.service、/root/ai_guardian/start.sh、原Python路径、HTTP5000/UDP8888及FRP均保持，不烧录、不改JTAG/调试器 | 检查实际MainPID、进程环境、服务状态。SSH6022是既有入口；不改路由、端口和硬件布置 |
| 关怀身份与影子隔离 | 姓名/ID不一致已由e463172修复；本轮无新业务修改。shadow仍不写新线上outbox，不触发模拟播报以外的音频路径 | 同一事件的L0/L1、影子记录及零线上outbox必须实际观测；原旧告警功能本身仍照常运行 |

本轮新增内容仅是验证工具、冻结指纹、离线测试和文档；未修改src业务逻辑。新工具审查中修复了：恢复中断后的可重试性、启动看门狗后才启用临时配置、按同一人员/会话/事件判断证据，避免假通过。

## 三、工具、输出及安全边界

入口：`tools/Invoke-BoardValidation.ps1`（PowerShell7）；板上执行器：`tools/board_validation.py`（Python3.9标准库）。本机Prepare不连接设备；其他Action是明确的在线动作。

冻结指纹在 `deploy/board/care-validation-baseline.json`，来自实际平铺部署及e463172补丁，并非直接取可能有CRLF差异的src。指纹不符时停止，先记录差异，不自动安装或更新基线。

Prepare生成 `.tmp/board-ready-kit/board-kit.zip`、编译报告，包含完整说明、现有纯模拟周报用例、care模块与SQL；不含模型、私钥、token、真实姓名、数据库或录像。压缩包内容、排序和时间戳固定，可重复生成同一哈希。设备仅在SHA256校验后解包；不覆盖已有内容不同的staging文件。

默认新会话 `/root/guardian-care-staging/care-validation-20261117`，必须位于应用目录之外。StartShadow先备份代码/配置、在线SQLite快照及原服务信息，再使用独立测试model_version、独立数据库和私有token。原用户数据库不写、不删除。只有本工具拥有的三行临时dropin可以清理；遇到外来配置拒绝操作。

输出：`ledger.json`保存门禁；`probe.json`保存准入；`observations.jsonl`逐秒记录角色代号、状态、计时、级别、event_id、影子播报时间/文案标识及outbox行数；`step2-assessment.json`汇总；后续`step3-*`、`step4-*`、`step5-audio.json`、`step6-*`各自留证。PASS是该输出声明范围的通过；INCOMPLETE/NOT_EXERCISED/BLOCKED都不能推进下一步。工具非零退出时先看结构化原因，不能改ledger绕过。

DownloadEvidence只下载允许的去身份记录到本机私有目录，缺文件会明确报告；这些记录有事件ID，仍不入Git。私有config/token/roles/DB/MP4不下载到公开交付。会话自动恢复off的看门狗在启用shadow前确认启动，30分钟后清理；异常重试。人工结束也应RecoverOff并Probe，不依赖看门狗推测成功。

## 四、照顺序执行的复连清单

以下命令在本仓库工作树的PowerShell7执行。为减少重复，先定义固定绝对路径；若工作区搬家，只修改这一个路径。

```powershell
$boardCheck = 'C:\Users\Yang\.codex\worktrees\board-py39-adaptation\zhihuixing\tools\Invoke-BoardValidation.ps1'
& $boardCheck -Action Prepare
```

确认输出status=PASS、interpreter为3.9.25、compiled_files=64、board_contacted=false。没有本机3.9时工具退回3.11并如实显示，不能把该结果称为3.9实编译。

### 第1步：环境、旧配置收尾与备份

- [ ] 板连接后先Probe，记录真实运行环境；若因连接/服务/指纹失败，停止后续步骤。
- [ ] 对昨日旧会话RecoverOff，核对真实进程环境；NO_CHANGE不等于已经off。
- [ ] 再Probe，确认care_mode=off且care_config_present=false、相机/时间/指纹均通过。陌生override不可删除。

```powershell
& $boardCheck -Action Probe
& $boardCheck -Action RecoverOff -Session '/root/guardian-care-staging/shadow-acceptance-20261116'
& $boardCheck -Action Probe
& $boardCheck -Action BaselineResources -Seconds 30
```

首次Probe只读取应用数据并在staging记结果，不改应用；RecoverOff只收尾已备份的旧临时配置。若旧备份丢失或出现陌生配置，先记录BLOCKED并补备份，不能猜测删除。下一步StartShadow会在任何应用配置改动前做新的非覆盖备份。资源采集只读取现有进程/proc/sys及HTTP，不另外打开外设；30秒仅作off基线，不是稳定性验收。

### 第2步：关闭／影子模式（本轮唯一允许先开展的范围）

- [ ] 原视频、检测、历史页面、原音视频连接由现场观察确认；启动shadow后也应保持原功能。观察旧告警是否正常遵循原策略，**不主动触发旧危险告警**。记录具体检查项，不写笼统“正常”。
- [ ] 启动加速shadow：L0=15秒，L0→L1=10秒，重复间隔10秒，其他次数上限沿用代码；sync=false、独立测试库。此为计时链路验证，不等于正常30分钟阈值实测。

为保持快测会话可继续第3步，**先在自然静默时段完成下面的静默会话，再启动快测会话**。如果当前不在22:00–07:00，只能先做快测并收尾，静默保持未验证；不得越过第2步。不能通过修改系统时钟满足时段。

```powershell
& $boardCheck -Action StartShadow -Session '/root/guardian-care-staging/care-validation-20261117-quiet' -Quiet
& $boardCheck -Action Mark -Session '/root/guardian-care-staging/care-validation-20261117-quiet' -Phase quiet -ConfirmedAction
& $boardCheck -Action Observe -Session '/root/guardian-care-staging/care-validation-20261117-quiet' -Seconds 40
& $boardCheck -Action RecoverOff -Session '/root/guardian-care-staging/care-validation-20261117-quiet'
```

静默预期quiet=true且pending_level存在、没有播报。接着启动快测会话：

```powershell
& $boardCheck -Action StartShadow
```

每个动作开始时先Mark再Observe；-ConfirmedAction表示现场确实执行了该动作，不能只发命令。Role=auto要求画面中唯一已登记人员；多人时从输出recognized_roles选择实际测试者的P编号并加`-Role P2`，后续保持同一人。P编号不跨会话混用。

```powershell
# 坐好、面部无遮挡，观察静止代理开始计时、同一event_id先L0后L1。
& $boardCheck -Action Mark -Phase seated -ConfirmedAction
& $boardCheck -Action Observe -Seconds 50
# 原位遮挡面部20秒：同一人进入PAUSED、seated_seconds冻结，不能静默吞掉缺失。
& $boardCheck -Action Mark -Phase cover -ConfirmedAction -Role P2
& $boardCheck -Action Observe -Seconds 20
# 解除遮挡、回到坐姿：应恢复原轮计时而非凭空清零。
& $boardCheck -Action Mark -Phase seated -ConfirmedAction -Role P2
& $boardCheck -Action Observe -Seconds 35
# 离开画面：至少连续120秒身份丢失，原轮应清零；在已有正计时后再离开。
& $boardCheck -Action Mark -Phase leave -ConfirmedAction -Role P2
& $boardCheck -Action Observe -Seconds 135
# 回来坐下，重新形成事件。
& $boardCheck -Action Mark -Phase seated -ConfirmedAction
& $boardCheck -Action Observe -Seconds 50
# 现场真正起身并活动，预期IDLE且计时为0；不能只看标签变化。
& $boardCheck -Action Mark -Phase standing -ConfirmedAction
& $boardCheck -Action Observe -Seconds 20
# 继续站着不动45秒，记录静止代理是否错误累加；出现则阻止live，不能宣称姿态检测完成。
& $boardCheck -Action Mark -Phase stand-still -ConfirmedAction
& $boardCheck -Action Observe -Seconds 45
# 再坐好后做短、长服务重启；现场应保持坐姿，工具记录前后事件ID及提醒次数。
& $boardCheck -Action Mark -Phase seated -ConfirmedAction
& $boardCheck -Action Observe -Seconds 50
& $boardCheck -Action Restart -RestartKind short
& $boardCheck -Action Restart -RestartKind long
& $boardCheck -Action Assess2 -IncludeSession '/root/guardian-care-staging/care-validation-20261117-quiet'
& $boardCheck -Action DownloadEvidence
```

上例P2仅来自上次最后识别样本；**今天必须以本会话实际输出为准**，不能认定仍为P2。短停5秒、长停130秒并恢复原服务；工具还观察35秒。模型暖机若超恢复窗口，会被记录成失败，不能人为调大窗口掩盖。手工比对：短中断仍同轮、无补发重复；长中断新轮；遮挡满2分钟清零；站立静止误报是已知代理限制，需要记录，不获准live。

Assess2同时要求同一会话/人员/事件的L0和L1、真实动作证据、短长重启及零线上outbox。静默起止边界用既有虚拟时间用例验证；要声明真实时段边界已上板验收，须在当地07:00/22:00前后自然观测并记录，不能伪造物理时间。整体第2步即使PASS也只覆盖影子/静止代理/模拟播报，不能外推真实语音关怀。若今天无法等到静默窗口则该项NOT_EXERCISED，停止第3步。到此结束时必须RecoverOff再Probe；如继续第3步，保持当前会话，不执行收尾命令直到完成或阻塞。

### 第3步：事件与反馈（第2步PASS后）

测试库必须仍是本会话拥有的shadow配置；若已RecoverOff，不能复用旧会话启用或伪造门禁，应以新的Session路径重新完成第1–2步。静默会话保留记录供快测Assess2合并。快测完成后保持在30分钟窗口内继续；超过窗口，重新验证。后续所有命令沿用该Session。

```powershell
& $boardCheck -Action Feedback -Role P2
& $boardCheck -Action Media
```

- [ ] Feedback使用实际产生的事件ID，重复提交仅一条、更新不变created_at、撤销默认隐藏且审计可见、错误/无token拒绝、错误人/版本拒绝。仅修改独立测试库。
- [ ] Media只读取实际care事件与历史录像关联；至少两事件共用同一segment，下载真实MP4并以ffmpeg解码5秒（静音输出，不播放声音）。板缺ffmpeg时明确阻塞，不自动安装。不添加假关联，不拿无关旧录像替代care-ID。
- [ ] App负责人按 #25 在真实客户端确认同一事件ID反馈/撤销与实际MP4播放。影子本身不触发新录像，所以可能没有care录像关联；这是明确缺口，不能临时开live绕过。

`CompleteStep -Step 3 -Proof <板上私有JSON绝对路径>`仅接受真实证据；JSON字段是real_app=true、played_on_client=true、app_event_id和board_event_id均为本次feedback输出ID、app_revoke_confirmed=true。须由真实操作后记录，不预填true。目前 #25 未接通，step3保持INCOMPLETE，这也阻止第4–6步。真实客户端操作与接口未实现部分无法在今天编造可执行调用。

### 第4步：区域周报（第3步PASS后）

```powershell
& $boardCheck -Action EnableWeekly
& $boardCheck -Action WeeklyFixture
& $boardCheck -Action WeeklyLifecycle -Role P2
```

- [ ] EnableWeekly备份独立测试库后只开启该配置weekly开关；不更改原用户数据库。
- [ ] WeeklyFixture在板上用临时库重跑现有跨周、重复事件、反馈撤销、时区、过期清理五类构造场景，并读取真实聚合HTTP输出；不生成周报文字。
- [ ] 检查三维键（粗区域/时段/事件类型）、质量、人工确认数、有效观测时长；无观测标志不能当零风险；不足最小样本量不输出趋势。
- [ ] WeeklyLifecycle只清理本会话拥有的person+acceptance模型域，验证保留期清理、个人删除、派生统计归零且重启不复活，随后要求现场重新形成新事件，事件ID不能是被删除的旧ID。
- [ ] 现场确认设备时区与实际粗区域配置。当前快测region_id=unknown，不得把它宣称为真实区域映射验证。

实际区域映射确认后在板上私有JSON记录real_region_mapping_confirmed=true，执行`CompleteStep -Step 4 -Proof <实际记录路径>`；工具还会检查新采集事件及清理结果，单有true不能过门禁。

### 第5步：音频与同步（第4步PASS且真实接入补齐后）

```powershell
& $boardCheck -Action AudioReadiness
```

当前结果明确BLOCKED：RecordingSpeaker仍为模拟；回应入口、真实关怀音频适配与对讲抢占仲裁、实际接收端未齐。不能拿旧音频通路可用推断关怀音频接通。本轮不改变业务功能，也没有这些未来接口的真实地址/契约，不能提供虚假调用脚本。

接入完成后必须按顺序留证：同一care event_id对应真实发声且与模拟文案一致→实际用户回应抑制升级→对讲开始立即抢占且结束按策略恢复→只隔离测试接收端网络验证本地落盘、恢复连接后同一ID幂等补传→接收端处理与回执一致。禁止修改板默认路由或关闭现有网络。当前不允许CompleteStep5自动PASS；新增接入功能时连同测试适配器一并交付，按功能规则决定PR。

### 第6步：稳定性与回退（第5步PASS后）

```powershell
& $boardCheck -Action Stability -Seconds 1800
& $boardCheck -Action RollbackReadiness
& $boardCheck -Action CodeRollback
& $boardCheck -Action Probe
```

Stability记录原进程RSS/HWM(KiB)、线程数、CPU tick、温度(毫摄氏度)、实际fps/帧号。30分钟是采样段，不是已约定资源SLA；没有给定CPU/RSS限值，报告保持INCOMPLETE，由实际曲线/日志及长时运行结果判定，不能凭空设置阈值。更长观察按会话分段归档。

**真实回退演练会停服务，只在第5步已通过时使用。** 两层原始备份必须齐全，工具先验证全部指纹：

1. 停本会话shadow并停服务；先反向恢复e463172两文件补丁，来源 `/root/guardian-care-staging/shadow-acceptance-20261116/pre-shadow-backup/manifest.json`。
2. 再按 `/root/guardian-preflight-backups/20261116-env-adapt-135914/overlay/backup.json` 回退063ea04平铺安装，恢复适配前原入口字节；不是整库回滚或替换模型。
3. 恢复原服务；遇未知新代码或中断保持停止，先排查，不启动半套恢复代码。数据库不恢复、不物理删除。
4. 复验camera/fps/帧递增、原视频时间戳、历史录像、原对讲、原告警策略、无care临时配置。原代码回退后冻结新基线Probe指纹应不匹配，这一结果是预期，不可强改新基线让它PASS；用原备份manifest对照恢复字节。CodeRollback只报告已请求启动、INCOMPLETE，必须现场复验后才可认定完成。

需要回到新版本时先备份现状，再按 `docs/board-environment-adaptation.md` 的原入口三方合并发布方式重装063ea04，再应用经过核对的e463172两模块；不能拿本次验证包当部署包。当前设备上既有两份回退材料可读性必须在RollbackReadiness在线核实。

## 五、结果记录与问题去向

每个步骤保存：时间及会话、动作、预期、实际、证据文件、PASS/FAIL/INCOMPLETE、原因及下一步。自动输出已有这些数据的机器记录；现场观察（原页面/声音/实际姿态/区域）由操作者写入私有实际记录，不以脚本猜测。仓库只提交去身份的结论。

| 遗留 | 去向 | 是否需要板在线 |
| --- | --- | --- |
| 上次未完成的计时/动作/静默/恢复/隔离 | 按第2步脚本逐项执行；失败定位实际sensor→identity→state→broadcast/outbox日志，不绕状态机 | 是，依赖真实输入 |
| 临时shadow是否已清理 | 首次RecoverOff旧会话，再Probe实际进程 | 是 |
| 准确芯片与OM转换来源 | 采集板上元信息；原ATC记录缺失由模型维护资料补足；保留原OM不重编 | 设备信息需在线，原转换记录还需历史资料 |
| 真实App反馈/录像关联 | 既有Issue #25，由Jianyuanxi负责App契约/客户端联调；本轮不重复提issue | 是，且需App |
| 静止代理不等同坐姿 | 记录站立静止反例，禁止live语音完成结论；真实坐姿分类不属于本轮适配修改 | 是 |
| 真实关怀音频、回应、抢占、同步接收 | 第5步阻塞，后续真实接入功能单独交付；本轮不伪造完成或新建空PR | 是，且代码能力尚缺 |
| 周报真实区域/生命周期、稳定性与完整回退 | 预写脚本已齐；按门禁在前序通过后执行，不越级 | 是 |

本轮离线交付完成的范围是记录、兼容核对、可重复编译/模拟检查、复连验证工具和清单；不是六步上板验收完成。

复现本轮离线模拟检查（不等待真实时间，不接设备）：

```powershell
Set-Location 'C:\Users\Yang\.codex\worktrees\board-py39-adaptation\zhihuixing'
& 'C:\Users\Yang\.codex\worktrees\board-py39-adaptation\zhihuixing\.tmp\offline-python\cpython-3.9.25-windows-x86_64-none\python.exe' -m unittest test_board_validation test_sedentary_care test_local_care_store test_shadow_mode test_region_aggregation test_shadow_scenarios test_care_identity test_weekly_report.WeeklyTests -q
```
