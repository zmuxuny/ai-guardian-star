# 智护星开发交接手册

> 面向接手 HarmonyOS 应用与云端服务的队员。整理自当前仓库代码、生产部署文档和已记录的故障经验。服务器地址、配置和验收状态可能变化；动手前先核对线上现状。

## 1. 接手先看什么

建议按下面顺序熟悉项目：

1. [README.zh-CN.md](README.zh-CN.md)：项目范围、架构、快速开始。
2. [AGENTS.md](AGENTS.md)：本仓库工作约定；修改前保留其他人的未提交改动。
3. [DEVECO_BUILD.md](DEVECO_BUILD.md)：当前 HarmonyOS SDK/API、HAP/APP 构建、产物核验。
4. [docs/aliyun-migration-repair.md](docs/aliyun-migration-repair.md)：当前生产拓扑与最近一次服务/设备验收记录。
5. [deploy/aliyun/MQTT_ACCESS.md](deploy/aliyun/MQTT_ACCESS.md)：MQTT 临时凭据、设备访问范围、部署和回滚。
6. [docs/production-operations.md](docs/production-operations.md)：备份、恢复、监控和部署流程。注意其中标为华为云保留环境的命令是历史环境专用，不能直接用于阿里云。
7. [SECURITY.md](SECURITY.md)、[docs/database-admin-access.md](docs/database-admin-access.md)：安全报告和管理后台边界。

旧的 [PROJECT_HANDOFF.md](PROJECT_HANDOFF.md) 形成于 2026-04，含已过时的华为云、OpenGauss、SDK 和接口描述。它只可作历史背景；当前代码、`DEVECO_BUILD.md`、迁移及运维专项文档优先。

## 2. 系统现状与边界

- 本仓库包括 HarmonyOS 原生客户端、Flask API/AI 网关、SQLite 维护脚本、部署配置和自动化检查。板端 AI 推理源码不在仓库内，单独部署维护。
- 客户端主链路：ArkUI/ArkTS → HTTPS API；告警链路：App 经 MQTT TLS 订阅板端事件；视频、设备状态和对讲通过设备 HTTP/WSS 接入。
- 当前生产 API 域名为 `https://api.aistar.asia`，云端服务由 Nginx HTTPS 反代到只监听回环地址的 Gunicorn/Flask；生产数据库为 SQLite。MQTT 使用 TLS 8883。
- 当前生产在阿里云 `47.108.167.0`。华为云 `117.78.9.144` 是保留/回退环境，不能把旧环境脚本、数据库或配置直接覆盖到生产。
- 开发板部署在独立环境，项目代码路径、密钥和完整人脸数据不在本仓库。板端进程正常、HTTPS 可达或 MQTT 已连接，分别都不能单独证明整条业务已验收。
- OpenGauss 不是当前生产业务库。迁移评估和当前数据库状态见 [docs/opengauss-migration-assessment.md](docs/opengauss-migration-assessment.md) 与迁移修复文档；不要因历史文档提到它就新建迁移。

## 3. 代码导航

| 范围 | 入口 | 主要职责 |
|---|---|---|
| HarmonyOS 配置 | `entry/src/main/ets/config.ets` | API、MQTT、设备地址和应用偏好键 |
| 登录/资料 | `entry/src/main/ets/pages/Login.ets`、`Profile.ets` | 登录、短信注册、资料和账号操作 |
| API 会话 | `entry/src/main/ets/common/CloudService.ets` | HTTPS、Bearer、刷新轮换、请求重试、退出和本地凭据清理 |
| AI 对话 | `entry/src/main/ets/common/WenxinService.ets`、`pages/AiChat.ets` | 选择数据授权等级、裁剪健康上下文、调用 `/ai/chat`、呈现回复 |
| MQTT 告警 | `entry/src/main/ets/pages/MqttManager.ets`、`common/MqttParser.ets` | 凭据领取、TLS 连接、订阅、事件分类和本地记录 |
| 本地数据库 | `entry/src/main/ets/database/DatabaseHelper.ets` | ArkDB 初始化、迁移、用户/事件/设置存取 |
| Flask 后端 | `wenxin_proxy.py` | 账号、短信挑战、会话、MQTT 凭据、AI 网关和受限管理页 |
| 密码安全 | `security_utils.py` | 密码哈希、校验和升级判断 |
| MQTT 授权 | `mqtt_access.py`、`guardian_mqtt_plugin.py` | 服务端短时凭据及 broker 主题/动作授权 |
| 运维 | `deploy/`、`docs/production-operations.md` | systemd、Nginx、备份、监控和运行恢复 |

