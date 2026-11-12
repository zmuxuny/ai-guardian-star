# caringSystem（AI 守护星）项目规则

> Claude（经 `CLAUDE.md` 导入）和 Codex 共用这一份文件。改约定只改这里。

## 工作原则

- 保留无关改动，不顺手重构；优先复用现有代码。缺少影响结果的关键决策时询问，常规实现选择自行处理。
- 修复以实际复现和相应验证为准；已通过且代码未变的检查不重复执行。
- 设计类任务（界面设计、重设计、评审、可访问性、布局、视觉层级、交互体验）先走 `impeccable` 技能流程。
- OpenWolf 是按需索引：陌生模块读 `.wolf/anatomy.md`，历史决策读 `.wolf/cerebrum.md`；已知文件直接定向搜索。只在用户纠正或有非显而易见的项目约定时写 `cerebrum.md`，确认根因的产品缺陷才写 `buglog.json`，结构性增删文件后跑 `openwolf scan`。

## 文件夹分工

- 本仓库只放应用代码及其配套（App、后端、开发板、部署脚本、测试、技术文档）。
- 比赛用的资料（PPT、计划书、申报书、讲稿、视频、效果图、报名表、奖项）一律放本机的比赛资料目录（路径见 `CLAUDE.local.md`），不放进本仓库；生成到别处的成品也移过去。

## 分支、提交与推送

- 仓库 `https://github.com/zmuxuny/ai-guardian-star`（公开）。用户（简沅晞）的工作分支是 `feature/jyx-home`，默认在它上面改；不动 `main`，不新建分支，除非用户要求。
- `zy` 是硬件负责人维护的开发分支；`feature/hjb-ascend-voice` 是旧硬件分支（末次提交 2025-12-18，已含在 `zy` 中）。**未经用户授权不得合并 `main` 或其他分支到 `zy`。**
- 谁改谁推（2026-11-05 起）：验证通过后自己 commit 并 push，不积攒；推送前先 `git fetch`，远端有新提交先合并。不 force push 共享分支。
- 提交：Conventional Commits，类型英文、描述中文，正文写“为什么”；一次逻辑改动一次提交；末尾带 AI 署名行（Claude 用 `Co-Authored-By`，Codex 用 `AI-Agent: codex`）。
- 只 `git add` 本次相关文件，**不用 `git add -A`**；工作区里别人的未提交改动不带进提交、不覆盖。
- 交付顺序：先备份（本地回退点 / 远端备份目录）→ 最小修改 → 本地验证 → push → 再部署服务器或开发板。

## 安全（公开仓库）

- 不提交、不写进文档或日志：密钥、token、短信码、管理密码、签名材料（密码、私钥、Profile、证书）、手机号、人脸原图、日志原文、本机绝对路径。引用凭据只写“见设备上的私有配置”。
- 不提交 HAP/APP、视频、数据库、`local.properties`、`.env`；大于 50 MB 的文件先问。
- 云端凭据只通过服务器环境变量注入，不写进 App。

## 环境（用户长期设定）

- 生产服务器：阿里云 `47.108.167.0:22`，root，应用 `/opt/wenxin/app`（部署副本，非 git 仓库），服务 `wenxin.service`。
- 开发板：`47.108.167.0:6022`（经云服务器 frp 转发），root，代码 `/root/ai_guardian`（部署副本，非 git 仓库），服务 `guardian-board.service`。
- 两台机器的私钥只保存在操作机本地，不写入仓库、不粘贴进记录。
- 本机到 github.com:443 可能被阻断：不通时经 `ssh -N -D 127.0.0.1:1080 root@47.108.167.0` 隧道，并设 `http.sslBackend=openssl`（已写入本仓库 `.git/config`）。
- 后端测试：`python -m unittest discover -v`。

## HarmonyOS 构建（SDK 26.0.0）

- 目标与最低兼容版本均为 `26.0.0`（API 26，2026-11-05 用户升级）；本机 SDK 为 HarmonyOS 26.0.0.105 Release。版本号读 `AppScope/app.json5`，签名读根目录 `build-profile.json5` 的 `default` 配置。
- 只有一个模块 `entry@default`，产品 `default`。HAP 用于装机测试；APP 是提交 AppGallery Connect 的包，不能直接装。口头说的“HPP”就是 HAP。
- 用 DevEco 自带的 Node、OHPM、Hvigor，不用系统 Node；不自动升级 DevEco、SDK、Hvigor 或依赖。本机 DevEco 在 `E:\DevEco Studio`，换电脑只换路径，不改任务名。

```powershell
$DevEco = 'E:\DevEco Studio'
$Node = "$DevEco\tools\node\node.exe"; $Ohpm = "$DevEco\tools\ohpm\bin\pm-cli.js"; $Hvigor = "$DevEco\tools\hvigor\bin\hvigorw.bat"
$env:DEVECO_SDK_HOME = "$DevEco\sdk"; $env:JAVA_HOME = "$DevEco\jbr"; $env:Path = "$env:JAVA_HOME\bin;$env:Path"

& $Node $Ohpm install --all        # 仅首次、切分支或改了 oh-package*.json5 时
& $Hvigor --mode module -p product=default -p module=entry@default -p buildMode=release assembleHap --no-daemon
& $Hvigor --mode project -p product=default -p buildMode=release assembleApp --no-daemon   # 需要 APP 时

Get-ChildItem .\entry\build\default\outputs\default -Filter *.hap | Get-FileHash -Algorithm SHA256
```

- 不每次 `clean`；只有缓存异常或切换 SDK 后出现旧产物时才 `& $Hvigor clean --no-daemon`，改过工具路径仍报旧环境时 `& $Hvigor --stop-daemon`。
- 看到产物文件并核对 SHA-256 才能说“包已构建”。构建成功不等于设备验收，模拟器通过不等于真机通过，APP 构建成功不等于上架通过；没验证的层级明说。
- 交付前：`versionCode` 已递增、服务地址指向目标环境、使用 release 和正确签名、报告产物路径、大小、时间和 SHA-256。

## 开发板模型

- 检测服务从 `src/ascend_main_other.py` 的候选列表里取第一个存在的 `best.om`，输入 640×640；`best1/3/4.om`、`model.om`、`*.onnx` 是备用或导出文件，默认不用。
- 替换模型前记录来源 checkpoint、ATC 转换命令和 CANN 版本、输入输出形状、目标 SoC，并在板端跑通一次推理；新模型验证前不删旧文件。
- 人脸登记的头姿复验候选模型是 6DRepNet `RepVGG-B1g2`（输入 1×3×224×224，MIT），目前只实现了探针和门限，模型未转换、未部署，权重不进 Git；详见 `docs/superpowers/plans/2026-11-03-face-enrollment-phase0-probe.md` Task 6。接入正式登记前须在板端完成转换与基准测试。
