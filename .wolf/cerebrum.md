# Cerebrum

> OpenWolf's learning memory. Updated automatically as the AI learns from interactions.
> Do not edit manually unless correcting an error.
> Last updated: 2026-05-01

## User Preferences

<!-- How the user likes things done. Code style, tools, patterns, communication. -->
- **修复后及时推送**：修复一个问题、确认没问题之后，必须立即 commit + push，不要积攒多个修复再一次推送。

## Key Learnings

- **Project:** caringSystem
- **Description:** <div align="center">
- **Layout.ets 已改为 Stack + visibility 常驻方案（2026-05-06）**：去掉 Tabs，每页用 Stack 叠加 + `visibility(Visible/None)` 控制显示，底部用自定义 Row。四页始终挂载不销毁，切 tab 保留聊天/输入/滚动状态。Tabs 层的 expandSafeArea + backgroundColor 冲突问题彻底消除，每页完全独立控制自己的顶部安全区
- **Record 页面模式（标准参考）**：GradientHeader 不带 expandSafeArea（仅用 topSafeHeight padding） + 圆角底部 + 紧随其后的卡片用负 margin（-4%）叠入渐变区域形成过渡桥
- mainpage：VideoArea 移出 Scroll 并用负 margin 叠入渐变头部，模仿 record 的 StatDashboard 过渡模式
- AiChat：新增 HealthOverview 卡片（复用 MqttManager 数据），置于 GradientHeader 与 Scroll 之间，用负 margin 叠入渐变
- person：StatDashboard 已有负 margin，仅需保持 GradientHeader 与 record 一致（无 expandSafeArea + borderRadius）

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
- [2026-05-05] **主页面响应式改造时，不要把共享卡片（平板和手机共用）的 padding/margin/borderRadius 从百分比改成 rSize() 像素值。** 手机端应该保留原来的百分比值，只有平板特有的双列布局区域才用 rSize()。正确做法：共享区域保持百分比值，平板特有区域用 rSize() + constraintSize。
- [2026-05-05] **loginComponentManager.HuaweiIDCredential 和 authentication.LoginWithHuaweiIDResponse 是 Account Kit 中两个不同 API 体系的类型，不能互相强转。** LoginWithHuaweiIDButton 的回调参数类型是 loginComponentManager.HuaweiIDCredential，它的结构可能是 { data: jsonString } 或直接展开的对象，需要防御式解析。

## Decision Log

<!-- Significant technical decisions with rationale. Why X was chosen over Y. -->

- **2026-05-02: Tabs → 条件渲染 + 悬浮底栏** — Tabs 的 expandSafeArea(TOP) + backgroundColor 与各页面 GradientHeader 的 expandSafeArea(TOP) 三层叠加冲突，导致反复出现顶部白块/黑块。去掉 Tabs 后每页独立控制安全区，无冲突。同时将底栏改为 iOS 风格悬浮胶囊（backdropBlur + 圆角 + 阴影），视觉更现代。
