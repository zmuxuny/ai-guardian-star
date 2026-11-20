# Issue23 优先级②板端本地交付证据

日期：2026-11-20。分支：`wip/codex-20261120-personal-baseline`。基线：`10fa28a`。
功能提交：`d0e522a`、`5da0f37`、`32c35fa`；独立审查修复：`f640bce`。

## 已实现与已证明

- posture_v1归一化特征、反馈正负样本与修改/撤销/恢复、无告警时段固定直方图、只读静态匹配报告；默认关闭。
- 实际HistoryStore/EventClipCache组件中，原录像事件ID贯穿特征与反馈；shadow不生成第二个可反馈ID，live继续复用原引用。
- 人物/模型/模式/相机版本隔离；旧schema4升级备份及失败回滚；特征不进入outbox或公开stats。
- 后台有界队列；SQLite慢写盘复现RED约1.66秒阻塞，修复后同用例要求检测入口在0.3秒内返回附加关怀失败，原alerts保持不变；此时间是测试上限，不代表硬实时保证。
- 无观测、采集关闭及重启后的过期清理；人物删除等待在途写入、移除排队特征并清除线程局部快照；关停未排空返回False并输出故障码，支持重试。

## 测试证据

独立环境：当前worktree的`.tmp/personal-env`，仅安装本机测试依赖，不修改设备或生产环境。

1. 新专项最终36项通过，覆盖纯特征、事务存储、实际事件接线、认证、队列/写锁/生命周期及打包完整性。
2. 修复后的组合回归：223项运行，222通过、1跳过，无失败；覆盖新专项与原local store、delivery、weekly、shadow、identity、runtime、release、validation、audio、restart、web、event cache及shutdown。
3. 最后新增服务关停提示后：新专项、server shutdown、care web、board validation、care release相关入口回归86项运行，85通过、1跳过，无失败。
4. 两轮中的跳过均为同一POSIX/uvicorn停机测试，在Windows不适用。FastAPI测试环境存在上游httpx弃用提示，不影响断言。
5. 69个Python文件通过Python3.9语法规则检查及本机编译；检查解释器实际为Python3.14.6，未冒充原板3.9运行。
6. 独立平铺目录导入个人常态模块并执行事件反馈通过；打包清单包含3个新增模块和迁移005。`git diff --check`通过。

组合命令可查本次协作记录和计划；主要命令为`python -m unittest`加载对应模块，最终入口命令加载`test_personal_baseline tests.test_server_shutdown tests.test_care_web test_board_validation test_care_release`。临时原始测试输出在本worktree的`.tmp/personal-*.txt`，不进入Git。

## 独立审查处理

3项重要问题：后台SQLite锁拖慢检测、无新观测TTL缺入口、trusted附原因遗漏正样本，全部建立失败用例后修复。
同时修复2项删除/关停边界：清除内存排队快照，传播关停超时并支持重试；没有遗留待处理的小问题。

实现取舍：帧尺寸从现有服务入口传入，保留设备检测器源文件；关闭采集仍维护既有样本的撤销资格；锁争用时宁可跳过附加关怀帧，不等待可选采集写盘。这可能推迟关怀状态更新或损失观测，但不会把跳过当成功采集。

## 尚未验证

没有push、合并到zy或部署；未连接板端、未启用live或新开关。
未验证原板新代码编译/运行、真实App/云端反馈、真实录像编码播放、真人姿态准确率、现场身份专项和长期运行。
当前真实输入缺少完整静止/回应/雷达保护证据，所以真实影子建议预计为0。36项专项中的完整保护条件为模拟；静态建议数不等同实际少报数或召回率。

配置、操作与schema5回退约束见[运行说明](personal-baseline-runbook.md)。下一步在设备现状指纹和私有备份核对后，按隔离shadow逐项上板验收；App继续Issue25。
