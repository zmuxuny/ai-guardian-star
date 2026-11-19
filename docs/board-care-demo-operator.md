# 开发板关怀演示操作

在 Windows PowerShell 7 中执行以下命令。只操作开发板关怀演示，不需要打开网页。

```powershell
Set-Location 'C:\Users\Yang\.codex\worktrees\board-retest-ready-20261118\zhihuixing'
$demoKey = Join-Path $env:USERPROFILE '.ssh/orangepi_ed25519'

# 本地准备；更新工具代码后先重新执行一次，不连接开发板
pwsh.exe -NoProfile -File .\tools\Invoke-CareDemo.ps1 -Action Prepare

# 开启带语音的短时演示
pwsh.exe -NoProfile -File .\tools\Invoke-CareDemo.ps1 -Action Start -AudioDemo -IdentityFile $demoKey -SocksProxy '127.0.0.1:7890'

# 查询实际状态
pwsh.exe -NoProfile -File .\tools\Invoke-CareDemo.ps1 -Action Status -IdentityFile $demoKey

# 关闭并核实恢复 off
pwsh.exe -NoProfile -File .\tools\Invoke-CareDemo.ps1 -Action Stop -IdentityFile $demoKey
```

`127.0.0.1:7890` 必须已有本机 SOCKS 服务；脚本复用 Git for Windows 的 `connect.exe`。直连可用时，开启命令去掉 `-SocksProxy`；已有记录需要切回直连时显式传 `-SocksProxy ''`。路由保存在本地，后续查询/关闭自动复用，SSH 主机校验保持开启。

去掉 `-AudioDemo` 即为静默演示。演示复用原 FastDemo：稳定约 2 秒后累计，约 3 秒/5 秒触发提醒，使用隔离关怀配置和数据库，关闭云同步；仍需识别到登记人员并满足现有状态条件，不能保证坐下立刻播放。识别可见性的专项问题本轮暂缓。

脚本自动记录独占会话到 `.tmp/care-demo-operator/state.json`，不保存私钥或令牌。`Start` 先确认设备 off，再落盘 pending 后远程开启；重复开启会被拒绝。网络中断后保留此目录，在新 PowerShell 中重新运行 `Stop`，仍会针对原会话恢复。不要删目录或换工作区后直接当作已关闭。

只有服务、摄像头和基线检查通过，且实际模式为 off、无关怀配置时才返回 `CLOSED`。关闭报错或中断不能当作 off；继续使用原目录重试 `Stop`，必要时查询 `Status`。现有板端 30 分钟恢复看门狗保留，但不替代手动核实。

状态查询报告 `care_mode` 和 `care_config_present`；`PASS` 本身不等于 off，shadow 状态也可能通过环境检查。`RUNNING` 只表示模式已开启并通过检查，不表示已识别人脸或已播放语音。

本轮验收采用静默开启→查询→关闭→查询，不需要操作人员坐姿配合；听音和对讲打断沿用此前用户确认结果，不在此重复播放。
