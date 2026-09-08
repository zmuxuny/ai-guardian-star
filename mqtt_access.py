"""Short-lived, read-only MQTT grants bound to existing login sessions."""

import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path

APP_PREFIX = 'guardian_app_'
ALERT_FILTER = 'ai_guardian/alerts/#'
GRANT_TTL = 300


def allowed_users(path):
    """Read the explicit single-board account allowlist; missing/invalid means deny."""
    try:
        users = json.loads(Path(path).read_text(encoding='utf-8'))
        if isinstance(users, list) and all(isinstance(user, str) for user in users):
            return set(users)
    except (OSError, ValueError):
        pass
    return set()


def create_schema(conn):
    conn.execute('''CREATE TABLE IF NOT EXISTS t_mqtt_grant (
        client_id TEXT PRIMARY KEY,
        password_hash TEXT NOT NULL,
        access_token_hash TEXT NOT NULL UNIQUE,
        expires_at INTEGER NOT NULL
    )''')


def issue_grant(conn, access_hash, session_expiry, now=None):
    now = int(time.time()) if now is None else now
    password = secrets.token_urlsafe(32)
    client_id = APP_PREFIX + secrets.token_hex(12)
    expires_at = min(now + GRANT_TTL, session_expiry)
    conn.execute('DELETE FROM t_mqtt_grant WHERE expires_at<=? OR access_token_hash=?',
                 (now, access_hash))
    conn.execute('INSERT INTO t_mqtt_grant VALUES (?, ?, ?, ?)',
                 (client_id, hashlib.sha256(password.encode()).hexdigest(), access_hash, expires_at))
    return {'username': client_id, 'password': password, 'clientId': client_id,
            'topic': ALERT_FILTER, 'expiresIn': expires_at - now}


def valid_grant(database, users_file, client_id, password, now=None):
    """Check revocation on every delivery, including logout, frozen/deleted user and allowlist removal."""
    if not isinstance(client_id, str) or not isinstance(password, str):
        return False
    if not client_id.startswith(APP_PREFIX) or len(password) > 128:
        return False
    now = int(time.time()) if now is None else now
    try:
        # mode=ro prevents silently creating a second empty database on misconfiguration.
        conn = sqlite3.connect(Path(database).resolve().as_uri() + '?mode=ro', uri=True, timeout=1)
        try:
            row = conn.execute('''
                SELECT u.username FROM t_mqtt_grant AS m
                JOIN t_session AS s ON s.access_token_hash=m.access_token_hash
                JOIN t_user AS u ON u.username=s.username
                WHERE m.client_id=? AND m.password_hash=? AND m.expires_at>?
                  AND s.access_expires_at>? AND COALESCE(u.is_frozen, 0)=0
            ''', (client_id, hashlib.sha256(password.encode()).hexdigest(), now, now)).fetchone()
        finally:
            conn.close()
        return bool(row and row[0] in allowed_users(users_file))
    except (OSError, sqlite3.Error):
        return False


def permitted_topic(topic, action):
    if not isinstance(topic, str):
        return False
    if action == 'subscribe':
        return topic == ALERT_FILTER
    if action == 'receive':
        return (topic == 'ai_guardian/alerts' or topic.startswith('ai_guardian/alerts/')) and not any(
            character in topic for character in ('#', '+', '\x00'))
    return False
