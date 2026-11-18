# 开发板复连即验：AF-01 准备包

事实截止：2026-11-18。本轮仅在 Windows 离线准备，没有 SSH、部署、重启或现场动作。业务基线为已部署修复 `0ca3f38`，不再安装一次。11月17日19:38的 off/active/摄像头正常是历史记录，连板后重新 Probe。

## 已备入口

独立工作区：`C:\Users\Yang\.codex\worktrees\board-retest-ready-20261118\zhihuixing`。

入口：`tools/Invoke-BoardValidation.ps1`；已准备包和编译报告位于本工作区 `.tmp/board-ready-kit/`。新工具只进入隔离 staging，不覆盖板端应用。冻结的28文件部署指纹沿用 AF-01，禁止将 Windows 源文件哈希替代设备字节哈希。

本轮补齐重启评估：短停前必须同一真实事件已达到 L0=1、L1=2，避免正常升级被当作重复；恢复及观察结束都须同一事件、两级次数不变、计时不回退。同一角色必须实际被识别，观察不得有采样错误。记录停服前/恢复首样本/最终样本的单调时间，恢复间断短停为5至不足120秒、长停为至少120秒。时间、身份或观察证据不足返回 INCOMPLETE，不推进门禁。

提醒：输入仍是静止代理；站着不动也可能计时。本次验证真实移动与恢复边界，不证明已具备坐姿分类。

## 连上后第一组命令

由 Codex 执行，现场人员仅配合动作。PowerShell 7 中先定义一次：

```powershell
$readyRoot = 'C:\Users\Yang\.codex\worktrees\board-retest-ready-20261118\zhihuixing'
$boardCheck = Join-Path $readyRoot 'tools/Invoke-BoardValidation.ps1'
$runTag = Get-Date -Format 'yyyyMMdd-HHmmss'
$boardCommon = @{
    Session = "/root/guardian-care-staging/care-validation-$runTag-af01"
    OutputDirectory = Join-Path $readyRoot '.tmp/board-ready-kit'
}
# 如已确认密钥路径，可在 boardCommon 加 IdentityFile；不显示密钥正文。
function Invoke-ReadyBoard([hashtable]$StepArgs) {
    & $boardCheck @boardCommon @StepArgs
    if ($LASTEXITCODE -ne 0) { throw '本项未通过；停止后续操作，保留证据并收尾。' }
}
Invoke-ReadyBoard @{Action='Probe'}
```

本地 Prepare 已做完，现场无需重新编译/打包。若源码或说明发生变化才重新 Prepare。新会话名每次生成，不复用昨日或已收尾会话。

Probe 必须实际通过：28指纹、原服务解释器/架构、时差、摄像头与视频检查；还须 care_mode=off、care_config_present=false。不符即停，先定位差异，不自动改基线、依赖或服务。发现旧会话/外来 drop-in 先审查归属，不能用新会话删除旧配置。

```powershell
Invoke-ReadyBoard @{Action='BaselineResources';Seconds=30}
Invoke-ReadyBoard @{Action='StartShadow'}
```

StartShadow 会先备份，再确认自动恢复看门狗，然后启用独立数据库、独立 model_version 的 shadow；不运行 live、真实关怀播报或新关怀消息同步。30分钟看门狗仅为兜底。后续操作必须置于 try/finally，finally 执行下方收尾；每个现场动作分别执行，不把整段动作命令无人值守连跑。

## 现场逐项执行

1. **坐稳与短重启**：现场测试人员面部可识别且持续坐稳，不要求画面只有一位登记人员。auto从当前已识别人员中选择计时最长者；可用本会话实际Role指定测试对象。实际执行动作后才 Mark。Observe 50秒后核对该人员同一事件 counts=L0:1/L1:2；未到上限则继续真实观察，不改JSON。

```powershell
Invoke-ReadyBoard @{Action='Mark';Phase='seated';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=50}
# 核对实际计时/事件/次数后执行；整个短停及恢复期间现场保持原位。
Invoke-ReadyBoard @{Action='Restart';RestartKind='short'}
```

检查 restart-short.json：status=PASS、timing/visible_actor=true、observation=PASS、event_and_counts=true，恢复间断小于120秒，两级次数不增加。服务起来本身不算通过。身份丢失、采样失败或超时为未完成，现场条件重建后用新会话复验。

2. **真实起身移动**：人实际起身且明显移动，在仍能识别同一人的位置观察清零。只站着不动不能证明移动分支。移动后才 Mark，检查其角色 IDLE/0秒；别人 IDLE 不算该人员通过。

```powershell
Invoke-ReadyBoard @{Action='Mark';Phase='standing';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=20}
```

