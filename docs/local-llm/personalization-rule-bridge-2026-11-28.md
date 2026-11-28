# 个性化规则修复与CSV到模型HTTP接线

2026-11-28，用户同意按计划修正晚起窗口、接通三规则发送，并进行真实模型板端隔离联调。代码及本机验证完成；开发板转发连接不可用，板端部分尚未开始，本次以草稿PR交付并保留待验项。

## 修改与来源

从已审阅的839edbe22ce9742e99ae36bcbdef93bc92308aa8复用七个Python源/测试文件，引入提交790c0c8逐文件保持原字节；未合并个性化分支或引入App代码，原下载包不改。

晚起基线训练仍读取06:00至10:00前。检测窗口延伸至11:30前，覆盖全部受支持基线加90分钟的采样点：08:30→10:00、09:00→10:30、09:55→11:25。缺采和提前离床的抑制规则保持。原先3种基线均在回归中失败，修复后通过。

新增`tools/personalization_routine_peer.py`：固定启动时历史基线，周期读取完整观测CSV，过滤当前时钟之后的记录，由三规则生成事件，添加显式绑定设备ID，事务登记到现有Personalization发件箱，再向模型提醒接口发送。重扫及相同配置重启沿用事件ID、触发时间和有效期；旧事件保留原期限，不刷新成新提醒。结果接收、低版本求助保持和待处置去重复用原模块。

输入应为完整、追加式CSV，列为timestamp,zone,state；历史和观测日期须分离。此入口尚不支持滚动截断文件，未接生产采样器。历史文件或阈值配置跨重启改变的迁移另验，不能用本轮相同配置去重测试推定。

首次独立审查发现超长CSV字段可抛出csv.Error并退出接收/重试循环。新增真实CLI失败回归复现后，于a10d22b将csv.Error及时间转换OverflowError作为扫描错误隔离；回归验证坏CSV期间原有提醒仍实际发送，needs_help结果仍接收并保存。修复后定向复审无剩余Critical/Important。

## 启动方式

先准备新鲜、时间带时区并按5分钟对齐的完整观测CSV，以及日期分离的历史CSV。两个服务在同一台机器运行、设备ID相同，以下端口为隔离示例；模型服务须另行准备并核验资产。

```powershell
python -m tools.personalization_v5_text serve --role model --db .tmp/routine-pair/model.sqlite --device demo-device --port 18101 --model-url http://127.0.0.1:18081 --model-id qwen25-15b-q4km --policy v4-fast --peer-url http://127.0.0.1:18102
```

另一个PowerShell终端，在同一仓库根运行：

```powershell
python -m tools.personalization_routine_peer --history history.csv --observations observations.csv --db .tmp/routine-pair/personalization.sqlite --device-id demo-device --model-port 18101 --results-port 18102 --scan-seconds 5
```

可加`--seconds 30`限制试验时长；恢复使用相同数据库和配置。入口只绑定127.0.0.1，不安装或启动模型，不发送MQTT。已有固定2026-11-24日期的生成CSV用于规则回放；在当前墙钟运行会保留已过期事件并标记未确认，不会把旧时间改为当前时间。

## 已完成验证

- 晚起边界、规则到持久化发送、未来样本不提前触发、过期不发送/不刷新、历史/观测日期分离、重扫/重开去重和三类HTTP回传均有回归。
- 显式测试两种真实HTTP实现互通：三条规则由CSV生成提醒，分别取得ok、needs_help、unclear并由个性化端保存，重复结果回duplicate；使用模拟模型，不能作为真实模型验收。
- 完整CLI测试验证过期文件不触发发送；超长CSV字段期间已有队列仍送达且结果端存下求助。
- 最终170项相关本机测试全部通过（29.328秒），四个变更模块编译及diff检查通过。独立源码/异常隔离复审无剩余阻断。
- 原上游21项测试通过根目录加载器纳入现有CI发现，避免tests目录无__init__导致这些测试被跳过。

本机记录与来源/计划上传哈希位于`evidence/personalization-rule-bridge-2026-11-28/`。planned-upload-manifest仅说明准备的30份文件，不表示已上传或在设备运行。

## 板端待验

本轮一次直连6022被关闭，既有网关本地对应端口ConnectionRefused。已询问用户恢复，随后未持续重试。未执行新一轮远端备份、上传、启动模型、生产状态/资源/收尾检查，不能把此前板端结果或准备好的文件包算作本轮通过。

`tools/local_routine_v5_scenario.py`及`tools/local_routine_v5_board_trial.py`已准备：三种规则、09:00基线的10:30晚起、重扫重开去重、真实模型辅助、失败后规则求助及同服务自动恢复。场景本机用替身后端跑通过，板端须使用新私有目录，先备份62文件/SQLite、核对资产及上传哈希，再实际验证。使用合成CSV和双方一致的回放墙钟、真实单调请求时限，不能冒称真实作息采样或真实老人回答。

生产默认策略、care/App、报警阈值、模型生成问候、语音、物理断网断电、窗口外独立求助和长期运行均未变更或新增验收。草稿PR目标zy，不自动合并；待设备恢复完成真实模型联合验证及证据复核后再转正式。
