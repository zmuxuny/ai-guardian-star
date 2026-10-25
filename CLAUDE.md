# caringSystem

- OpenWolf 为按需项目索引。陌生模块或跨项目调查时读 `.wolf/anatomy.md`；历史决策影响任务时读 `.wolf/cerebrum.md`。已知文件/符号直接定向搜索。需要维护 OpenWolf 时按 `.wolf/OPENWOLF.md` 的 Slim Protocol 执行。
- 构建、签名、HAP/APP 交付按 `DEVECO_BUILD.md` 的相关章节；构建成功不代表设备/API 验收成功。
- 保留无关改动，不顺手重构；优先复用现有代码。缺少影响结果的关键决策时询问，常规实现选择自行处理。
- 修复以实际复现和相应验证为准；已通过且代码未变的检查不重复执行。
- AI 协作按 `docs/修改记录/协作/README.md` 执行：开工读 `TASKS.md` 与对方 `STATUS` 最新一条，收工更新自己的 `STATUS`；未验证代码走 WIP 分支，不用 `git add -A`。

## 环境与权限（用户长期设定，2026-10-25）

- 仓库 `https://github.com/zmuxuny/ai-guardian-star`。`zy` 是用户（硬件负责人）维护的开发分支；`feature/hjb-ascend-voice` 是旧硬件分支，末次提交 2025-12-18，已包含在 `zy` 中。**未经用户授权不得合并 `main` 或其他分支到 `zy`。**
- 推送统一由 Codex 执行；DeepSeek 只做本地提交，不 push。
- 生产服务器：阿里云 `47.108.167.0:22`，root，应用 `/opt/wenxin/app`（部署副本，非 git 仓库），服务 `wenxin.service`。
- 开发板：`47.108.167.0:6022`，root，代码 `/root/ai_guardian`（部署副本，非 git 仓库），服务 `guardian-board.service`。
- 两台机器的私钥只保存在操作机本地，不写入仓库、不粘贴进记录。
- 本机到 github.com:443 被阻断：git 需经 `ssh -N -D 127.0.0.1:1080 root@47.108.167.0` 隧道，并设 `http.sslBackend=openssl`；该配置已写入本仓库 `.git/config`。
- 交付顺序：先备份（本地回退点/远端备份目录）→ 最小修改 → 本地验证 → 由 Codex push → 再部署服务器或开发板。
