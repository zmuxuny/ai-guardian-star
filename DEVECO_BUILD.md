# DevEco Studio 构建 HAP / APP 说明

> 本项目没有 `HPP` 包。日常口头说的 “HPP” 按 `HAP` 理解。

## 1. 两种产物

- `HAP`：HarmonyOS 模块安装包，用于模拟器、真机安装和测试。
- `APP`：包含一个或多个 HAP 的 App Pack，用于提交 AppGallery Connect，不能直接安装到设备。

本项目当前只有一个模块：`entry@default`；产品为 `default`；常用构建模式为 `release`。

## 2. 当前机器与项目配置

- 项目目录：`E:\caringSystem`
- DevEco Studio：`E:\DevEco Studio`
- Hvigor：`E:\DevEco Studio\tools\hvigor\bin\hvigorw.bat`
- Hvigor 版本：`6.24.3`
- SDK：`E:\DevEco Studio\sdk`
- HarmonyOS SDK：`6.1.0(23)` / API 23
- 应用版本：读取 `AppScope/app.json5` 中的 `versionName` 和 `versionCode`
- 签名：读取根目录 `build-profile.json5` 的 `default` 配置

换电脑时只替换 DevEco、项目和签名材料路径，不要改构建任务名。签名密码、私钥、Profile、证书内容禁止输出到聊天、日志或提交到 Git。

## 3. DevEco Studio 图形界面流程

1. 用 DevEco Studio 打开 `E:\caringSystem`。
2. 执行 `File > Sync and Refresh Project`，等待同步成功。
3. 确认 Product 为 `default`，Build Mode 为 `release`，签名配置无红色报错。
4. 构建 HAP：`Build > Build Hap(s)/APP(s) > Build Hap(s)`。
5. 构建 APP：`Build > Build Hap(s)/APP(s) > Build APP(s)`。
6. 在 Build 输出看到 `BUILD SUCCESSFUL` 后，再检查实际产物文件。

菜单文字可能随 DevEco Studio 小版本略变；认准 `Build Hap(s)` 和 `Build APP(s)`。

## 4. Claude Code / PowerShell 构建流程

全部命令使用 PowerShell。不要嵌套 `powershell -Command`，不要调用系统 Node.js；始终使用 DevEco Studio 自带的 Node、OHPM 和 Hvigor。

### 4.1 初始化当前终端

以下整块原样粘贴：

```powershell
$DevEcoHome = 'E:\DevEco Studio'
$ProjectRoot = 'E:\caringSystem'
$Node = Join-Path $DevEcoHome 'tools\node\node.exe'
$Ohpm = Join-Path $DevEcoHome 'tools\ohpm\bin\pm-cli.js'
$Hvigor = Join-Path $DevEcoHome 'tools\hvigor\bin\hvigorw.bat'
$env:DEVECO_SDK_HOME = Join-Path $DevEcoHome 'sdk'

foreach ($Tool in @($Node, $Ohpm, $Hvigor, $env:DEVECO_SDK_HOME)) {
  if (-not (Test-Path -LiteralPath $Tool)) { throw "缺少构建工具或 SDK：$Tool" }
}

Set-Location -LiteralPath $ProjectRoot
```

预期：无输出、无报错。若提示路径不存在，停止构建，先修正 `$DevEcoHome` 或 `$ProjectRoot`。

### 4.2 安装或同步依赖

首次构建、切换分支、修改 `oh-package*.json5` 后执行。以下整块原样粘贴：

```powershell
& $Node $Ohpm install --all
if ($LASTEXITCODE -ne 0) { throw "OHPM 依赖安装失败：$LASTEXITCODE" }
```

普通源码改动且依赖未变时可跳过，避免无意义改写锁文件。

### 4.3 构建 Release HAP

以下整块原样粘贴：

```powershell
& $Hvigor --mode module `
  -p product=default `
  -p module=entry@default `
  -p buildMode=release `
  assembleHap --no-daemon
if ($LASTEXITCODE -ne 0) { throw "Release HAP 构建失败：$LASTEXITCODE" }
```

常见产物目录：`entry\build\default\outputs\default\`。

### 4.4 构建 Release APP

以下整块原样粘贴：

```powershell
& $Hvigor --mode project `
  -p product=default `
  -p buildMode=release `
  assembleApp --no-daemon
if ($LASTEXITCODE -ne 0) { throw "Release APP 构建失败：$LASTEXITCODE" }
```

APP 通常位于项目级 `build\outputs\` 下。不要依赖固定文件名，以实际搜索结果为准。

### 4.5 检查产物

构建 HAP 后原样粘贴：

```powershell
$Artifacts = Get-ChildItem -LiteralPath '.\entry\build\default\outputs\default' -File -Filter '*.hap'
if (-not $Artifacts) { throw 'Hvigor 已结束，但未找到 HAP 产物' }
$Artifacts | Select-Object FullName, Length, LastWriteTime
$Artifacts | Get-FileHash -Algorithm SHA256 | Select-Object Path, Hash
```

构建 APP 后原样粘贴：

```powershell
$Artifacts = Get-ChildItem -LiteralPath '.\build\outputs' -Recurse -File -Filter '*.app'
if (-not $Artifacts) { throw 'Hvigor 已结束，但未找到 APP 产物' }
$Artifacts | Select-Object FullName, Length, LastWriteTime
$Artifacts | Get-FileHash -Algorithm SHA256 | Select-Object Path, Hash
```

预期：至少找到一个非零大小文件，并输出 SHA-256。没有产物时不得只凭 `BUILD SUCCESSFUL` 宣称完成。

## 5. 什么时候清理

不要每次先 `clean`。只有缓存异常、切换 SDK 后出现无法解释的旧产物或增量编译问题时执行：

```powershell
& $Hvigor clean --no-daemon
if ($LASTEXITCODE -ne 0) { throw "Hvigor clean 失败：$LASTEXITCODE" }
```

如果改过 `DEVECO_SDK_HOME`、Node 或 Hvigor 路径且守护进程仍报旧环境，执行：

```powershell
& $Hvigor --stop-daemon
```

然后重新初始化终端并构建。

## 6. 交付前检查

1. 确认 `AppScope/app.json5` 的 `versionCode` 已递增，`versionName` 符合本次发布。
2. 确认服务地址和环境配置指向目标环境。
3. 确认使用 `release` 和正确签名，不提交本机签名路径或密钥。
4. 构建后报告完整产物路径、文件大小、修改时间和 SHA-256。
5. HAP 构建成功不等于真机验收；需要交付测试时，还要安装、启动并走关键流程。
6. APP 构建成功不等于上架通过；需要上架时，还要以 AppGallery Connect 的上传校验结果为准。

## 7. Claude Code 执行规则

- 用户说“构建 HPP”时，先说明应为 HAP，再按 HAP 流程执行。
- 优先使用第 4 节 PowerShell 命令；GUI 仅用于签名配置、设备运行或用户明确要求时。
- 构建前先看 `git status`，不得覆盖或清理用户现有改动。
- 不自动升级 DevEco Studio、SDK、Hvigor 或依赖。
- 不显示 `build-profile.json5` 中的密码和签名材料。
- 失败时保留最短关键错误；先修环境、签名或依赖根因，不反复盲目 `clean`。
- 只有找到产物并核对哈希后，才可说“包已构建”；真机/上架未验证必须明确写出。
