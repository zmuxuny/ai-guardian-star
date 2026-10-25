# caringSystem

- OpenWolf 为按需项目索引。陌生模块或跨项目调查时读 `.wolf/anatomy.md`；历史决策影响任务时读 `.wolf/cerebrum.md`。已知文件/符号直接定向搜索。需要维护 OpenWolf 时按 `.wolf/OPENWOLF.md` 的 Slim Protocol 执行。
- 构建、签名、HAP/APP 交付按 `DEVECO_BUILD.md` 的相关章节；构建成功不代表设备/API 验收成功。
- 保留无关改动，不顺手重构；优先复用现有代码。缺少影响结果的关键决策时询问，常规实现选择自行处理。
- 修复以实际复现和相应验证为准；已通过且代码未变的检查不重复执行。
- 设计类任务默认使用项目内 `$impeccable` 技能；涉及界面设计、重设计、评审、可访问性、布局、视觉层级或交互体验时，先按该技能流程读取项目上下文并完成设计检查。

## AI 协作（Codex / DeepSeek）

- 开工先读 `docs/修改记录/协作/README.md`、`TASKS.md` 和对方 `STATUS` 的最新一条；收工前更新自己的 `STATUS` 与 `TASKS`。
- 未验证代码放 `wip/<agent>-<date>` 分支；`zy` 只接收已验证合并和协作文档。当前阶段只做本地提交，由用户统一 push。
- 记录写分支、提交 SHA、影响文件、验证结果、未验证项、下一步；不贴大段代码，不写密钥和个人信息。
- 各自使用独立 worktree，禁止在对方工作区提交或覆盖未提交改动；不要用 `git add -A`。
- 一次逻辑改动一次 commit，提交信息用完整中文，并加 `AI-Agent: <agent>`。
