# AF-01 短重启换轮／重复L0修复

基线df6d71c。此前实测：短停5秒，前后74.656秒内原事件被关闭、新建事件并重新L0，见 `board-reconnection-validation-2026-11-17.md`。本文件先记录已验证代码和部署方法，随后追加真实复验结果；没有真实结果前不宣称上板通过。

## 原因与最小改动

原检测输出is_sitting=False同时表示“重新积累静止时间”与“明确移动”，CareRuntime统一当NON_SIT，清掉恢复事件。用真实SQLite、虚拟时钟和原状态机已复现：耗尽提醒、有效35秒的事件在短重启后收到积累期False即变0。

- `StationaryTimer`只增加本次更新原因及care_observation方法：warming、still、moving、unreliable。anchor/since/samples/duration原算法不变。连续可观测位移才判moving，长缺口不当移动证据。
- 检测alerts只增加care_observation。原is_sitting、sit_duration_sec、跌倒和旧告警字段／阈值保持。
- CareRuntime将warming/unreliable／非法新判据作为低置信冻结，明确moving仍立即NON_SIT；旧调用没有新字段时保留旧行为。原120秒清零、身份隔离、静默和次数上限不变。

没有修改SDK、Python、OM、摄像头、引脚、时钟、端口或音视频布置。仍然是静止代理，不宣称已有真实坐姿分类。

## 本机证据

真实运行时回归覆盖：耗尽提醒的短重启保持ID和次数、真实运动立即复位、缺失仍120秒清零、长重启新轮、真实StationaryTimer判据；生产检测AST用例验证原布尔／时长与新增字段。新增缺陷回归先失败后通过。

首轮308项、最终313项完整本机回归均无失败（各18项设备／网络依赖跳过）；Python3.9标准库专项34项通过，65文件实际编译通过。原3.9独立环境缺numpy/FastAPI时不把导入失败归因于板端，用已有3.11依赖环境跑完整回归。独立审查通过。

## 发布与回退

设备是平铺部署副本，不是Git仓库。三个固定文件：guardian_runtime.py、ascend_main_other.py、care_runtime.py。实际原文件指纹已对照冻结基线；设备ascend_main_other含独立增强，只从实际原字节精确增加两行关怀判据；去掉新增字段后AST必须与原文件完全一致，不能用仓库整文件覆盖。

本机打包命令（实际原文件和包均留在被忽略的私有目录，不能入Git）：

```powershell
Set-Location 'C:\Users\Yang\.codex\worktrees\board-py39-adaptation\zhihuixing'
$releaseRevision = git rev-parse HEAD
python3.11 tools/care_runtime_patch.py pack --originals .tmp/af01/private-original --baseline .tmp/af01/original-baseline.json --bundle .tmp/af01/patch.zip --revision $releaseRevision
```

发布前在板上隔离目录运行新用例及apply/rollback演练；全量备份代码／配置／SQLite在线快照，核对无关怀环境变量。先提交push zy，再对原服务停服应用。以下为板上固定路径：

```sh
systemctl stop guardian-board.service
/usr/local/miniconda3/bin/python3.9 /root/guardian-care-staging/af01-release-20261117/care_runtime_patch.py apply --app-root /root/ai_guardian --bundle /root/guardian-care-staging/af01-release-20261117/patch.zip --backup /root/guardian-preflight-backups/20261117-af01/patch
# 仅上条成功后执行；失败保持停止，按下段回退。
systemctl start guardian-board.service
```

发布器先验证三个原指纹、三个payload指纹及语法，服务必须inactive；新备份不覆盖，备份manifest先落盘，再逐文件原子替换。中断后不盲目启动部分新代码。profile三项新期望指纹取实际payload哈希，其他25项保持；新Probe通过后才进入shadow。

```sh
systemctl stop guardian-board.service
/usr/local/miniconda3/bin/python3.9 /root/guardian-care-staging/af01-release-20261117/care_runtime_patch.py rollback --app-root /root/ai_guardian --backup /root/guardian-preflight-backups/20261117-af01/patch
# 仅回退成功才启动；数据不回滚、不删除。
systemctl start guardian-board.service
```

回退精确恢复本次之前三个原字节，再使用原df6d71c profile核查。需要继续回退e463172/063ea04时，必须先回退本AF-01层，再按此前的身份补丁→平铺overlay顺序；原严格发布器遇到AF-01新指纹拒绝覆盖是保护行为，不能删检查或强推覆盖。

## 现场复验顺序

1. off确认服务、28指纹、原模型、摄像头／JPEG，记录新全量备份及三文件回退备份。
2. 新建独立shadow会话 `/root/guardian-care-staging/care-validation-20261117-af01`，sync=false、快测15/10/10秒，原库不写，30分钟自动恢复保护。
3. 现场坐稳，先取得实际正计时和同一事件L0/L1；短停5秒。预期旧事件仍相同、恢复期间计时冻结、不再发L0；不能只有“服务已起来”。
4. 真实移动应立即清零；持续缺失／长停超过120秒应清零新轮，不因为修复短停而永久保留旧事件。各项依据原始记录单独判定，不伪造身份、动作或超时。
5. 收尾实际恢复off并Probe。未测项仍未测；第2步完整门禁未通过时，不进入第3–6步，不开live，不外推真实音频。

## 已完成的发布前板端验证

19:21，原Python3.9.2隔离运行22项模拟测试通过；使用三份实际原文件在simulated-app演练apply/rollback，三个文件字节完全恢复，新增模拟数据标记保留；运行目录原指纹不变。

19:22，新备份 `/root/guardian-preflight-backups/20261117-af01/preflight` 实际verified：28份代码／模型文件、2份SQLite在线快照、1份私有配置，实际进程无关怀配置环境变量。三文件替换前仍需发布器停服及原指纹准入；此处不是现场短重启复验通过结论。
