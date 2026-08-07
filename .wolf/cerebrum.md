# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-07-15

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- **命令说明必须明确（2026-07-14）**：每组命令都要标明“原样粘贴”还是“需要自行替换”，说明逐行复制还是整块一次性复制，并给出预期结果及结果不符时的停止条件；密钥等敏感值必须与命令分开输入。
- **Codex 提交说明与署名（2026-07-14）**：后续提交使用完整中文标题和详细中文正文，正文列出改动文件或模块、具体行为变化和验证结果；末尾追加 `Co-Authored-By: Codex <noreply@openai.com>`。已推送历史不主动改写。
- **修复后及时推送**：修复一个问题、确认没问题之后，必须立即 commit + push，不要积攒多个修复再一次推送。
- **提交说明使用完整中文（2026-07-14）**：后续 Git commit/push 展示文字不用英文 `feat/fix/refactor`，改用完整中文说明，例如“新增：AI 助手开关与分析权限”。

## Key Learnings

- **Project:** caringSystem
- **Description:** <div align="center">
- **Layout.ets 已改为 Stack + visibility 常驻方案（2026-05-06）**：去掉 Tabs，每页用 Stack 叠加 + `visibility(Visible/None)` 控制显示，底部用自定义 Row。四页始终挂载不销毁，切 tab 保留聊天/输入/滚动状态。Tabs 层的 expandSafeArea + backgroundColor 冲突问题彻底消除，每页完全独立控制自己的顶部安全区
- **Record 页面模式（标准参考）**：GradientHeader 不带 expandSafeArea（仅用 topSafeHeight padding） + 圆角底部 + 紧随其后的卡片用负 margin（-4%）叠入渐变区域形成过渡桥
- mainpage：VideoArea 移出 Scroll 并用负 margin 叠入渐变头部，模仿 record 的 StatDashboard 过渡模式
- AiChat：新增 HealthOverview 卡片（复用 MqttManager 数据），置于 GradientHeader 与 Scroll 之间，用负 margin 叠入渐变
- person：StatDashboard 已有负 margin，仅需保持 GradientHeader 与 record 一致（无 expandSafeArea + borderRadius）
- **AI 助手设置（2026-07-14）**：按账号复用 `t_setting` 的 `saveSetting/loadSetting` 持久化；`AppStorage` 负责 Layout/person/AiChat 即时联动。默认开启 + `privacy`。关闭时只条件移除 AiChat 与底栏入口，个人页仍保持固定 index=3，避免切换索引。
- **AI 数据权限（2026-07-14）**：`full`=当前完整监护状态与精确最近记录，`privacy`=近7天脱敏统计，`basic`=不发送监护上下文。项目当前没有老人姓名/年龄资料源，不得拿监护人账号资料冒充。

- **Account Kit 实名边界（2026-07-15）**：华为账号普通登录只提供 UnionID/OpenID，不等于手机号实名。需要后台实名时，应申请 Account Kit 一键登录与 `phone` scope；客户端取得 Authorization Code，服务端换 Token 后再取可信手机号，并同时关联 UnionID 与手机号。`quickLoginAnonymousPhone` 仅为脱敏展示，不能作为后台实名凭据；无资格账号或用户拒绝授权时回退短信验证。
- **账号安全评估基线（2026-07-15）**：当前 ECS 账号/AI API 仍是公网明文 HTTP，且客户端本地 RDB 仍保存可直接比对的密码；在可信 HTTPS、服务端会话、短信/平台服务端手机号核验和本地 Keystore 迁移完成前，不得宣称实名整改或凭据保护已完成。社交平台登录只作便捷入口，必须映射内部不可变 `user_id` 并补手机号核验。
- **AI 风控隔离原则（2026-07-15）**：AI 网关必须先认证本应用用户，再按 `user_id` 检查账号/AI 状态、限流和内容安全；处罚默认只冻结违规用户的 AI 权限，不能通过共享上游 Token 把所有用户连坐。只保留最小化审计元数据，必要证据加密、限时、限权保存，不默认留存全部对话原文。