## 4. 应用开发约定和经验

### 架构与状态

- 页面负责交互和展示；跨页面/网络/数据库逻辑放在 `common/` 服务或 `DatabaseHelper`，避免页面之间互相承担服务职责。
- 单例服务要明确生命周期：数据库初始化应可重复调用；会话清理必须同时清除 MQTT 连接、重连/续期定时器和缓存。
- ArkUI 响应式集合不要长期持有服务内部数组的原引用；需要界面可靠刷新时维护页面状态副本并明确同步时机。列表 key 应体现数据变化，而不是只用数组下标。
- 网络/云同步失败要有清楚的错误状态。确实允许离线工作的操作可以降级，但不要把“本地写成功”显示成“云端同步成功”。
- 数据库导出或人工检查时注意 SQLite/WAL：活动数据库可能还有 `-wal`、`-shm` 状态；应使用数据库备份 API 或 checkpoint 后的一致副本，不要只复制主 `.db` 文件就声称数据完整。

### 登录态与密钥

- Access Token 只驻留内存；用户选择“记住我”时才将 Refresh Token 写入 HarmonyOS Asset Store。不要恢复旧式本地密码认证，也不要新增密码明文/可逆缓存。
- 所有受保护 API 经 `CloudService` 统一加 Bearer。并发 401 共用 single-flight refresh；刷新成功后原请求最多重试一次，避免无限循环。
- Refresh Token 在服务端轮换；退出、改密、删号及服务端冻结/撤销均须按后端契约失效会话。新增受保护端点应从 token 推导用户身份，不信任请求体传来的 username。
- 登录态清除要联动 MQTT：当前客户端清理钩子会断连并清掉告警缓存。新增退出路径时沿用该入口，不要只清 UI 标志。
- 客户端、日志、Git 和构建产物禁止出现 API Token、短信/审核 AccessKey、管理密码、签名私钥或服务端环境文件。

### ArkTS 与发布构建

- 项目启用 ArkTS 严格检查，优先使用明确接口类型、避免 `any`/`unknown` 逃逸；按编译器要求处理异常类型，不照抄旧文档中与当前 SDK 不符的写法。
- 外部 JSON 字段名是客户端/服务器契约。Release 混淆曾改写 `expiresIn` 导致续期定时器异常；更新请求/响应字段时同步维护混淆保留规则和契约检查，并检查 Release 产物字段。
- 当前统一目标为 HarmonyOS SDK/API 24，构建基线见 `DEVECO_BUILD.md`。使用 DevEco 自带 Node、OHPM、Hvigor；依赖变化时再安装依赖，勿无故重写锁文件或升级工具链。
- HAP 用于安装测试；APP 是 App Pack，不能直接安装。只有找到非空产物、记录 SHA-256 才能称已构建；构建通过不等于真机通过，上架还需 AppGallery Connect 校验。
- 做设备验收时分开记录构建、模拟器、真机、网络、权限和端到端结果，并以仓库现有专项记录为准。历史上验证过的 API 23 真机认证链路不能替代当前 API 24 与新功能的核验，不要沿用旧结论。

### MQTT 与 AI 隐私

