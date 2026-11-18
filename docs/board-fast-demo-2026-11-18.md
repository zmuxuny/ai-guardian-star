# 久坐关怀：快速演示档

当前以功能演示为主。显式FastDemo设置：静止确认2秒、有效计时2秒首提醒、再3秒升级、再5秒重复；因此识别稳定后约4秒首提醒、7秒升级、12秒第二次升级提醒。L0一次、L1最多两次。小幅人体框抖动不会重置，明显移动仍清零；移动后只需2秒重新确认静止，不再等原来的10秒。

任何已识别人员分别计时，不要求唯一人员。测试auto从当前已识别角色选计时最长者，也可指定Role；选定后固定角色。无识别身份时不绑定旧人物。

工具用独立shadow配置、独立DB、sync=false和临时systemd drop-in启动；test-profile.json保存具体参数。FastDemo通过既有AI_GUARDIAN_VLM_LONG_SIT_SECONDS=2同时缩短原久坐判定和care输入确认，这是演示期的临时覆盖。临时配置按精确所有权识别，RecoverOff删除该覆盖并恢复原服务设置；其他环境行不接受。默认验收15/10/10秒、正式Care Config1800/300/300秒保留。

PowerShell7启动入口由Codex选择新Session和独立OutputDirectory：

```powershell
& ./tools/Invoke-BoardValidation.ps1 -Action StartShadow -FastDemo -Session $newSession -OutputDirectory $demoOutput
```

上述变量需设置为本轮路径，不是可直接粘贴的完整命令。后续由Codex实际RecoverOff并Probe，不依赖30分钟保护推测已恢复。shadow记录模拟提醒，不驱动新关怀音频或新消息同步；该模式是演示触发链路，不冒充完整验收。

验证：Python3.9专项49项和独立审查通过；真实StationaryTimer与CareRuntime虚拟时间链路证明4/7/12秒提醒、小幅抖动容忍、大移动清零和人员隔离。此前5/5/10秒版曾上板触发zy=P2，并取得起身272秒归零证据；原始历史记录保留在board-retest-evidence-2026-11-18.md，不改写为本版现场结果。

上板核对：实际进程静止阈值2秒、machine 2/3/5已读回，原Python3.9.2隔离演示场景通过。22:25最终off/服务/摄像头及28指纹通过，临时环境已与备份原值一致；新真人演示留待下次，无需用户继续等待。
