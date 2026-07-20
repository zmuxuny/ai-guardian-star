# openGauss 生产迁移评估（2026-07-18）

## 结论

当前不切换生产数据库。服务器已有 openGauss 6.0.3 LTS，实例基本为空，可以在整改后复用；但现有 ECS 只有 2 核、约 3.3 GiB 内存且无 Swap，低于官方个人开发最低 2 核 4 GB，并且数据库缺少可靠 systemd 自启、监听所有网卡。现在迁移会降低登录系统可靠性。

SQLite 继续作为当前生产库，不影响应用功能。项目答辩可准确表述为“已在华为云部署 openGauss 并完成迁移可行性验证，生产切换需先完成规格和安全整改”，不能表述为已经使用 openGauss 承载生产数据。

## 服务器实测

- 系统：openEuler 24.03 LTS，x86_64。
- 资源：2 vCPU、3405 MiB 内存、无 Swap；根盘剩余约 29 GB。
- openGauss：6.0.3 LTS，用户 `omm`，数据目录 `/opt/gauss/data/dn1`。
- 实例：约 31.8 MiB，1 个非模板数据库，当前 schema 0 张用户表，0 个外部客户端连接。
- 进程：常驻内存约 994 MiB，`shared_buffers=1GB`。
- 风险：15400/15401 监听所有网卡；未找到正式的 `opengauss.service`。
- 兼容性：openGauss 6.0 官方支持矩阵未列出 openEuler 24.03，属于实测可运行但官方未覆盖组合。

## 切换前条件

1. ECS 至少升级到 4 核 8 GB，并确认变更规格价格。
2. 建立正式 systemd 服务和开机自启。
3. 数据库只监听 `127.0.0.1`，同步收紧 `pg_hba.conf` 和华为云安全组。
4. 创建独立业务数据库和最小权限角色，不用 `omm` 运行 Flask。
5. 使用权限 0600 的环境文件保存数据库密码。
6. 验证与 openGauss 匹配的官方 psycopg2 驱动，不能直接假设普通 `psycopg2-binary` 完全兼容。
7. 完成自动备份和一次恢复演练。

官方依据：[硬件准备要求](https://docs.opengauss.org/en/docs/latest/getting_started/preparing_for_installation.html)、[Python 驱动](https://docs.opengauss.org/en/docs/latest/getting_started/python.html)、[版本生命周期](https://opengauss.org/en/download/?version=all)。

## 受控迁移步骤

1. 备份 `/root/guardian_users.db`，记录表行数与完整性检查结果。
2. 在 openGauss 新建独立业务库、角色、`t_user`、`t_session` 和唯一约束。
3. 数据访问层同时支持 SQLite 与 openGauss：占位符、字典游标和并发事务分别适配。
4. 在临时库执行全部登录、刷新、注销、改密、删号回归。
5. 安排几分钟停写窗口，导入用户、密码哈希与会话哈希，不输出任何敏感值。
6. 对比行数、唯一约束和哈希校验，执行真实登录验收。
7. 通过环境变量切到 openGauss；失败且尚无新写入时立即切回 SQLite。
8. 至少保留两份只读 SQLite 快照。当前规模不做双写，避免增加新的数据一致性风险。
