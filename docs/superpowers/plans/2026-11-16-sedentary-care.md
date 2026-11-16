# 久坐关怀状态机 Implementation Plan

**Goal:** 实现不依赖硬件的可复用状态机与一键离线场景验收。

**Architecture:** Python 标准库，可信姿态、输入可靠性和提醒阶段分别保存，注入虚拟时钟。确定性截止项调度支持任意时间步长；模拟接口记录实际应播报内容。

**Spec:** ../specs/2026-11-16-sedentary-care-design.md

**Global Constraints:** 当前 feature/jyx-home；不修改检测入口；不增加依赖；不连接设备/服务；只暂存本次文件；已有基线备份。

用户已要求继续实现；在当前会话直接执行，不另行引入设计确认轮次。

## 实现次序

1. 在 test_sedentary_care.py 写行为断言并执行，确认缺少模块导致预期失败。覆盖默认触发点、暂停/失效、回应、静默、非法时间与事件。
2. 新增 src/sedentary_care.py：Config、VirtualClock、RecordingSpeaker、CareMachine。接口 handle(event)、snapshot()、export()，截止项先于/等于事件的规则见设计。
3. 在 test_sedentary_scenarios.py 先验证运行器不存在/行为缺失，再新增 tools/run_sedentary_scenarios.py。场景使用显式周期 SIT，输出每个场景的快照、完整轨迹、播报和断言结果；失败退出非零。
4. 更新规格中的完整事件矩阵、原因分类及命令。执行专项与根目录全套 unittest、场景导出、diff 检查、OpenWolf 扫描。按验证结果提交并推送。

## 重点复查

- 同刻有效坐姿续报可刷新观测；同刻起身/回应/不可靠观测优先于播报。
- 遮挡或其他不可靠状态共用暂停机制，原因不同，默认失效期限相同且可配置；重复异常不能续命。
- TARGET_CHANGED 清空旧人的状态；拒绝不再提醒，稍后提醒/回应不重置次数。
- 静默内不消耗次数，不累计补发队列；有待提醒时恢复可靠输入也要检查静默。
- 事件/配置错误必须在修改状态前报错；导出的数据可直接 JSON 序列化。

## 执行记录

work_state_read/write 未出现在本会话可用工具目录，无法调用；不使用替代的内置待办工具。

## 验证结果（2026-11-16）

专项 22 项通过；离线场景 199 个通过，涵盖 156 个状态/事件组合。场景 JSON 的终端输出与文件导出一致，可重复运行得到相同结果。

项目全套 unittest：261 项，OK，18 项因设备/MQTT条件跳过。首次运行缺少 Flask/PyMySQL；通过在忽略的 `.tmp/sedentary-test-deps` 安装项目已有固定依赖并设置进程级 PYTHONPATH 完成回归，未修改系统 Python、依赖文件或业务代码。

独立只读审查无须修复项；补充验证各提醒阶段暂停恢复、待 L1 跨静默终点恢复。

`openwolf scan` 已尝试，当前环境未安装或 PATH 中无该命令，扫描未执行。无设备部署、无真实音频输出。