- App MQTT 凭据通过已登录 API 短时领取，服务端仅向 allowlist 账号授权，并限制为告警主题只读。当前是一块共享板，不代表可以对所有注册账号开放；新增设备/家庭应先建立设备绑定和分主题授权。
- App 侧 `deviceOnline` 是按最近消息超时推算。若板端没有心跳，不能把页面“在线”当作板端健康或告警到达证明；验收要看真实事件链路。
- AI 上下文默认最小化：`privacy` 不传健康统计，`basic` 仅传用户问题所需基础请求，`full` 才能传授权范围内的脱敏事件摘要。不得传姓名、手机号、人脸或完整身份信息；调整字段要同时审查同意文案、服务端日志与第三方处理范围。
- AI 请求经过后端输入审核 → 模型供应商 → 输出审核。审核服务失败应关闭放行；不可为了“恢复聊天”静默跳过审核。区分错误来源：Coze 上游错误和内容审核服务故障是两类问题，应分别查服务响应与日志；不要记录对话原文或凭据。

## 5. 服务端开发与生产规范

### API 与数据

- 新增/修改 API 时同步更新客户端接口类型、服务端验证、鉴权、契约检查与错误映射。校验 JSON 缺字段、类型错误、越界输入、重复请求、过期/撤销会话和并发刷新。
- SQL 使用参数化语句；用户密码使用 `security_utils.py` 提供的安全哈希，不要自建弱哈希或在响应/日志写出敏感值。敏感操作需验证当前会话/挑战，并考虑事务边界与并发竞争。
- 短信挑战只保存 challenge/code 的哈希，限定有效期、一次性使用、失败次数和手机号/IP 频控；同时设置日/月费用上限。检查测试是否只用临时库和测试 provider。
- SQLite 变更需考虑旧库兼容、服务并发写、备份和回滚。恢复前先在隔离目录校验 `PRAGMA integrity_check`、表结构和关键记录；不要用旧库覆盖当前生产数据来回滚代码。
- 错误响应给调用端足够的分类，但日志只留排查所需的脱敏元数据。认证信息、短信码、用户健康内容、Cookie、Token、AccessKey 不得进入普通日志。

### 网络和管理边界

- 生产拓扑保持：公网 Nginx 443/HTTPS → Gunicorn/Flask 回环 `127.0.0.1:8899`。不要开放公网 8899，也不要恢复明文 MQTT 1883；MQTT 使用 TLS 8883、校验 CA 和服务端身份。
- 管理页 `/admin` 只允许经 SSH 隧道访问，公网固定返回 404。参考 [docs/database-admin-access.md](docs/database-admin-access.md)。不要为了排障临时公开后台或数据库。
- 配置与密钥放在服务器 root-only 环境文件/密钥管理中，权限按专项文档维持；部署输出和聊天中只展示服务状态、健康检查、脱敏摘要。
- 当前 MQTT 凭据按短 TTL 签发，App 需提前续期；登出/冻结/删除/过期应停止后续消息投递。已在网络中的消息无法撤回，空闲 TCP 连接也不代表消息授权仍有效。

### 部署、备份和回滚

1. 先确认目标主机、分支、服务版本与变更范围；备份当前应用、systemd/Nginx 配置和数据库（SQLite backup API）。保留 UTC 时间戳回滚件。
2. 生产依赖按 `requirements-production.txt` 管理；先在隔离环境运行针对性回归，再检查 unit 和 Nginx 配置语法。
3. 先部署/重启 API，检查本机 `/health` 和服务日志；再平滑加载 Nginx并从公网检查 HTTPS。MQTT/broker 改动还要验证原板端重连、授权订阅/发布边界及 App 告警。
4. 失败时恢复本轮代码与配置并验证本机、公网健康检查；不要通过开放端口、关闭鉴权或覆盖业务库应急。
5. 定期检查 SQLite 在线备份新鲜度与完整性；恢复演练先写入隔离目录，正式恢复需有明确停机/切换窗口。

具体命令和当前配置以 [docs/aliyun-migration-repair.md](docs/aliyun-migration-repair.md)、[docs/production-operations.md](docs/production-operations.md) 及 `deploy/aliyun/` 为准。生产状态、域名解析、allowlist、账单、证书有效期是动态信息，每次操作先现场核对。

## 6. 验收时怎样描述证据

