#!/usr/bin/env python3
import json
import math
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def count_costly_ai_requests(logs):
    count = 0
    for line in logs.splitlines():
        match = re.search(r'"POST /ai/chat HTTP/[^"]+" (\d{3}) ', line)
        if match and int(match.group(1)) not in (400, 401, 413, 429):
            count += 1
    return count


def count_ai_upstream_auth_failures(logs):
    return len(
        re.findall(r"\[ai_chat\] upstream HTTP status=(?:401|403)\b", logs)
    )


def evaluate_metrics(metrics):
    alerts = []
    checks = (
        (not metrics["wenxin_active"], "wenxin_service", "inactive"),
        (not metrics["nginx_active"], "nginx_service", "inactive"),
        (not metrics["health_ok"], "health", "local endpoint failed"),
        (
            metrics["disk_used_percent"] >= int(os.environ.get("DISK_USED_ALERT_PERCENT", "85")),
            "disk",
            f'{metrics["disk_used_percent"]:.1f}% used',
        ),
        (
            metrics["memory_used_percent"] >= int(os.environ.get("MEMORY_USED_ALERT_PERCENT", "90")),
            "memory",
            f'{metrics["memory_used_percent"]:.1f}% used',
        ),
        (
            metrics["tls_days_remaining"] <= int(os.environ.get("TLS_EXPIRY_ALERT_DAYS", "21")),
            "tls",
            f'{metrics["tls_days_remaining"]:.1f} days remaining',
        ),
        (
            metrics["backup_age_hours"] >= int(os.environ.get("BACKUP_MAX_AGE_HOURS", "36")),
            "backup_age",
            f'{metrics["backup_age_hours"]:.1f} hours',
        ),
        (
            metrics["backup_integrity"] != "ok",
            "backup_integrity",
            metrics["backup_integrity"],
        ),
        (
            metrics["sms_count"] >= math.ceil(metrics["sms_limit"] * 0.8),
            "sms_usage",
            f'{metrics["sms_count"]}/{metrics["sms_limit"]} sends',
        ),
        (
            metrics["ai_count"] >= int(os.environ.get("AI_DAILY_REQUEST_ALERT", "100")),
            "ai_usage",
            f'{metrics["ai_count"]} potentially billable requests',
        ),
        (
            metrics["ai_auth_failures"] > 0,
            "ai_upstream_auth",
            f'{metrics["ai_auth_failures"]} failures in 10 minutes',
        ),
    )
    for failed, name, detail in checks:
        if failed:
            alerts.append(f"{name}: {detail}")
    return alerts


def _service_active(name):
    return subprocess.run(
        ["systemctl", "is-active", "--quiet", name], check=False
    ).returncode == 0


def _health_ok(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        body = json.load(response)
        return response.status == 200 and body.get("status") == "ok"


def _memory_used_percent():
    values = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0])
    return 100 * (1 - values["MemAvailable"] / values["MemTotal"])


def _tls_days_remaining(certificate):
    decoded = ssl._ssl._test_decode_cert(str(certificate))
    expires = datetime.fromtimestamp(
        ssl.cert_time_to_seconds(decoded["notAfter"]), timezone.utc
    )
    return (expires - datetime.now(timezone.utc)).total_seconds() / 86400


def _backup_metrics(backup_dir):
    latest = max(Path(backup_dir).glob("guardian_users-*.db"), key=lambda path: path.stat().st_mtime)
    age = (time.time() - latest.stat().st_mtime) / 3600
    conn = sqlite3.connect(f"{latest.resolve().as_uri()}?mode=ro", uri=True)
    try:
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
    finally:
        conn.close()
    return age, integrity


def _sms_count(database):
    conn = sqlite3.connect(f"{Path(database).resolve().as_uri()}?mode=ro", uri=True)
    try:
        return conn.execute(
            "SELECT COUNT(1) FROM t_sms_challenge "
            "WHERE purpose='register' AND sent_at>=?",
            (int(time.time()) - 24 * 60 * 60,),
        ).fetchone()[0]
    finally:
        conn.close()


def _journal_logs(since):
    result = subprocess.run(
        [
            "journalctl",
            "-u",
            "wenxin.service",
            "--since",
            since,
            "--no-pager",
            "-o",
            "cat",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def collect_metrics():
    disk = shutil.disk_usage("/")
    backup_age, backup_integrity = _backup_metrics(
        os.environ.get("SQLITE_BACKUP_DIR", "/var/backups/wenxin")
    )
    ai_logs = _journal_logs("24 hours ago")
    recent_ai_logs = _journal_logs("10 minutes ago")
    return {
        "wenxin_active": _service_active("wenxin.service"),
        "nginx_active": _service_active("nginx.service"),
        "health_ok": _health_ok(
            os.environ.get("HEALTH_URL", "http://127.0.0.1:8899/health")
        ),
        "disk_used_percent": 100 * disk.used / disk.total,
        "memory_used_percent": _memory_used_percent(),
        "tls_days_remaining": _tls_days_remaining(
            Path(
                os.environ.get(
                    "TLS_CERTIFICATE",
                    "/etc/letsencrypt/live/api.aistar.asia/fullchain.pem",
                )
            )
        ),
        "backup_age_hours": backup_age,
        "backup_integrity": backup_integrity,
        "sms_count": _sms_count(
            os.environ.get("SQLITE_DB_PATH", "/root/guardian_users.db")
        ),
        "sms_limit": int(os.environ.get("ALIYUN_SMS_DAILY_LIMIT", "20")),
        "ai_count": count_costly_ai_requests(ai_logs),
        "ai_auth_failures": count_ai_upstream_auth_failures(recent_ai_logs),
    }


def main():
    try:
        metrics = collect_metrics()
        alerts = evaluate_metrics(metrics)
    except Exception as error:
        print(f"MONITOR_ALERT internal: {type(error).__name__}", file=sys.stderr)
        return 1
    if alerts:
        for alert in alerts:
            print(f"MONITOR_ALERT {alert}", file=sys.stderr)
        return 1
    print(f"MONITOR_OK {json.dumps(metrics, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
