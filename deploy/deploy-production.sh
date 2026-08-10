#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
    echo "usage: deploy-production.sh RELEASE_DIR" >&2
    exit 2
fi

release_dir=$(readlink -f "$1")
if [[ "$release_dir" != /root/wenxin-releases/* ]] ||
   [[ ! -d "$release_dir" ]] ||
   [[ $(stat -c %U "$release_dir") != root ]] ||
   [[ $(hostname) != ecs-f195 ]]; then
    echo "unsafe release directory or host" >&2
    exit 2
fi

required=(
    wenxin_proxy.py
    admin_panel.html
    security_utils.py
    requirements-production.txt
    requirements-moderation.txt
    requirements-sms.txt
    deploy/wenxin.service
    deploy/wenxin-sqlite-backup.service
    deploy/wenxin-sqlite-backup.timer
    deploy/sqlite_maintenance.py
    deploy/wenxin-monitor.service
    deploy/wenxin-monitor.timer
    deploy/ops_monitor.py
    deploy/journald/wenxin-retention.conf
    deploy/nginx/api.aistar.asia.conf
)
for file in "${required[@]}"; do
    [[ -f "$release_dir/$file" ]] || {
        echo "missing release file: $file" >&2
        exit 2
    }
done

exec 9>/run/wenxin-deploy.lock
flock -n 9 || {
    echo "another deployment is running" >&2
    exit 1
}

stamp=$(date -u +%Y%m%dT%H%M%SZ)
rollback_dir="/root/wenxin-rollbacks/$stamp"
install -d -m 700 "$rollback_dir"
cp -a /root/wenxin_proxy.py "$rollback_dir/wenxin_proxy.py"
if [[ -f /root/admin_panel.html ]]; then
    cp -a /root/admin_panel.html "$rollback_dir/admin_panel.html"
else
    touch "$rollback_dir/admin_panel.html.missing"
fi
cp -a /root/security_utils.py "$rollback_dir/security_utils.py"
cp -a /etc/systemd/system/wenxin.service "$rollback_dir/wenxin.service"
cp -a /etc/systemd/system/wenxin-sqlite-backup.service "$rollback_dir/wenxin-sqlite-backup.service"
cp -a /etc/systemd/system/wenxin-sqlite-backup.timer "$rollback_dir/wenxin-sqlite-backup.timer"
cp -a /usr/local/lib/wenxin/sqlite_maintenance.py "$rollback_dir/sqlite_maintenance.py"
cp -a /etc/nginx/conf.d/api.aistar.asia.conf "$rollback_dir/api.aistar.asia.conf"
cp -a /usr/local/lib/wenxin/ops_monitor.py "$rollback_dir/ops_monitor.py"
cp -a /etc/systemd/system/wenxin-monitor.service "$rollback_dir/wenxin-monitor.service"
cp -a /etc/systemd/system/wenxin-monitor.timer "$rollback_dir/wenxin-monitor.timer"
cp -a /etc/systemd/journald.conf.d/wenxin-retention.conf "$rollback_dir/wenxin-retention.conf"

wait_local_health() {
    for _ in {1..10}; do
        python3 -c 'import sys, urllib.request; sys.exit(urllib.request.urlopen(sys.argv[1], timeout=3).status != 200)' \
            http://127.0.0.1:8899/health && return 0
        sleep 1
    done
    return 1
}

rollback() {
    trap - ERR
    set +e
    cp -a "$rollback_dir/wenxin_proxy.py" /root/wenxin_proxy.py
    if [[ -f "$rollback_dir/admin_panel.html.missing" ]]; then
        rm -f /root/admin_panel.html
    else
        cp -a "$rollback_dir/admin_panel.html" /root/admin_panel.html
    fi
    cp -a "$rollback_dir/security_utils.py" /root/security_utils.py
    cp -a "$rollback_dir/wenxin.service" /etc/systemd/system/wenxin.service
    cp -a "$rollback_dir/wenxin-sqlite-backup.service" /etc/systemd/system/wenxin-sqlite-backup.service
    cp -a "$rollback_dir/wenxin-sqlite-backup.timer" /etc/systemd/system/wenxin-sqlite-backup.timer
    cp -a "$rollback_dir/sqlite_maintenance.py" /usr/local/lib/wenxin/sqlite_maintenance.py
    cp -a "$rollback_dir/api.aistar.asia.conf" /etc/nginx/conf.d/api.aistar.asia.conf
    cp -a "$rollback_dir/ops_monitor.py" /usr/local/lib/wenxin/ops_monitor.py
    cp -a "$rollback_dir/wenxin-monitor.service" /etc/systemd/system/wenxin-monitor.service
    cp -a "$rollback_dir/wenxin-monitor.timer" /etc/systemd/system/wenxin-monitor.timer
    cp -a "$rollback_dir/wenxin-retention.conf" /etc/systemd/journald.conf.d/wenxin-retention.conf
    systemctl daemon-reload
    systemctl restart wenxin.service
    nginx -t && systemctl reload nginx
    systemctl restart systemd-journald
    if wait_local_health &&
       python3 -c 'import sys, urllib.request; sys.exit(urllib.request.urlopen(sys.argv[1], timeout=5).status != 200)' \
           https://api.aistar.asia/health; then
        echo "deployment failed; rollback restored $rollback_dir; health ok" >&2
    else
        echo "deployment failed; rollback attempted from $rollback_dir; health failed" >&2
    fi
    exit 1
}
trap rollback ERR

python3 -m py_compile "$release_dir/wenxin_proxy.py" \
    "$release_dir/security_utils.py" "$release_dir/deploy/sqlite_maintenance.py"
python3 -m pip install --disable-pip-version-check \
    --requirement "$release_dir/requirements-production.txt"

install -m 644 "$release_dir/wenxin_proxy.py" /root/wenxin_proxy.py
install -m 644 "$release_dir/admin_panel.html" /root/admin_panel.html
install -m 644 "$release_dir/security_utils.py" /root/security_utils.py
install -d -m 755 /usr/local/lib/wenxin
install -m 755 "$release_dir/deploy/sqlite_maintenance.py" \
    /usr/local/lib/wenxin/sqlite_maintenance.py
install -m 755 "$release_dir/deploy/ops_monitor.py" \
    /usr/local/lib/wenxin/ops_monitor.py
install -m 644 "$release_dir/deploy/wenxin.service" \
    /etc/systemd/system/wenxin.service
install -m 644 "$release_dir/deploy/wenxin-sqlite-backup.service" \
    /etc/systemd/system/wenxin-sqlite-backup.service
install -m 644 "$release_dir/deploy/wenxin-sqlite-backup.timer" \
    /etc/systemd/system/wenxin-sqlite-backup.timer
install -m 644 "$release_dir/deploy/wenxin-monitor.service" \
    /etc/systemd/system/wenxin-monitor.service
install -m 644 "$release_dir/deploy/wenxin-monitor.timer" \
    /etc/systemd/system/wenxin-monitor.timer
install -d -m 755 /etc/systemd/journald.conf.d
install -m 644 "$release_dir/deploy/journald/wenxin-retention.conf" \
    /etc/systemd/journald.conf.d/wenxin-retention.conf
install -m 644 "$release_dir/deploy/nginx/api.aistar.asia.conf" \
    /etc/nginx/conf.d/api.aistar.asia.conf

systemd-analyze verify /etc/systemd/system/wenxin.service \
    /etc/systemd/system/wenxin-sqlite-backup.service \
    /etc/systemd/system/wenxin-sqlite-backup.timer \
    /etc/systemd/system/wenxin-monitor.service \
    /etc/systemd/system/wenxin-monitor.timer
nginx -t
systemctl daemon-reload
systemctl restart systemd-journald
systemctl restart wenxin.service

wait_local_health

systemctl reload nginx
python3 -c 'import sys, urllib.request; sys.exit(urllib.request.urlopen(sys.argv[1], timeout=5).status != 200)' \
    https://api.aistar.asia/health
systemctl enable --now wenxin-sqlite-backup.timer
systemctl start wenxin-sqlite-backup.service
systemctl enable --now wenxin-monitor.timer
systemctl start wenxin-monitor.service

trap - ERR
echo "deployed $release_dir; rollback $rollback_dir"
