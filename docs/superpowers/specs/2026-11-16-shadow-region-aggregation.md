# 影子模式与区域聚合设计

状态：用户已授权自主确定并直接实施。基线必须为现有 AlertEpisodeTracker；本设计据此保留原方法语义，不使用模拟计数函数冒充现有逻辑。

## 本阶段范围

仅构造数据，不导入真实设备、事件数据库、摄像头、网络或音频；不修改 guardian_runtime.py、ascend_board_server.py 或其输出。工作与推送目标仅为 zy。现有 AlertEpisodeTracker.update(alerts, now_ts) 保持原样。

采用独立影子执行器加纯函数区域聚合，而非在生产推理循环中增加分支。本阶段仍使用真实的旧逻辑函数，只把输入换成构造场景。现有 helper 只识别 fall/sit/stranger，返回本次新增事件列表，没有区域或时长输出；因此比较新增事件次数，时长和覆盖时长另外与手工期望验证。

## 数据源接口

EventSource.read_batch() 返回一个有限批次的两种输入视图，由构造场景人工明确对应关系：

- frames：按时间给出的检测帧，字段 at_ms、model_version、alerts。alerts 保留原 helper 所用的 id/status/is_sitting/face_label，不替换其判断规则。允许为空列表以表示正常/目标消失等原语义。
- events：规范区域事件，字段 event_id、person_id、model_version、region_id、kind、start_ms、end_ms。每个事件属于一个区域。kind 本版支持 fall/sit/stranger，以便与旧逻辑比较；更换类型集合应明确升级协议。
- query：start_ms、end_ms，表示 [start_ms,end_ms) 的统计范围；所有时间为整数 UTC Unix 毫秒，无真实时钟取值。

frames 与 events 是同一场景的两种视图，不宣称目前已有通用的检测帧到稳定区域事件转换算法。后续真实数据源适配器负责时间、人物关联、稳定事件 ID、区域归属和事件起止，计算层与输出层不改。开放事件 end_ms=None 暂不累计，明确列为 open_event；不能用当前真实时间悄悄补齐。

一个批次内的旧逻辑按模型版本分别持有独立 tracker，避免版本切换串计数。各场景使用新实例，跨批次持续运行时由调用方持有实例并保持输入时序；构造测试不依赖其他用例的运行顺序。

## 旧逻辑基线与影子隔离

- 基线适配器逐帧调用真正的 AlertEpisodeTracker.update，使用 at_ms/1000 转为其所需秒数，保留默认 max_gap=4.0。对 query 范围外的前置帧仍更新 tracker 以预热，但只统计范围内新增事件。
- 基线输出包含按模型与类型的新增次数及逐帧新增事件，用于对照；该适配器是离线调用入口，不替换现有 HTTP/MQTT 输出。
- 通用影子执行器接受 legacy(batch) 与 candidate(batch) 回调。原逻辑收到原始输入，保留其既有输入修改行为和返回对象；影子收到原逻辑执行前的独立副本。影子结果及差异只进入独立报告，不写回原逻辑输入、状态或返回对象。隔离依赖回调只访问传入数据；这不是任意不可信代码的安全沙箱。
- 使用独立线程执行影子计算；原逻辑不等待影子完成。原逻辑自身异常原样传播；影子计算/比较/记录失败只进入影子错误状态，不替换原返回值。待处理数有上限，满时明确记录 skipped，不能阻塞原路径或无界积压。
- 离线测试完成后显式收集影子任务，再检查报告；稳定报告不含耗时、真实时间、线程 ID 或随机 ID，按提交序号排序。后台任务永不直接写现有输出。

## 区域聚合口径

窗口固定 300000 毫秒，按 Unix 时间从零对齐。输出键为 (model_version, region_id, kind, window_start_ms)。不同模型不混算；人物通过 person_count 表达，区域汇总有意允许多个人共同计入。

- event_count：该区域/类型/窗口中有重叠的去重事件数。跨窗事件在每个重叠窗口各计一次，因此不能把各窗口 event_count 直接相加用作全局事件总数。
- person_count：同组有效事件涉及的去重 person_id 数。
- event_duration_ms：各事件与 query 及窗口相交部分的时长之和。多人或多事件重叠时允许大于窗口时长。
- occupied_duration_ms：上述相交时间段的并集时长，不因多人重叠重复累计；范围为 0 到本窗口与 query 的有效相交长度。它表示该区域有此类事件覆盖的时间，不代表整个区域的人员占用率。
- start_ms=end_ms 是瞬时事件：落在 query 内时按起点归属窗口，事件数和人数为 1，时长为 0；不跨到下一个窗口。区间按左闭右开处理，恰好在窗口右端结束不进入下一窗。
- 跨 query 边界只累计相交部分，完全在外的事件列入 excluded，不当作非法数据。无有效事件时 groups=[]，不伪造大量零值区域。
- 去重键为 (person_id, model_version, event_id)。内容完全相同的重复行仅计一次。相同键出现不同区域、类型或起止时间时属于冲突，整个冲突键的各行均拒绝，不能按先后顺序任取一行。跨区域的连续行为暂需上游提供明确的分段事件 ID。
- 比较旧逻辑新增次数时，只数 start_ms 落在 query 内的唯一事件，按模型与类型汇总；与区域窗口内的重叠 event_count 分开，避免预热事件、跨窗切分导致假差异。