| 证据 | 能说明 | 不能单独说明 |
|---|---|---|
| Python 单元/契约检查通过 | 被覆盖的逻辑符合预期 | 生产配置正确、真机已安装 |
| `BUILD SUCCESSFUL` | 构建任务结束 | 产物存在、签名正确、设备可运行 |
| HAP 安装启动 | 指定设备上的基本安装启动 | 全部 API、权限、弱网和硬件流程通过 |
| `/health` 返回 200 | API 健康端点当时可用 | 登录、短信、数据库写入、AI/MQTT 端到端正常 |
| MQTT 已连接/订阅成功 | broker 接受当前连接和主题订阅 | 真实告警已送达并正确落库/呈现 |
| 服务进程 active | 进程管理器认为进程运行 | API 可用或用户业务完成 |

交接测试结果时记下设备/版本、环境、步骤、期望和实际、时间及日志摘要；把“通过”“未覆盖”“跳过（原因）”分开写。

## 7. 常见坑与处理经验

- DevEco 报 `00303217 Configuration Error`：先检查 `DEVECO_SDK_HOME` 是否指向 DevEco 的 SDK，而不是先反复 clean。
- 干净检出缺 `@ohos/mqtt`：检查 OHPM 安装与 DevEco 自带 Node；确认被忽略的依赖目录/锁文件状态，别把生成物误提交。
- Release 出现 MQTT 凭据不断续期：先查混淆后的字段名、返回 JSON 和有限数值检查，不能仅看 Debug。
- 本地 RDB 看不到最近记录：确认 WAL 状态并用一致性备份/checkpoint。
- AI 接口返回 5xx：沿 App → `/ai/chat` → 输入审核 → Coze → 输出审核逐段查，依据上游状态分类；不能把审核失败等同模型故障。
- SSH/FRP 断开：分别观察服务 PID/重启次数、板端帧增长、摄像头状态、MQTT、NPU/USB/OOM 和 API。单次隧道失败不能判定业务进程崩溃。
- 摄像头离线后旧帧可能造成“假在线”；失去新帧时应检查 `camera_connected`、FPS 和帧接口状态，恢复后确认帧确实增长。
- 不因历史交接里的某个 IP、端口、数据库、SDK 数字或测试通过记录推定现状；回到配置和线上证据确认。

## 8. 建议交接清单

- [ ] 本地开发环境：DevEco/SDK、Python、Node/OHPM 版本和当前签名材料保管人已确认。
- [ ] 明确 API 24 的目标设备与最低兼容版本，完成一次当前分支 Release HAP 构建并归档产物哈希。
- [ ] 确认生产 SSH/云账号由新负责人按团队流程获得；不要通过聊天传递私钥、密码或 Token。
- [ ] 交接生产服务、数据库备份、监控告警、证书续期、短信/审核/模型供应商账单入口及各自负责人。
- [ ] 逐项列明实体设备验收：登录/刷新/退出、MQTT 真实告警、摄像头恢复、双向音频、AI 同意与审核；当前未实测项继续标为待验收。
- [ ] 先读 Git 工作区和未提交差异，再开始改动；发布前按专项文档留备份、做健康检查并写明回滚步骤。

## 9. 关键文档索引

- 构建：[`DEVECO_BUILD.md`](DEVECO_BUILD.md)
- 当前生产迁移和设备验收：[`docs/aliyun-migration-repair.md`](docs/aliyun-migration-repair.md)
- 生产运行、备份和监控：[`docs/production-operations.md`](docs/production-operations.md)
- MQTT ACL 与回滚：[`deploy/aliyun/MQTT_ACCESS.md`](deploy/aliyun/MQTT_ACCESS.md)
- AI 内容审核：[`docs/aliyun-content-moderation-setup.md`](docs/aliyun-content-moderation-setup.md)
- 短信注册：[`docs/aliyun-sms-registration-setup.md`](docs/aliyun-sms-registration-setup.md)
- 管理页隧道：[`docs/database-admin-access.md`](docs/database-admin-access.md)
- 数据库迁移评估：[`docs/opengauss-migration-assessment.md`](docs/opengauss-migration-assessment.md)
- 项目结构：[`PROJECT_STRUCTURE.md`](PROJECT_STRUCTURE.md)