- **Claude-mem in Codex (2026-07-16):** Codex loads claude-mem 13.11.0 through plugin hooks plus the `mcp-search` MCP server. The live worker stores data under `C:\Users\16228\.claude-mem`, scopes observations to `caringSystem`, and was verified with `initialized=true` and `mcpReady=true`. Claude Code and Codex share this database, while `sdk_sessions.platform_source` keeps their sessions distinguishable; Codex can query Claude observations even when startup injection is platform-filtered. This is separate from Codex built-in memories and OpenWolf `.wolf` files.
- **OpenWolf and Repomix evaluation (2026-07-16):** OpenWolf 1.0.4 provides useful anatomy/design-QC features, but its mandatory per-action memory and low-threshold bug logging duplicate claude-mem/Codex memories and keep `.wolf` files dirty. Prefer a slim configuration with generated/build directories excluded and routine logging disabled. Repomix remains globally installed; only the 170,066-line `repomix-output.xml` was deleted in security commit `90e904b` because it contained suspected credentials, then added to `.gitignore`.

## Do-Not-Repeat

<!-- Mistakes made and corrected. Each entry prevents the same mistake recurring. -->
<!-- Format: [YYYY-MM-DD] Description of what went wrong and what to do instead. -->
- [2026-05-20] **改昵称不能只靠 newUsername 改云端 username(PK)。** 若部署的后端无 newUsername 映射，updates 为空→返回"无需更新"+success=true，App 误显示成功但云端没变。正确：同时写 nickname 列（fields.nickname，原始后端就支持），登录优先读 cu.nickname。MyAddress 仿京东卡片重设计但功能不变（仍单地址）。person.ets 用户自己把版本号改成 v1.0.0，勿动。mainpage 发起通话前用已有的 deviceOnline 守卫。
- [2026-05-20] **资料页昵称/头像云端同步要用 await，不能 fire-and-forget + 立即退页。** 旧 saveProfile 发云端请求用 `.then()` 不等待，紧接着 `setTimeout(pop, 1000)` 1 秒退页销毁组件，云端请求（10s 超时）来不及完成就被丢弃→昵称永不同步。手机/邮箱/密码因为 await 且不退页所以正常。教训：任何"改完就退页"的写操作必须 await 完成或不退页。
- [2026-05-20] **Profile 改为「全内联即时保存」无全局保存按钮（用户选择）。** 昵称行改动且合法时显示「保存」小标签（点击/onSubmit 触发 saveNickname，云端优先 await）；头像 processAndSaveAvatar 末尾直接 await saveAvatar（本地立即落地 + 云端尽力同步，不退页所以 fire-and-forget 也能跑完）。删除了 hasChanged/updateChangedState/saveProfile/originalAvatarPath/originalPhone/originalEmail 以及 onBackPressed 的未保存拦截。所有资料写操作统一"云端优先"，本地与云端不会分叉，无需额外 last-write-wins 合并机制。
- [2026-05-19] **云端 t_user.username 是主键且存的是「昵称」，不是 loginId。** 改手机/邮箱/昵称时不能用 loginId 去 `WHERE username=?` 更新（必然 0 行）。正确做法：后端 /api/updateUser 用柔性 lookup `WHERE username=? OR phone=? OR email=?`，App 传当前 loginId 当 lookup key；改昵称走新增的 `newUsername` 字段更新 username 列。后端 UPDATE 后必须判断 `cursor.rowcount==0` 返回失败，否则 App 误以为成功。
- [2026-05-19] **资料修改（手机/邮箱/密码）必须「先 await 云端成功，再写本地」。** 旧代码 fire-and-forget 云端 + 先写本地，导致云端失败时双端漂移（旧手机还能登录）。云端失败就不动本地并弹错误，保证两端一致。
- [2026-05-19] **真机头像：不能 `fs.copyFile(photoUri, dest)` 直接复制 PhotoViewPicker 的 file://media URI。** 模拟器宽容、真机报「处理图片失败」。正确：`fs.openSync(uri, READ_ONLY)` 取 fd → `image.createImageSource(fd)` 解码 → crop/scale → ImagePacker 编码 JPEG → 写沙箱。文件名带时间戳绕过 Image 组件路径缓存，并删旧文件。
- [2026-05-19] **App 调 /api/changePassword 但后端原本没这个端点（404）。** 新功能调用云端接口前，先确认 wenxin_proxy.py 里端点已实现。
- [2026-05-17] **Login.ets 云端兜底登录不能覆盖本地密码。** 云端兜底成功时只同步 username，不写 `existing.passwordHash = pwd`，否则本地改密后旧密码仍能登录。
- [2026-05-17] **修改手机/邮箱后必须同步更新 AppStorage+Preferences 里的 loginId。** loginId 用于 loadProfile 查询，若修改后不更新，下次进入资料页查不到用户导致字段清空。同步方式：onSuccess 回调里判断 currentUser 格式，若为手机/邮箱则 UserManager.setCurrentUsername(newValue) + pref.putSync。
- [2026-05-17] **个人资料/地址编辑弹窗保存时，不要在保存路径重复查询数据库。** 正确模式：loadProfile/loadAddress 加载时缓存 UserInfo 对象到 loadedUser，弹窗通过 prop 接收 loadedUser，保存时直接用 loadedUser.id 做 updateUser，不再二次查询。queryUserByUsername/queryUserByIdentifier 在保存路径调用均容易因 loginId 格式与 DB 字段不匹配而返回 null。 登录后 currentUser（AppStorage）存的是 loginId（手机号/邮箱/HW_XXX），而 username 列存的是显示昵称，两者不同。queryUserByUsername 用 loginId 查必然返回 null。同理 queryUserByIdentifier 只匹配中国手机号和邮箱格式，华为 HW_ ID 需要兜底到 queryUserByPhone。
- [2026-05-17] **AI 助手出现 502 时，优先排查扣子 API Token 是否过期。** wenxin_proxy.py 的 502 来自 Coze 返回 HTTP 错误（requests.exceptions.HTTPError），最常见原因是 Token 过期。更新 Token 后必须重启服务进程（`pkill -f wenxin_proxy && nohup python3 ...`），Python 进程不会热重载，上传新文件不生效。
- [2026-07-14] **MqttManager 的告警数组按最新优先插入。** 最近记录必须读 `[0]`，不能读 `[length - 1]`；后者是最旧记录，会让 AI 的“最近一次”判断错误。
- [2026-07-14] **连接 ECS 必须显式传 `ssh -p 22`。** 本机 SSH 配置会把未指定端口的连接改写到 6022 并超时；显式 22 后 root 登录成功，主机名 `ecs-f195`。
- [2026-05-05] **主页面响应式改造时，不要把共享卡片（平板和手机共用）的 padding/margin/borderRadius 从百分比改成 rSize() 像素值。** 手机端应该保留原来的百分比值，只有平板特有的双列布局区域才用 rSize()。正确做法：共享区域保持百分比值，平板特有区域用 rSize() + constraintSize。
- [2026-05-05] **loginComponentManager.HuaweiIDCredential 和 authentication.LoginWithHuaweiIDResponse 是 Account Kit 中两个不同 API 体系的类型，不能互相强转。** LoginWithHuaweiIDButton 的回调参数类型是 loginComponentManager.HuaweiIDCredential，它的结构可能是 { data: jsonString } 或直接展开的对象，需要防御式解析。

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- **2026-05-02: Tabs → 条件渲染 + 悬浮底栏** — Tabs 的 expandSafeArea(TOP) + backgroundColor 与各页面 GradientHeader 的 expandSafeArea(TOP) 三层叠加冲突，导致反复出现顶部白块/黑块。去掉 Tabs 后每页独立控制安全区，无冲突。同时将底栏改为 iOS 风格悬浮胶囊（backdropBlur + 圆角 + 阴影），视觉更现代。
- **2026-07-14: AI 权限分为深度照护/隐私保护/基础问答** — 采用客户端先裁剪、Flask 再按等级白名单构造扣子提示；默认隐私保护。低权限上下文为空，高权限也只发送项目真实拥有的监护状态，不虚构老人身份资料。
- **2026-07-15: 安全整改分“代码止血”和“上线切换”两段** — 仓库先移除泄露快照/共享密钥、加固密码存储与日志、关闭邮箱自动注册；生产部署必须等域名证书、短信服务、第三方平台资质、密钥轮换和数据库备份回滚方案就绪后再切换，避免在明文 HTTP 上发送新的会话 Token。
- [2026-08-07] **AGC 的 ACL 受限权限一经批准就不可取消，且会自动写入此后新建的每一个 Profile。** 新建 Profile 时「不勾选受限权限」无效——实测新旧两个 .p7b 逐字段 diff 只有 uuid 不同，`acls.allowed-acls` 原样保留。华为官方采纳答复明确「全部写入不会影响后续的传包及上架流程」，因此这不是上架阻塞项。真正要保证的是 module.json5 里不声明用不到的权限。