## 稳定输出协议 v1

聚合 JSON 固定包含 schema_version、query、summary、groups、rejected、new_event_counts。query 的 start_ms/end_ms/window_ms 为整数。groups 每项固定包含：model_version/region_id/kind（字符串）、window_start_ms/window_end_ms/event_count/person_count/event_duration_ms/occupied_duration_ms（整数）。按模型、区域、类型、窗口起点排序。new_event_counts 按模型/类型提供起点在查询范围内的去重新增次数，用于与旧逻辑比较。

summary 固定整数：received、accepted、included、excluded、duplicates、rejected。accepted 是去重后的合法事件数，含完全在查询范围外的事件；included+excluded=accepted；received=accepted+duplicates+rejected。诊断 rejected 每项包含 input_index（整数）、event_id（字符串或 null）、code（稳定字符串），不回显任意原始敏感 payload。

影子报告固定包含 schema_version、sequence、status、candidate、comparison、error；status 为 completed/failed/skipped。comparison 包含 matched 与逐模型/类型差异，每项给出 legacy_count、shadow_count、delta=shadow_count-legacy_count。影子错误不给出虚假 matched=true；candidate 可为 null。等待中的状态仅为运行期状态，正式导出在离线任务收集后进行。

标识缺失/空值、非整数时间（含 bool/NaN/Inf）、负时间、逆序区间、未知类型、冲突重复与未闭合事件均明确拒绝；query 错误直接报错，不返回貌似成功的空统计。批次大小和每次查询的时间跨度有限制，避免超长事件生成无界窗口。

## 构造场景与验收

1. 单区域单人、两区域、同区域多人重叠，区分累计时长与并集时长。
2. 两种模型版本使用相同人物/事件标识，独立聚合与比较。
3. 跨 5 分钟边界、恰好右端结束、瞬时事件、query 外/部分相交、空批次。
4. 完全重复、同键冲突、非法标识、NaN/Inf/bool、逆序区间、开放事件；逐项断言诊断码及输入行数核算。
5. 真实 AlertEpisodeTracker 的连续告警不重复计数、起身/正常后复发、短缺失容忍与超过 4 秒重计、陌生人 pending/known 边界。构造事件与这些帧逐项对应，比较次数。
6. 有意制造的旧/新不一致必须产生准确 delta；不能只覆盖 matched=true。
7. 影子抛错、修改输入、比较器或记录器异常、队列满：原返回值及原输入行为保持；原逻辑自身失败不被遮蔽。使用可控线程同步验证，无随机休眠。
8. 相同构造输入重复运行得到相同 JSON 字节；字段集合及类型逐项断言，数据源可替换成另一个内存源，不修改计算函数。

新增 src/region_aggregation.py、src/shadow_mode.py、构造数据与一键验收工具及根目录 unittest；保留既有模块原样。先验证失败测试，再实现，完成后独立审查、专项与全套回归，记录已有失败，仅推送 zy。

## 运行与验收结果

```powershell
python3.11 tools/run_shadow_scenarios.py --output .tmp/shadow-regions.json
python3.11 -m unittest test_region_aggregation test_shadow_mode test_shadow_scenarios -v
```

Python 3.11+，仅标准库；若本机命令为 python，可直接替换命令名。工具向 stdout 和 UTF-8 文件输出相同 JSON，失败返回非零码；刻意差异用例以预期 matched=false/delta 验收，不能把“存在预期差异”当作整个工具失败。17 个场景、109 项检查及 26 项专项测试通过。全套回归 232 项无失败，18 项因设备/MQTT环境跳过。

实际限制：查询跨度最多 24 小时，事件/帧每批最多 10000 条，单帧 alerts 最多 1000 条，事件切窗片段总数最多 100000。超过限制明确报错；影子错误不会改变原逻辑的返回值。影子正式报告按 sequence 排序；运行中 reports() 可看到 pending，正式导出前应 drain()。drain(timeout=...) 超时明确抛错，不能强制终止任意不合作的 Python 线程；close() 等待工作完成，因此需由调用方在批次结束或停机时显式管理。

```python
from src.shadow_fixtures import evaluate_source

class NextSource:
    def read_batch(self):
        return {'query': {'start_ms': 0, 'end_ms': 300000},
                'frames': [], 'events': []}

result = evaluate_source(NextSource())
```

真实源需提供已归一化的双视图数据；当前没有连接真实源，也不将手工构造事件声称为真实帧归一化算法。相同去重键比较规范的七个核心字段，额外字段不参与聚合。

当前无必须由 App 负责人处理的事项。另已自行修复前述 App JSON 字段保留配置，只补齐 recognitionStatus、photoCount、hint，对应既有回归由失败转为通过；未改人脸业务逻辑。App Release 包与真机行为不属于本次离线验收，未重新打包或做真机验证。
