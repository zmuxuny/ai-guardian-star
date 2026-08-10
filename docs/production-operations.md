# 生产运行与恢复

生产拓扑：公网只到 Nginx `443`；Nginx 转发 `127.0.0.1:8899`；Gunicorn 运行
`wenxin_proxy:app`。SQLite 仍位于 `/root/guardian_users.db`，每日在线备份到
`/var/backups/wenxin`，每份先执行 `PRAGMA integrity_check`，保留 14 天。

## 部署

以下命令中的仓库路径和服务器地址是当前生产值；整块执行前必须先确认 SSH
主机仍为 `ecs-f195`。密钥、短信、审核和 AI 凭据不出服务器，不写进命令或仓库。

1. 上传代码和配置到临时路径。
2. 备份当前文件：

   ```sh
   stamp=$(date -u +%Y%m%dT%H%M%SZ)
   install -m 600 /etc/systemd/system/wenxin.service "/root/wenxin.service.$stamp.rollback"
   install -m 600 /etc/nginx/conf.d/api.aistar.asia.conf "/root/api.aistar.asia.conf.$stamp.rollback"
   install -m 600 /root/wenxin_proxy.py "/root/wenxin_proxy.py.$stamp.rollback"
   ```

3. 安装 `requirements-production.txt`，再安装 unit、Nginx 配置和
   `sqlite_maintenance.py`。
4. 先运行 `systemd-analyze verify` 与 `nginx -t`；任何一个失败都停止，不重启服务。
5. `systemctl daemon-reload && systemctl restart wenxin.service`，确认本机
   `/health` 后再 `systemctl reload nginx`。
6. 启用 `wenxin-sqlite-backup.timer`，立即手工运行一次备份。

## Gunicorn / Nginx 回滚

服务或接口验收失败时，立刻把本轮 `.rollback` 文件装回原路径，执行：

```sh
systemctl daemon-reload
systemctl restart wenxin.service
nginx -t
systemctl reload nginx
curl --fail --silent http://127.0.0.1:8899/health
```

回滚后仍须检查 `systemctl status wenxin.service` 和公网 HTTPS `/health`。不得通过
恢复公网 `8899` 或启用公开 `/admin` 绕过故障。

## SQLite 恢复演练

恢复命令默认拒绝覆盖现有数据库。先恢复到隔离目录并核对完整性、表和行数：

```sh
drill="/root/wenxin-restore-drill-$(date -u +%Y%m%dT%H%M%SZ)"
install -d -m 700 "$drill"
latest=$(find /var/backups/wenxin -maxdepth 1 -type f -name 'guardian_users-*.db' | sort | tail -n 1)
python3 /usr/local/lib/wenxin/sqlite_maintenance.py restore --backup "$latest" --target "$drill/guardian_users.db"
python3 - "$drill/guardian_users.db" <<'PY'
import sqlite3
import sys
db = sqlite3.connect(sys.argv[1])
assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
for table in ("t_user", "t_session", "t_sms_challenge"):
    print(table, db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
db.close()
PY
```

真实灾难恢复前：停止 `wenxin.service`，把损坏数据库移到带 UTC 时间戳的隔离路径，
恢复到 `/root/guardian_users.db`，确认权限 `600`，再启动服务并验证登录。不得删除
原数据库或备份。

## CI 与自动部署

`.github/workflows/ci.yml` 默认在 `main`、`develop` 和 PR 上运行 Python 测试、
语法检查和差异检查。HarmonyOS 构建需要标签为 `Windows`、`caring-system` 的
自托管 runner；确认 runner 安全隔离后设置：

- 仓库变量 `HARMONY_BUILD_ENABLED=true`
- 仓库变量 `DEVECO_STUDIO_HOME` 为 DevEco Studio 绝对路径

生产自动部署默认关闭。准备 GitHub `production` Environment 审批后，再设置：

- 仓库变量 `PRODUCTION_DEPLOY_ENABLED=true`
- 仓库变量 `PRODUCTION_SSH_HOST`
- Actions secret `PRODUCTION_SSH_KEY`
- Actions secret `PRODUCTION_SSH_KNOWN_HOSTS`

部署脚本只接受 `ecs-f195` 上 `/root/wenxin-releases/` 内、root 所有的 release
目录。每次部署保存 `/root/wenxin-rollbacks/<UTC时间>`；本机或公网健康检查失败时
自动恢复应用、systemd、Nginx 和备份脚本。GitHub 密钥不得写入仓库或构建日志。

## 监控与告警

`wenxin-monitor.timer` 每五分钟检查 API/Nginx、磁盘、可用内存、TLS 剩余天数、
备份新鲜度与完整性、24 小时及自然月短信发送量，以及可能产生费用的 AI 请求量。
默认阈值：磁盘 85%、内存 90%、TLS 21 天、备份 36 小时、短信日上限 100 条、
短信月上限 200 条、AI 100 次/日；短信达到日/月上限的 80% 时告警，达到上限后
应用直接拒绝继续发送。近 10 分钟出现 AI 上游 `401/403` 也会立即告警。阈值可放在
root-only `/etc/wenxin/monitor.env` 中调整：

```ini
ALIYUN_SMS_DAILY_LIMIT=100
ALIYUN_SMS_MONTHLY_LIMIT=200
AI_DAILY_REQUEST_ALERT=100
```

检查失败时 `wenxin-monitor.service` 进入 failed，详细原因写入 journal：

```sh
systemctl --failed
journalctl -u wenxin-monitor.service --since today --no-pager
```

Nginx 已由系统 logrotate 每日压缩、保留 10 份；journald 限制为 256 MiB、最长
30 天。Certbot 每日检查续期。当前服务器没有外发告警接收渠道；绑定邮件/Webhook
前，systemd failed 仅是本机告警，不能视为已送达通知。短信计数来自实际注册
challenge；AI 数量按 Gunicorn 访问日志保守估算，不等同供应商余额或账单。
阿里云短信账单、Coze Token 余额等金额告警仍须在各自控制台绑定接收邮箱。