3. **长停恢复**：重新坐稳、重新产生正计时及活动事件，再长停130秒。先确认现场可以一直留在画面；长停恢复需新事件且计时重新开始。

```powershell
Invoke-ReadyBoard @{Action='Mark';Phase='seated';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=50}
Invoke-ReadyBoard @{Action='Restart';RestartKind='long'}
```

检查 restart-long.json：真实间断至少120秒，最终有新事件及正计时。仅服务重启与整板断电恢复是不同验收项。

4. **遮挡与身份波动**：先有正计时的活动事件，再实际短遮挡，观察冻结；恢复可识别后应延续事件。另一次持续离开/遮挡超过120秒验证清零。每个具体动作的证据绑定对应人员，其他识别人员仍独立计时；可用本会话实际 recognized_roles 的 P编号指定Role，不能套用昨日P2。

```powershell
# 每项命令前均须现场真实做对应动作。
Invoke-ReadyBoard @{Action='Mark';Phase='cover';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=20}
# 现场恢复识别并重新观察正计时。
Invoke-ReadyBoard @{Action='Mark';Phase='seated';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=30}
# 现场人员离开画面，需记录离开起点与足够时间的原始证据。
Invoke-ReadyBoard @{Action='Mark';Phase='leave';ConfirmedAction=$true}
Invoke-ReadyBoard @{Action='Observe';Seconds=140}
```

leave 自动评估要求证据中仍能看到离开初期尚未清零的状态，以及满120秒后的清零；若首样本就已IDLE，不能凭140秒命令补造通过。身份短波动要核对同人恢复/跨人隔离，单独记录，不凭事件数量推断原因。

5. **自然静默**：仅在板端真实本地时间22:00–07:00用新的 `-Quiet` shadow会话验证；先收尾当前会话。检查 quiet=true、pending_level存在且没有播报。不改系统时钟，不在非静默时间填写PASS。安静会话也须实际坐稳并确认对应角色；证据汇总可用 Assess2 的 IncludeSession。

## 结果与异常收尾

按每个结果分别判定。短重启PASS只代表 AF-01 的这一项；完整第2步还包含上述其他现场项及静默。Assess2 返回 INCOMPLETE/FAIL 时不执行 CompleteStep 或第3–6步；App #25、真实音频、整板断电和长期稳定性仍是后续任务。

结束、用户无法继续或异常时，执行顺序如下；即使下载失败也要尝试 RecoverOff。实际操作中用嵌套 finally 保证最后 Probe，保留各自错误，不用关闭终端代替收尾。

```powershell
try {
    # 各现场项完成后再评估；INCOMPLETE 会抛错，仍进入 finally。
    Invoke-ReadyBoard @{Action='Assess2'}
} finally {
    try {
        Invoke-ReadyBoard @{Action='DownloadEvidence'}
    } finally {
        try { Invoke-ReadyBoard @{Action='RecoverOff'} }
        finally { Invoke-ReadyBoard @{Action='Probe'} }
    }
}
```

这是结束段；从 StartShadow 到结束段的所有在线动作也须由操作者放在同一受保护的 try/finally 范围中。不能等全部现场步骤完成后才建立收尾保护。最后实际确认 active、off、care_config_present=false、28指纹和摄像头；恢复失败记为阻塞并立即排查，不能宣布已恢复。

若停服出现 timeout/SSH中断，不盲目重复 Restart，也不自动 reset-failed。先回读服务 ActiveState/Result/MainPID/ControlGroup 和部署指纹；现有原退出超时归 T-20261117-04。只有证实无进程、控制组空、文件未变后再决定恢复；本包未修改服务退出路径。断连时不得宣称已off，待复连读回并收尾。

本机下载目录：`.tmp/board-ready-kit/private-evidence/`。本轮仅使用一个快测会话；换会话先把已下载证据复制到独立私有目录，避免同名文件覆盖。完整原件保留各自板端session。token/config/roles/DB/原始音视频不在公开交付中，证据也不提交Git。

## 离线完成证明

已验证：Python3.9.25下工具/AF-01/发布回退45项通过；带既有本地依赖的Python3.11下周报14项通过；PowerShell入口语法解析通过。裸3.9环境不带FastAPI，周报API用例在3.11既有依赖环境验证，不为此安装或升级板端依赖。

Prepare 的JSON和Python3.9编译报告、专项结果及包校验记录放 `.tmp/board-ready-kit/`，供下一次直接检查。包包含 manifest、执行器、PowerShell入口、迁移SQL、隔离测试及本说明。独立解包核验每项SHA256后运行工具/AF-01/回退/周报专项。离线结果不能替代真实输入和设备验收。
