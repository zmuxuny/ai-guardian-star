# AF-01 短重启恢复最小修复

基线df6d71c，WIP工作树独立实现；交付仅zy。用户已授权直接处理，不另等待设计确认。

问题：静止代理重建时is_sitting=False没有区分积累期与明确运动，CareRuntime把它转成NON_SIT，关闭恢复的事件，随后重新L0。不能通过延长120秒、忽略真实移动或修改输入数据使验收通过。

方案：StationaryTimer增加只读关怀判据方法及本次更新原因，原duration和告警行为不变；检测alerts附加care_observation；CareRuntime将warming/unreliable作为低置信冻结，moving仍明确NON_SIT，可靠still依旧使用原is_sitting。缺少新字段的旧调用契约保持原行为。

1. 先用真实CareRuntime/SQLite/VirtualClock写短重启后False暖机的红色回归；覆盖已耗尽提醒不重发、真实移动仍复位、长缺失仍120秒清零、身份丢失不移给他人。用真实StationaryTimer与生产检测AST打通组合输入测试。
2. 最小修改src/guardian_runtime.py、ascend_main_other.py、care_runtime.py；只添加关怀元数据，不改旧阈值/布尔输出、摄像头/SDK/模型/音视频。
3. Python3.9编译、相关专项和完整本机回归；独立审查。
4. 只读取实际板端三个文件，在原有备份之上新建独占备份和指纹；对设备独立增强的ascend_main_other只做审查过的局部插入，不复制整个src覆盖；隔离演练与原解释器回归后，按先push zy再部署规则最小发布，保持off。
5. 新建独立shadow会话，现场坐稳后短停5秒，检查同一事件ID、次数保持、旧视频与零线上outbox；若板离线或现场无法配合，保持off并明确上板未验。更新冻结指纹、回退说明与实际结果；不进入第3–6步，不开启live，不创建PR。
