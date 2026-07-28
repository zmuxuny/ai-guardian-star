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
