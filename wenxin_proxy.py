"""
wenxin_proxy.py — 智护星 AI 助手 · 扣子编程智能体中转服务
部署在华为云 ECS 上，避免 API Token 暴露在 App 端

依赖安装：pip install flask flask-cors requests
后台运行：nohup python3 wenxin_proxy.py > /var/log/wenxin_proxy.log 2>&1 &
"""

from flask import Flask, request, jsonify, session, redirect, url_for, g
from flask_cors import CORS
import base64
import hmac
import hashlib
import requests
import secrets
import time
import json
import sqlite3
import os
import functools
import re
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

from security_utils import hash_password, password_needs_rehash, verify_password

app = Flask(__name__)


def _env_true(name):
    return os.environ.get(name, '').strip().lower() == 'true'


CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',')
    if origin.strip()
]
if CORS_ALLOWED_ORIGINS:
    CORS(app, origins=CORS_ALLOWED_ORIGINS)

# ─── 管理后台配置 ──────────────────────────────────────────────
ADMIN_ENABLED = _env_true('ADMIN_ENABLED')
if ADMIN_ENABLED:
    ADMIN_PASSWORD = os.environ['ADMIN_PASSWORD']
    app.secret_key = os.environ['FLASK_SECRET_KEY']
else:
    ADMIN_PASSWORD = ''
    app.secret_key = os.environ.get('FLASK_SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Strict',
    SESSION_COOKIE_SECURE=True,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
)
# ──────────────────────────────────────────────────────────────

# ─── 配置区 ────────────────────────────────────────────────────
COZE_STREAM_URL = "https://yhgh6fywzc.coze.site/stream_run"
COZE_PROJECT_ID = "7627479213733445658"
COZE_API_TOKEN = os.environ.get('COZE_API_TOKEN', '')
AI_MAX_MESSAGE_LENGTH = int(os.environ.get('AI_MAX_MESSAGE_LENGTH', '2000'))
AI_RISK_CONTROL_READY = _env_true('AI_RISK_CONTROL_READY')
ALIYUN_MODERATION_ENABLED = _env_true('ALIYUN_MODERATION_ENABLED')
ALIYUN_MODERATION_ENDPOINT = os.environ.get(
    'ALIYUN_MODERATION_ENDPOINT', 'green-cip.cn-shanghai.aliyuncs.com'
)
ALIYUN_SMS_ENABLED = _env_true('ALIYUN_SMS_ENABLED')
ALIYUN_SMS_ACCESS_KEY_ID = os.environ.get('ALIBABA_CLOUD_SMS_ACCESS_KEY_ID', '')
ALIYUN_SMS_ACCESS_KEY_SECRET = os.environ.get('ALIBABA_CLOUD_SMS_ACCESS_KEY_SECRET', '')
ALIYUN_SMS_SIGN_NAME = os.environ.get('ALIYUN_SMS_SIGN_NAME', '')
ALIYUN_SMS_TEMPLATE_CODE = os.environ.get('ALIYUN_SMS_TEMPLATE_CODE', '100001')
ALIYUN_SMS_SCHEME_NAME = os.environ.get('ALIYUN_SMS_SCHEME_NAME', 'guardian-register')
ALIYUN_SMS_DAILY_LIMIT = int(os.environ.get('ALIYUN_SMS_DAILY_LIMIT', '100'))
ALIYUN_SMS_MONTHLY_LIMIT = int(os.environ.get('ALIYUN_SMS_MONTHLY_LIMIT', '200'))
EMAIL_OTP_ENABLED = _env_true('EMAIL_OTP_ENABLED')
SMTP_HOST = os.environ.get('SMTP_HOST', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '465'))
SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SMTP_FROM = os.environ.get('SMTP_FROM', SMTP_USERNAME)
SMTP_USE_SSL = os.environ.get('SMTP_USE_SSL', 'true').strip().lower() != 'false'
EMAIL_OTP_DAILY_LIMIT = int(os.environ.get('EMAIL_OTP_DAILY_LIMIT', '50'))
ACCESS_TOKEN_TTL = 15 * 60
REFRESH_TOKEN_TTL = 30 * 24 * 60 * 60
SMS_CODE_TTL = 5 * 60
SMS_MAX_ATTEMPTS = 5
PASSWORD_MIN_LENGTH = 4
PASSWORD_RESET_WINDOW = 10 * 60
MAX_AVATAR_BYTES = 750 * 1024

# 账号数据库路径（ECS 上持久存储）
DB_PATH = os.path.join(os.path.dirname(__file__), "guardian_users.db")
# ──────────────────────────────────────────────────────────────


def get_db():
    """获取 SQLite 连接，自动建表"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS t_user (
            username      TEXT PRIMARY KEY,
            nickname      TEXT,
            phone         TEXT,
            password_hash TEXT NOT NULL,
            avatar_path   TEXT,
            email         TEXT,
            address       TEXT,
            create_time   INTEGER NOT NULL
        )
    """)
    user_columns = {row['name'] for row in conn.execute("PRAGMA table_info(t_user)")}
    for column, definition in (
        ('avatar_data', 'BLOB'),
        ('avatar_mime', 'TEXT'),
        ('avatar_updated_at', 'INTEGER'),
    ):
        if column not in user_columns:
            conn.execute(f"ALTER TABLE t_user ADD COLUMN {column} {definition}")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS t_session (
            access_token_hash  TEXT PRIMARY KEY,
            refresh_token_hash TEXT NOT NULL UNIQUE,
            username           TEXT NOT NULL,
            access_expires_at  INTEGER NOT NULL,
            refresh_expires_at INTEGER NOT NULL,
            create_time        INTEGER NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS t_sms_challenge (
            challenge_hash TEXT PRIMARY KEY,
            phone          TEXT NOT NULL,
            purpose        TEXT NOT NULL,
            requester_ip   TEXT NOT NULL,
            sent_at        INTEGER NOT NULL,
            expires_at     INTEGER NOT NULL,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            checking_at    INTEGER,
            consumed_at    INTEGER
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sms_challenge_phone_sent "
        "ON t_sms_challenge(phone, sent_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sms_challenge_ip_sent "
        "ON t_sms_challenge(requester_ip, sent_at)"
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS t_contact_challenge (
            challenge_hash TEXT PRIMARY KEY,
            username       TEXT NOT NULL,
            kind           TEXT NOT NULL,
            value          TEXT NOT NULL,
            code_hash      TEXT,
            requester_ip   TEXT NOT NULL,
            sent_at        INTEGER NOT NULL,
            expires_at     INTEGER NOT NULL,
            failed_attempts INTEGER NOT NULL DEFAULT 0,
            checking_at    INTEGER,
            consumed_at    INTEGER
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contact_value_sent "
        "ON t_contact_challenge(kind, value, sent_at)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_contact_ip_sent "
        "ON t_contact_challenge(requester_ip, sent_at)"
    )
    conn.commit()
    return conn


def _token_hash(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _new_session(conn, username, now=None):
    now = int(time.time()) if now is None else now
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO t_session
            (access_token_hash, refresh_token_hash, username,
             access_expires_at, refresh_expires_at, create_time)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _token_hash(access_token),
            _token_hash(refresh_token),
            username,
            now + ACCESS_TOKEN_TTL,
            now + REFRESH_TOKEN_TTL,
            now,
        ),
    )
    return {
        "accessToken": access_token,
        "refreshToken": refresh_token,
        "expiresIn": ACCESS_TOKEN_TTL,
        "refreshExpiresIn": REFRESH_TOKEN_TTL,
    }


def _user_json(row):
    return {
        "username": row['username'],
        "nickname": row['nickname'] or '',
        "phone": row['phone'] or '',
        "avatarPath": '',
        "avatarVersion": row['avatar_updated_at'] or 0,
        "email": row['email'] or '',
        "address": row['address'] or '',
        "createTime": row['create_time'],
    }


def _internal_error(scope, error):
    app.logger.error("[%s] internal error type=%s", scope, type(error).__name__)
    return jsonify({"success": False, "message": "服务内部错误"}), 500


def _client_ip():
    if request.remote_addr in ('127.0.0.1', '::1'):
        forwarded = request.headers.get('X-Real-IP', '').strip()
        if forwarded:
            return forwarded[:64]
    return (request.remote_addr or 'unknown')[:64]


def _sms_client():
    if not ALIYUN_SMS_ACCESS_KEY_ID or not ALIYUN_SMS_ACCESS_KEY_SECRET:
        raise RuntimeError('SMS credentials are not configured')
    try:
        from alibabacloud_dypnsapi20170525.client import Client
        from alibabacloud_tea_openapi import models as open_api_models
    except ImportError as error:
        raise RuntimeError('SMS SDK is not installed') from error
    config = open_api_models.Config(
        access_key_id=ALIYUN_SMS_ACCESS_KEY_ID,
        access_key_secret=ALIYUN_SMS_ACCESS_KEY_SECRET,
    )
    config.endpoint = 'dypnsapi.aliyuncs.com'
    return Client(config)


def _send_sms_verification(phone, challenge_id):
    if not ALIYUN_SMS_SIGN_NAME or not ALIYUN_SMS_TEMPLATE_CODE:
        raise RuntimeError('SMS sign or template is not configured')
    from alibabacloud_dypnsapi20170525 import models as sms_models
    from alibabacloud_tea_util import models as util_models

    sms_request = sms_models.SendSmsVerifyCodeRequest(
        scheme_name=ALIYUN_SMS_SCHEME_NAME,
        country_code='86',
        phone_number=phone,
        sign_name=ALIYUN_SMS_SIGN_NAME,
        template_code=ALIYUN_SMS_TEMPLATE_CODE,
        template_param='{"code":"##code##","min":"5"}',
        out_id=challenge_id,
        code_length=6,
        valid_time=SMS_CODE_TTL,
        duplicate_policy=1,
        interval=60,
        return_verify_code=False,
        code_type=1,
        auto_retry=1,
    )
    response = _sms_client().send_sms_verify_code_with_options(
        sms_request,
        util_models.RuntimeOptions(
            connect_timeout=5000,
            read_timeout=10000,
            autoretry=False,
            max_attempts=1,
        ),
    )
    body = getattr(response, 'body', None)
    if not body or not getattr(body, 'success', False) or getattr(body, 'code', '') != 'OK':
        raise RuntimeError('SMS provider rejected send request')


def _check_sms_verification(phone, verify_code, challenge_id):
    from alibabacloud_dypnsapi20170525 import models as sms_models
    from alibabacloud_tea_util import models as util_models

    sms_request = sms_models.CheckSmsVerifyCodeRequest(
        scheme_name=ALIYUN_SMS_SCHEME_NAME,
        country_code='86',
        phone_number=phone,
        out_id=challenge_id,
        verify_code=verify_code,
        case_auth_policy=1,
    )
    response = _sms_client().check_sms_verify_code_with_options(
        sms_request,
        util_models.RuntimeOptions(
            connect_timeout=5000,
            read_timeout=10000,
            autoretry=False,
            max_attempts=1,
        ),
    )
    body = getattr(response, 'body', None)
    model = getattr(body, 'model', None) if body else None
    if not body or not getattr(body, 'success', False) or getattr(body, 'code', '') != 'OK' or not model:
        raise RuntimeError('SMS provider rejected verification request')
    verify_result = getattr(model, 'verify_result', '')
    if verify_result == 'PASS':
        return True
    if verify_result == 'UNKNOWN':
        return False
    raise RuntimeError('SMS provider returned an unknown verification result')


def _send_email_verification(recipient, verify_code):
    if not SMTP_HOST or not SMTP_USERNAME or not SMTP_PASSWORD or not SMTP_FROM:
        raise RuntimeError('SMTP is not configured')
    message = EmailMessage()
    message['Subject'] = '智护星账号安全验证码'
    message['From'] = SMTP_FROM
    message['To'] = recipient
    message.set_content(
        f'你的验证码是：{verify_code}\n\n验证码 5 分钟内有效。'
        '如非本人操作，请忽略本邮件。'
    )
    smtp_class = smtplib.SMTP_SSL if SMTP_USE_SSL else smtplib.SMTP
    with smtp_class(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
        if not SMTP_USE_SSL:
            smtp.starttls()
        smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(message)


def _normalize_contact(kind, value):
    kind = (kind or '').strip().lower()
    value = (value or '').strip()
    if kind == 'phone' and re.fullmatch(r'1[3-9]\d{9}', value):
        return kind, value
    if kind == 'email' and len(value) <= 254 and re.fullmatch(
        r'[^\s@]+@[^\s@]+\.[^\s@]+', value
    ):
        return kind, value.lower()
    return '', ''


def bearer_required(function):
    @functools.wraps(function)
    def wrapper(*args, **kwargs):
        authorization = request.headers.get('Authorization', '')
        if not authorization.startswith('Bearer '):
            return jsonify({"success": False, "message": "未认证"}), 401
        token = authorization[7:].strip()
        if not token:
            return jsonify({"success": False, "message": "未认证"}), 401
        try:
            access_hash = _token_hash(token)
            conn = get_db()
            row = conn.execute(
                """
                SELECT session.username
                FROM t_session AS session
                JOIN t_user AS user ON user.username=session.username
                WHERE session.access_token_hash=? AND session.access_expires_at>?
                """,
                (access_hash, int(time.time())),
            ).fetchone()
            conn.close()
        except Exception as error:
            return _internal_error('bearer_auth', error)
        if not row:
            return jsonify({"success": False, "message": "会话无效或已过期"}), 401
        g.current_username = row['username']
        g.current_access_hash = access_hash
        return function(*args, **kwargs)
    return wrapper


# ─── 账号接口 ──────────────────────────────────────────────────

@app.route('/api/otp/send', methods=['POST'])
def api_send_otp():
    if not ALIYUN_SMS_ENABLED:
        return jsonify({"success": False, "message": "短信注册服务暂未开放"}), 503
    phone = ((request.get_json(silent=True) or {}).get('phone') or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        return jsonify({"success": False, "message": "手机号格式不正确"}), 400

    now = int(time.time())
    requester_ip = _client_ip()
    challenge_id = secrets.token_urlsafe(32)
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        month_start = int(
            datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
            .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            .timestamp()
        )
        conn.execute("DELETE FROM t_sms_challenge WHERE sent_at<?", (now - 40 * 24 * 60 * 60,))
        recent = conn.execute(
            "SELECT "
            "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_minute, "
            "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_hour, "
            "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_day, "
            "SUM(CASE WHEN requester_ip=? AND sent_at>=? THEN 1 ELSE 0 END) AS ip_hour, "
            # 全局预算只统计真正发出去的短信，blocked 行没有调用运营商
            "SUM(CASE WHEN sent_at>=? AND purpose<>'blocked' THEN 1 ELSE 0 END) AS total_day, "
            "SUM(CASE WHEN sent_at>=? AND purpose<>'blocked' THEN 1 ELSE 0 END) AS total_month "
            "FROM t_sms_challenge",
            (
                phone, now - 60,
                phone, now - 60 * 60,
                phone, now - 24 * 60 * 60,
                requester_ip, now - 60 * 60,
                now - 24 * 60 * 60,
                month_start,
            ),
        ).fetchone()
        contact_sms = conn.execute(
            """
            SELECT
              SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_day,
              SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_month
            FROM t_contact_challenge
            WHERE kind='phone'
            """,
            (now - 24 * 60 * 60, month_start),
        ).fetchone()
        if (
            (recent['phone_minute'] or 0) >= 1
            or (recent['phone_hour'] or 0) >= 5
            or (recent['phone_day'] or 0) >= 10
            or (recent['ip_hour'] or 0) >= 20
            or (recent['total_day'] or 0) + (contact_sms['total_day'] or 0)
            >= ALIYUN_SMS_DAILY_LIMIT
            or (recent['total_month'] or 0) + (contact_sms['total_month'] or 0)
            >= ALIYUN_SMS_MONTHLY_LIMIT
        ):
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码发送过于频繁，请稍后再试"}), 429
        if conn.execute(
            "SELECT 1 FROM t_user WHERE username=? OR phone=?", (phone, phone)
        ).fetchone():
            conn.execute(
                """
                INSERT INTO t_sms_challenge
                    (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
                VALUES (?, ?, 'blocked', ?, ?, ?)
                """,
                (challenge_hash, phone, requester_ip, now, now + SMS_CODE_TTL),
            )
            conn.commit()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "该手机号已注册"}), 409
        conn.execute(
            """
            INSERT INTO t_sms_challenge
                (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
            VALUES (?, ?, 'register', ?, ?, ?)
            """,
            (challenge_hash, phone, requester_ip, now, now + SMS_CODE_TTL),
        )
        conn.commit()
        conn.close()
        conn = None

        _send_sms_verification(phone, challenge_id)
        return jsonify({
            "success": True,
            "message": "验证码已发送",
            "challengeId": challenge_id,
            "expiresIn": SMS_CODE_TTL,
        })
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        return _internal_error('api_send_otp', error)


def _sms_send_blocked(conn, phone, requester_ip, now):
    """短信频控与预算检查，返回 True 表示应拒绝本次发送。"""
    month_start = int(
        datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    recent = conn.execute(
        "SELECT "
        "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_minute, "
        "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_hour, "
        "SUM(CASE WHEN phone=? AND sent_at>=? THEN 1 ELSE 0 END) AS phone_day, "
        "SUM(CASE WHEN requester_ip=? AND sent_at>=? THEN 1 ELSE 0 END) AS ip_hour, "
        # 全局预算只统计真正发出去的短信，blocked 行没有调用运营商
        "SUM(CASE WHEN sent_at>=? AND purpose<>'blocked' THEN 1 ELSE 0 END) AS total_day, "
        "SUM(CASE WHEN sent_at>=? AND purpose<>'blocked' THEN 1 ELSE 0 END) AS total_month "
        "FROM t_sms_challenge",
        (
            phone, now - 60,
            phone, now - 60 * 60,
            phone, now - 24 * 60 * 60,
            requester_ip, now - 60 * 60,
            now - 24 * 60 * 60,
            month_start,
        ),
    ).fetchone()
    contact_sms = conn.execute(
        """
        SELECT
          SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_day,
          SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_month
        FROM t_contact_challenge
        WHERE kind='phone'
        """,
        (now - 24 * 60 * 60, month_start),
    ).fetchone()
    return (
        (recent['phone_minute'] or 0) >= 1
        or (recent['phone_hour'] or 0) >= 5
        or (recent['phone_day'] or 0) >= 10
        or (recent['ip_hour'] or 0) >= 20
        or (recent['total_day'] or 0) + (contact_sms['total_day'] or 0) >= ALIYUN_SMS_DAILY_LIMIT
        or (recent['total_month'] or 0) + (contact_sms['total_month'] or 0) >= ALIYUN_SMS_MONTHLY_LIMIT
    )


@app.route('/api/password/otp/send', methods=['POST'])
def api_send_reset_otp():
    """忘记密码：向已注册手机号发送短信验证码。"""
    if not ALIYUN_SMS_ENABLED:
        return jsonify({"success": False, "message": "短信服务暂未开放"}), 503
    phone = ((request.get_json(silent=True) or {}).get('phone') or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        return jsonify({"success": False, "message": "手机号格式不正确"}), 400
    now = int(time.time())
    requester_ip = _client_ip()
    challenge_id = secrets.token_urlsafe(32)
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        conn.execute("DELETE FROM t_sms_challenge WHERE sent_at<?", (now - 40 * 24 * 60 * 60,))
        if _sms_send_blocked(conn, phone, requester_ip, now):
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码发送过于频繁，请稍后再试"}), 429
        registered = conn.execute(
            "SELECT username FROM t_user WHERE username=? OR phone=?", (phone, phone)
        ).fetchone()
        if not registered:
            # 记一条 blocked，让枚举未注册号码同样消耗频控额度
            conn.execute(
                """
                INSERT INTO t_sms_challenge
                    (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
                VALUES (?, ?, 'blocked', ?, ?, ?)
                """,
                (challenge_hash, phone, requester_ip, now, now + SMS_CODE_TTL),
            )
            conn.commit()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "该手机号尚未注册"}), 404
        conn.execute(
            """
            INSERT INTO t_sms_challenge
                (challenge_hash, phone, purpose, requester_ip, sent_at, expires_at)
            VALUES (?, ?, 'reset', ?, ?, ?)
            """,
            (challenge_hash, phone, requester_ip, now, now + SMS_CODE_TTL),
        )
        conn.commit()
        conn.close()
        conn = None
        _send_sms_verification(phone, challenge_id)
        return jsonify({
            "success": True,
            "message": "验证码已发送",
            "challengeId": challenge_id,
            "expiresIn": SMS_CODE_TTL,
        })
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        return _internal_error('api_send_reset_otp', error)


@app.route('/api/password/otp/verify', methods=['POST'])
def api_verify_reset_otp():
    """忘记密码第二步：校验短信验证码。通过后该 challenge 才允许用于设置新密码。"""
    if not ALIYUN_SMS_ENABLED:
        return jsonify({"success": False, "message": "短信服务暂未开放"}), 503
    d = request.get_json(silent=True) or {}
    phone = (d.get('phone') or '').strip()
    verify_code = (d.get('verifyCode') or '').strip()
    challenge_id = (d.get('challengeId') or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        return jsonify({"success": False, "message": "手机号格式不正确"}), 400
    if not re.fullmatch(r'\d{4,8}', verify_code):
        return jsonify({"success": False, "message": "验证码格式不正确"}), 400
    if len(challenge_id) < 32 or len(challenge_id) > 128:
        return jsonify({"success": False, "message": "验证码会话无效"}), 400
    now = int(time.time())
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        challenge = conn.execute(
            """
            SELECT challenge_hash
            FROM t_sms_challenge
            WHERE challenge_hash=? AND phone=? AND purpose='reset'
              AND expires_at>? AND failed_attempts<?
              AND (checking_at IS NULL OR checking_at<?) AND consumed_at IS NULL
            """,
            (challenge_hash, phone, now, SMS_MAX_ATTEMPTS, now - 30),
        ).fetchone()
        if not challenge:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "验证码会话无效或已过期"}), 400
        conn.execute(
            "UPDATE t_sms_challenge SET checking_at=? WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        conn.commit()
        conn.close()
        conn = None
        verified = _check_sms_verification(phone, verify_code, challenge_id)
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        if not verified:
            conn.execute(
                """
                UPDATE t_sms_challenge
                SET failed_attempts=failed_attempts+1, checking_at=NULL
                WHERE challenge_hash=? AND checking_at=? AND consumed_at IS NULL
                """,
                (challenge_hash, now),
            )
            conn.commit()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码错误"}), 400
        # 验证通过：标记为已验证，并留出填写新密码的时间窗
        cursor = conn.execute(
            """
            UPDATE t_sms_challenge
            SET purpose='reset_verified', checking_at=NULL, expires_at=?
            WHERE challenge_hash=? AND checking_at=? AND consumed_at IS NULL
            """,
            (now + PASSWORD_RESET_WINDOW, challenge_hash, now),
        )
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码会话已被使用"}), 400
        conn.commit()
        conn.close()
        conn = None
        return jsonify({
            "success": True,
            "message": "验证通过",
            "expiresIn": PASSWORD_RESET_WINDOW,
        })
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        return _internal_error('api_verify_reset_otp', error)


@app.route('/api/password/reset', methods=['POST'])
def api_reset_password():
    """忘记密码第三步：凭已验证的 challenge 设置新密码，并踢掉该账号全部会话。"""
    d = request.get_json(silent=True) or {}
    phone = (d.get('phone') or '').strip()
    password = (d.get('passwordHash') or '').strip()
    challenge_id = (d.get('challengeId') or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        return jsonify({"success": False, "message": "手机号格式不正确"}), 400
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > 128:
        return jsonify({
            "success": False,
            "message": f"密码长度应为 {PASSWORD_MIN_LENGTH} 到 128 位",
        }), 400
    if len(challenge_id) < 32 or len(challenge_id) > 128:
        return jsonify({"success": False, "message": "验证码会话无效"}), 400
    now = int(time.time())
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        challenge = conn.execute(
            """
            SELECT challenge_hash FROM t_sms_challenge
            WHERE challenge_hash=? AND phone=? AND purpose='reset_verified'
              AND expires_at>? AND consumed_at IS NULL
            """,
            (challenge_hash, phone, now),
        ).fetchone()
        if not challenge:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "请先完成手机号验证"}), 400
        row = conn.execute(
            "SELECT username, password_hash FROM t_user WHERE username=? OR phone=?",
            (phone, phone),
        ).fetchone()
        if not row:
            conn.execute(
                "UPDATE t_sms_challenge SET consumed_at=? WHERE challenge_hash=?",
                (now, challenge_hash),
            )
            conn.commit()
            conn.close()
            return jsonify({"success": False, "message": "该手机号尚未注册"}), 404
        # 与原密码相同时不消耗验证会话，用户改个密码就能直接重试
        if verify_password(row['password_hash'], password):
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "新密码不能与原密码相同"}), 400
        conn.execute(
            "UPDATE t_user SET password_hash=? WHERE username=?",
            (hash_password(password), row['username']),
        )
        # 重置后强制该账号在所有设备上重新登录
        conn.execute("DELETE FROM t_session WHERE username=?", (row['username'],))
        conn.execute(
            "UPDATE t_sms_challenge SET consumed_at=? WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        conn.commit()
        conn.close()
        conn = None
        return jsonify({"success": True, "message": "密码已重置，请用新密码登录"})
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        return _internal_error('api_reset_password', error)


@app.route('/api/contact/otp/send', methods=['POST'])
@bearer_required
def api_send_contact_otp():
    d = request.get_json(silent=True) or {}
    kind, value = _normalize_contact(d.get('kind'), d.get('value'))
    if not kind:
        return jsonify({"success": False, "message": "联系方式格式不正确"}), 400
    now = int(time.time())
    # 与 /api/otp/send 的月度口径保持一致，都按 UTC+8 的自然月切分
    month_start = int(
        datetime.fromtimestamp(now, timezone(timedelta(hours=8)))
        .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    requester_ip = _client_ip()
    challenge_id = secrets.token_urlsafe(32)
    challenge_hash = _token_hash(challenge_id)
    verify_code = f'{secrets.randbelow(1000000):06d}' if kind == 'email' else ''
    code_hash = _token_hash(challenge_id + ':' + verify_code) if verify_code else None
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        column = 'phone' if kind == 'phone' else 'email'
        owner = conn.execute(
            f"SELECT username FROM t_user WHERE {column}=? AND username<>?",
            (value, g.current_username),
        ).fetchone()
        if owner:
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "该联系方式已被其他账号使用"}), 409
        if kind == 'phone' and not ALIYUN_SMS_ENABLED:
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "短信验证码服务暂未开放"}), 503
        if kind == 'email' and not EMAIL_OTP_ENABLED:
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "邮箱验证码服务暂未开放"}), 503

        conn.execute(
            "DELETE FROM t_contact_challenge WHERE sent_at<?",
            (now - 40 * 24 * 60 * 60,),
        )
        recent = conn.execute(
            """
            SELECT
              SUM(CASE WHEN kind=? AND value=? AND sent_at>=? THEN 1 ELSE 0 END) AS value_minute,
              SUM(CASE WHEN kind=? AND value=? AND sent_at>=? THEN 1 ELSE 0 END) AS value_hour,
              SUM(CASE WHEN requester_ip=? AND sent_at>=? THEN 1 ELSE 0 END) AS ip_hour,
              SUM(CASE WHEN kind=? AND sent_at>=? THEN 1 ELSE 0 END) AS kind_day,
              SUM(CASE WHEN kind=? AND sent_at>=? THEN 1 ELSE 0 END) AS kind_month
            FROM t_contact_challenge
            """,
            (
                kind, value, now - 60,
                kind, value, now - 60 * 60,
                requester_ip, now - 60 * 60,
                kind, now - 24 * 60 * 60,
                kind, month_start,
            ),
        ).fetchone()
        registration_sms = conn.execute(
            """
            SELECT
              SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_day,
              SUM(CASE WHEN sent_at>=? THEN 1 ELSE 0 END) AS total_month
            FROM t_sms_challenge
            """,
            (now - 24 * 60 * 60, month_start),
        ).fetchone()
        budget_exhausted = (
            (recent['kind_day'] or 0) + (registration_sms['total_day'] or 0)
            >= ALIYUN_SMS_DAILY_LIMIT
            or (recent['kind_month'] or 0) + (registration_sms['total_month'] or 0)
            >= ALIYUN_SMS_MONTHLY_LIMIT
        ) if kind == 'phone' else (recent['kind_day'] or 0) >= EMAIL_OTP_DAILY_LIMIT
        if (
            (recent['value_minute'] or 0) >= 1
            or (recent['value_hour'] or 0) >= 5
            or (recent['ip_hour'] or 0) >= 20
            or budget_exhausted
        ):
            conn.rollback()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码发送过于频繁，请稍后再试"}), 429

        conn.execute(
            """
            INSERT INTO t_contact_challenge
                (challenge_hash, username, kind, value, code_hash,
                 requester_ip, sent_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge_hash, g.current_username, kind, value, code_hash,
                requester_ip, now, now + SMS_CODE_TTL,
            ),
        )
        conn.commit()
        conn.close()
        conn = None

        if kind == 'phone':
            _send_sms_verification(value, challenge_id)
        else:
            _send_email_verification(value, verify_code)
        return jsonify({
            "success": True,
            "message": "验证码已发送",
            "challengeId": challenge_id,
            "expiresIn": SMS_CODE_TTL,
        })
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        return _internal_error('api_send_contact_otp', error)


@app.route('/api/contact/update', methods=['POST'])
@bearer_required
def api_update_contact():
    d = request.get_json(silent=True) or {}
    kind, value = _normalize_contact(d.get('kind'), d.get('value'))
    verify_code = (d.get('verifyCode') or '').strip()
    challenge_id = (d.get('challengeId') or '').strip()
    if not kind:
        return jsonify({"success": False, "message": "联系方式格式不正确"}), 400
    if not re.fullmatch(r'\d{4,8}', verify_code):
        return jsonify({"success": False, "message": "验证码格式不正确"}), 400
    if len(challenge_id) < 32 or len(challenge_id) > 128:
        return jsonify({"success": False, "message": "验证码会话无效"}), 400

    now = int(time.time())
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        challenge = conn.execute(
            """
            SELECT code_hash
            FROM t_contact_challenge
            WHERE challenge_hash=? AND username=? AND kind=? AND value=?
              AND expires_at>? AND failed_attempts<?
              AND (checking_at IS NULL OR checking_at<?) AND consumed_at IS NULL
            """,
            (
                challenge_hash, g.current_username, kind, value,
                now, SMS_MAX_ATTEMPTS, now - 30,
            ),
        ).fetchone()
        if not challenge:
            conn.rollback()
            return jsonify({"success": False, "message": "验证码会话无效或已过期"}), 400
        conn.execute(
            "UPDATE t_contact_challenge SET checking_at=? WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        conn.commit()
        conn.close()
        conn = None

        if kind == 'phone':
            verified = _check_sms_verification(value, verify_code, challenge_id)
        else:
            verified = hmac.compare_digest(
                challenge['code_hash'] or '',
                _token_hash(challenge_id + ':' + verify_code),
            )

        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        if not verified:
            conn.execute(
                """
                UPDATE t_contact_challenge
                SET failed_attempts=failed_attempts+1, checking_at=NULL
                WHERE challenge_hash=? AND consumed_at IS NULL
                """,
                (challenge_hash,),
            )
            conn.commit()
            return jsonify({"success": False, "message": "验证码不正确"}), 400

        column = 'phone' if kind == 'phone' else 'email'
        owner = conn.execute(
            f"SELECT username FROM t_user WHERE {column}=? AND username<>?",
            (value, g.current_username),
        ).fetchone()
        if owner:
            conn.rollback()
            return jsonify({"success": False, "message": "该联系方式已被其他账号使用"}), 409
        cursor = conn.execute(
            f"UPDATE t_user SET {column}=? WHERE username=?",
            (value, g.current_username),
        )
        if cursor.rowcount != 1:
            conn.rollback()
            return jsonify({"success": False, "message": "账号不存在"}), 404
        conn.execute(
            "UPDATE t_contact_challenge SET consumed_at=?, checking_at=NULL WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        conn.execute(
            "DELETE FROM t_session WHERE username=? AND access_token_hash<>?",
            (g.current_username, g.current_access_hash),
        )
        conn.commit()
        return jsonify({"success": True, "message": "联系方式已更新"})
    except Exception as error:
        if conn:
            conn.rollback()
        return _internal_error('api_update_contact', error)
    finally:
        if conn:
            conn.close()


@app.route('/api/register', methods=['POST'])
def api_register():
    if not ALIYUN_SMS_ENABLED:
        return jsonify({"success": False, "message": "注册服务暂未开放"}), 503
    d = request.get_json(silent=True) or {}
    phone = (d.get('phone') or '').strip()
    password = (d.get('passwordHash') or '').strip()
    verify_code = (d.get('verifyCode') or '').strip()
    challenge_id = (d.get('challengeId') or '').strip()
    nickname = (d.get('nickname') or '').strip()
    if not re.fullmatch(r'1[3-9]\d{9}', phone):
        return jsonify({"success": False, "message": "手机号格式不正确"}), 400
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > 128:
        return jsonify({
            "success": False,
            "message": f"密码长度应为 {PASSWORD_MIN_LENGTH} 到 128 位",
        }), 400
    if not re.fullmatch(r'\d{4,8}', verify_code):
        return jsonify({"success": False, "message": "验证码格式不正确"}), 400
    if len(challenge_id) < 32 or len(challenge_id) > 128:
        return jsonify({"success": False, "message": "验证码会话无效"}), 400
    if len(nickname) > 32:
        return jsonify({"success": False, "message": "昵称不能超过 32 个字符"}), 400

    now = int(time.time())
    challenge_hash = _token_hash(challenge_id)
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        challenge = conn.execute(
            """
            SELECT challenge_hash
            FROM t_sms_challenge
            WHERE challenge_hash=? AND phone=? AND purpose='register'
              AND expires_at>? AND failed_attempts<?
              AND (checking_at IS NULL OR checking_at<?) AND consumed_at IS NULL
            """,
            (challenge_hash, phone, now, SMS_MAX_ATTEMPTS, now - 30),
        ).fetchone()
        if not challenge:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "验证码会话无效或已过期"}), 400
        conn.execute(
            "UPDATE t_sms_challenge SET checking_at=? WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        conn.commit()
        conn.close()
        conn = None

        verified = _check_sms_verification(phone, verify_code, challenge_id)
        if not verified:
            conn = get_db()
            conn.execute(
                """
                UPDATE t_sms_challenge
                SET failed_attempts=failed_attempts+1, checking_at=NULL
                WHERE challenge_hash=? AND checking_at=? AND consumed_at IS NULL
                """,
                (challenge_hash, now),
            )
            conn.commit()
            conn.close()
            conn = None
            return jsonify({"success": False, "message": "验证码错误"}), 400

        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        challenge = conn.execute(
            """
            SELECT challenge_hash FROM t_sms_challenge
            WHERE challenge_hash=? AND phone=? AND checking_at=? AND consumed_at IS NULL
            """,
            (challenge_hash, phone, now),
        ).fetchone()
        if not challenge:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "验证码会话已被使用"}), 400
        if conn.execute(
            "SELECT 1 FROM t_user WHERE username=? OR phone=?", (phone, phone)
        ).fetchone():
            conn.execute(
                "UPDATE t_sms_challenge SET consumed_at=?, checking_at=NULL WHERE challenge_hash=?",
                (now, challenge_hash),
            )
            conn.commit()
            conn.close()
            return jsonify({"success": False, "message": "该手机号已注册"}), 409
        conn.execute(
            """
            INSERT INTO t_user
                (username, nickname, phone, password_hash, avatar_path, email, address, create_time)
            VALUES (?, ?, ?, ?, '', '', '', ?)
            """,
            (phone, nickname or f"用户{phone[-4:]}", phone, hash_password(password), now * 1000),
        )
        conn.execute(
            "UPDATE t_sms_challenge SET consumed_at=?, checking_at=NULL WHERE challenge_hash=?",
            (now, challenge_hash),
        )
        tokens = _new_session(conn, phone, now)
        user = conn.execute("SELECT * FROM t_user WHERE username=?", (phone,)).fetchone()
        conn.commit()
        conn.close()
        conn = None
        response = {
            "success": True,
            "message": "注册成功",
            "user": _user_json(user),
        }
        response.update(tokens)
        return jsonify(response)
    except Exception as error:
        if conn:
            conn.rollback()
            conn.close()
        try:
            retry = get_db()
            retry.execute(
                "UPDATE t_sms_challenge SET checking_at=NULL "
                "WHERE challenge_hash=? AND checking_at=? AND consumed_at IS NULL",
                (challenge_hash, now),
            )
            retry.commit()
            retry.close()
        except Exception:
            pass
        return _internal_error('api_register', error)


@app.route('/api/login', methods=['POST'])
def api_login():
    d = request.get_json(force=True) or {}
    username = (d.get('username') or '').strip()
    pwd_hash = (d.get('passwordHash') or '').strip()
    if not username or not pwd_hash:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM t_user WHERE username=? OR phone=? OR email=?", (username, username, username)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "账号不存在"})
        if not verify_password(row['password_hash'], pwd_hash):
            conn.close()
            return jsonify({"success": False, "message": "密码错误"})
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            "SELECT * FROM t_user WHERE username=?", (row['username'],)
        ).fetchone()
        if not row or not verify_password(row['password_hash'], pwd_hash):
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "账号或密码已变更"})
        if password_needs_rehash(row['password_hash']):
            conn.execute(
                "UPDATE t_user SET password_hash=? WHERE username=?",
                (hash_password(pwd_hash), row['username'])
            )
        tokens = _new_session(conn, row['username'])
        conn.commit()
        conn.close()
        response = {
            "success": True,
            "message": "登录成功",
            "user": _user_json(row),
        }
        response.update(tokens)
        return jsonify(response)
    except Exception as error:
        return _internal_error('api_login', error)


@app.route('/api/refresh', methods=['POST'])
def api_refresh():
    refresh_token = ((request.get_json(silent=True) or {}).get('refreshToken') or '').strip()
    if not refresh_token:
        return jsonify({"success": False, "message": "refreshToken 缺失"}), 400
    try:
        now = int(time.time())
        old_hash = _token_hash(refresh_token)
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            """
            SELECT session.username
            FROM t_session AS session
            JOIN t_user AS user ON user.username=session.username
            WHERE session.refresh_token_hash=? AND session.refresh_expires_at>?
            """,
            (old_hash, now),
        ).fetchone()
        if not row:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "刷新会话无效或已过期"}), 401
        conn.execute("DELETE FROM t_session WHERE refresh_token_hash=?", (old_hash,))
        tokens = _new_session(conn, row['username'], now)
        conn.commit()
        conn.close()
        response = {"success": True}
        response.update(tokens)
        return jsonify(response)
    except Exception as error:
        return _internal_error('api_refresh', error)


@app.route('/api/me', methods=['GET'])
@bearer_required
def api_me():
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM t_user WHERE username=?", (g.current_username,)
        ).fetchone()
        conn.close()
        if not row:
            return jsonify({"success": False, "message": "账号不存在"}), 404
        return jsonify({"success": True, "user": _user_json(row)})
    except Exception as error:
        return _internal_error('api_me', error)


@app.route('/api/avatar', methods=['GET', 'POST'])
@bearer_required
def api_avatar():
    conn = None
    try:
        conn = get_db()
        if request.method == 'GET':
            row = conn.execute(
                "SELECT avatar_data, avatar_mime, avatar_updated_at FROM t_user WHERE username=?",
                (g.current_username,),
            ).fetchone()
            conn.close()
            if not row:
                return jsonify({"success": False, "message": "账号不存在"}), 404
            if not row['avatar_data']:
                return jsonify({"success": False, "message": "未设置头像"}), 404
            return jsonify({
                "success": True,
                "message": "头像读取成功",
                "imageBase64": base64.b64encode(row['avatar_data']).decode('ascii'),
                "mimeType": row['avatar_mime'] or 'image/jpeg',
                "updatedAt": row['avatar_updated_at'] or 0,
            })

        d = request.get_json(silent=True) or {}
        encoded = (d.get('imageBase64') or '').strip()
        mime_type = (d.get('mimeType') or '').strip().lower()
        if mime_type != 'image/jpeg' or not encoded:
            conn.close()
            return jsonify({"success": False, "message": "仅支持 JPEG 头像"}), 400
        try:
            image_data = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError):
            conn.close()
            return jsonify({"success": False, "message": "头像数据无效"}), 400
        if (
            len(image_data) < 4
            or len(image_data) > MAX_AVATAR_BYTES
            or not image_data.startswith(b'\xff\xd8')
            or not image_data.endswith(b'\xff\xd9')
        ):
            conn.close()
            return jsonify({"success": False, "message": "头像文件无效或过大"}), 400
        updated_at = int(time.time())
        cursor = conn.execute(
            """
            UPDATE t_user
            SET avatar_data=?, avatar_mime=?, avatar_updated_at=?, avatar_path=''
            WHERE username=?
            """,
            (image_data, mime_type, updated_at, g.current_username),
        )
        conn.commit()
        conn.close()
        if cursor.rowcount != 1:
            return jsonify({"success": False, "message": "账号不存在"}), 404
        return jsonify({
            "success": True,
            "message": "头像已同步",
            "updatedAt": updated_at,
        })
    except Exception as error:
        return _internal_error('api_avatar', error)
    finally:
        if conn:
            conn.close()


@app.route('/api/logout', methods=['POST'])
@bearer_required
def api_logout():
    try:
        conn = get_db()
        conn.execute(
            "DELETE FROM t_session WHERE access_token_hash=?",
            (g.current_access_hash,),
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "已退出登录"})
    except Exception as error:
        return _internal_error('api_logout', error)


@app.route('/api/deleteUser', methods=['POST'])
@bearer_required
def api_delete_user():
    d = request.get_json(force=True) or {}
    pwd_hash = (d.get('passwordHash') or '').strip()
    if not pwd_hash:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT username, password_hash FROM t_user WHERE username=?",
            (g.current_username,)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "账号不存在"})
        if not verify_password(row['password_hash'], pwd_hash):
            conn.close()
            return jsonify({"success": False, "message": "密码错误"})
        conn.execute("DELETE FROM t_session WHERE username=?", (row['username'],))
        conn.execute("DELETE FROM t_user WHERE username=?", (row['username'],))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "账号已注销"})
    except Exception as error:
        return _internal_error('api_delete_user', error)


@app.route('/api/updateUser', methods=['POST'])
@bearer_required
def api_update_user():
    d = request.get_json(force=True) or {}
    field_map = {
        'nickname': 'nickname',
        'avatarPath': 'avatar_path',
        'address': 'address',
    }
    ignored_fields = {'username'}
    sensitive_fields = {'phone', 'email', 'passwordHash', 'newUsername'}
    if any(key not in field_map.keys() | ignored_fields | sensitive_fields for key in d):
        return jsonify({"success": False, "message": "包含不允许修改的字段"}), 400
    if any(
        key in d and d[key] is not None and str(d[key]).strip()
        for key in sensitive_fields
    ):
        return jsonify({"success": False, "message": "请使用专用敏感资料修改接口"}), 400
    updates = {}
    for app_key, db_col in field_map.items():
        if app_key in d and d[app_key] is not None:
            updates[db_col] = d[app_key]

    if not updates:
        return jsonify({"success": True, "message": "无需更新"})

    try:
        conn = get_db()
        set_clause = ', '.join(f"{col}=?" for col in updates.keys())
        values = list(updates.values()) + [g.current_username]
        cursor = conn.execute(
            f"UPDATE t_user SET {set_clause} WHERE username=?",
            values
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected == 0:
            return jsonify({"success": False, "message": "找不到对应账号"})
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as error:
        return _internal_error('api_update_user', error)


@app.route('/api/changePassword', methods=['POST'])
@bearer_required
def api_change_password():
    d = request.get_json(force=True) or {}
    old_hash = (d.get('oldPasswordHash') or '').strip()
    new_hash = (d.get('newPasswordHash') or '').strip()
    if not old_hash or not new_hash:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    conn = None
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute(
            "SELECT username, password_hash FROM t_user WHERE username=?",
            (g.current_username,)
        ).fetchone()
        if not row:
            conn.rollback()
            return jsonify({"success": False, "message": "账号不存在"})
        if not verify_password(row['password_hash'], old_hash):
            conn.rollback()
            return jsonify({"success": False, "message": "原密码不正确"})
        conn.execute(
            "UPDATE t_user SET password_hash=? WHERE username=?",
            (hash_password(new_hash), row['username'])
        )
        conn.execute("DELETE FROM t_session WHERE username=?", (row['username'],))
        conn.commit()
        return jsonify({"success": True, "message": "密码已更新"})
    except Exception as error:
        if conn:
            conn.rollback()
        return _internal_error('api_change_password', error)
    finally:
        if conn:
            conn.close()


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "coze-proxy", "time": int(time.time())})


class ModerationUnavailable(Exception):
    pass


def _local_crisis_response(text):
    crisis_terms = (
        '自杀', '自残', '不想活', '结束生命', '服药过量', '吞药', '中毒',
        '昏迷', '胸痛', '呼吸困难', '严重出血', '严重过敏',
    )
    if not any(term in text for term in crisis_terms):
        return ''
    return (
        '我很担心你现在的安全。若有立即危险、已经受伤或服药过量，请马上拨打 '
        '120 或 110，并尽快联系身边可信任的人陪着你；心理援助也可拨打 12356。'
        '这类紧急情况不要只依赖在线回复。'
    )


def _redact_sensitive_text(text):
    text = re.sub(r'(?<!\d)1\d{10}(?!\d)', '[手机号已隐藏]', text)
    text = re.sub(r'(?<!\w)[1-9]\d{16}[0-9Xx](?!\w)', '[身份证号已隐藏]', text)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱已隐藏]', text)


def _local_output_unsafe(text):
    unsafe_terms = (
        '自行停药', '立即停药', '保证治愈', '无需就医', '不用去医院',
        '替代医生诊断', '增加剂量', '减少剂量',
    )
    return any(term in text for term in unsafe_terms)


def _moderate_text(service, content):
    access_key_id = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_ID', '')
    access_key_secret = os.environ.get('ALIBABA_CLOUD_ACCESS_KEY_SECRET', '')
    if not access_key_id or not access_key_secret:
        raise ModerationUnavailable('missing credentials')
    try:
        from alibabacloud_green20220302.client import Client as GreenClient
        from alibabacloud_green20220302 import models as green_models
        from alibabacloud_tea_openapi import models as open_api_models
        from alibabacloud_tea_util import models as util_models

        config = open_api_models.Config(
            access_key_id=access_key_id,
            access_key_secret=access_key_secret,
        )
        config.endpoint = ALIYUN_MODERATION_ENDPOINT
        client = GreenClient(config)
        moderation_request = green_models.TextModerationPlusRequest(
            service=service,
            service_parameters=json.dumps({
                'content': _redact_sensitive_text(content),
                'dataId': secrets.token_hex(16),
            }, ensure_ascii=False),
        )
        response = client.text_moderation_plus_with_options(
            moderation_request,
            util_models.RuntimeOptions(connect_timeout=1000, read_timeout=3000),
        )
        body = response.body
        if getattr(body, 'code', None) != 200:
            raise ModerationUnavailable('provider rejected request')
        data = getattr(body, 'data', None)
        risk_level = getattr(data, 'risk_level', None)
        if risk_level not in ('high', 'medium', 'low', 'none'):
            raise ModerationUnavailable('invalid provider response')
        advice_items = getattr(data, 'advice', None) or []
        advice = getattr(advice_items[0], 'answer', '') if advice_items else ''
        return {'risk_level': risk_level, 'advice': advice}
    except ModerationUnavailable:
        raise
    except Exception as error:
        app.logger.error('[moderation] unavailable type=%s', type(error).__name__)
        raise ModerationUnavailable('provider unavailable') from error


@app.route('/ai/chat', methods=['POST'])
@bearer_required
def ai_chat():
    if not AI_RISK_CONTROL_READY:
        return jsonify({"error": "AI 风控尚未就绪"}), 503
    if not ALIYUN_MODERATION_ENABLED:
        return jsonify({"error": "内容安全检查尚未启用"}), 503
    try:
        data = request.get_json(force=True) or {}
        user_message = data.get('message', '').strip()
        context = data.get('context', {})

        if not user_message:
            return jsonify({"error": "message 不能为空"}), 400
        if len(user_message) > AI_MAX_MESSAGE_LENGTH:
            return jsonify({"error": "消息过长，请缩短后重试"}), 413

        crisis_reply = _local_crisis_response(user_message)
        if crisis_reply:
            return jsonify({
                "reply": crisis_reply,
                "model": "local-safety",
                "timestamp": int(time.time())
            })

        input_result = _moderate_text('llm_query_moderation', user_message)
        if input_result['advice']:
            return jsonify({
                "reply": input_result['advice'],
                "model": "aliyun-safety",
                "timestamp": int(time.time())
            })
        if input_result['risk_level'] in ('high', 'medium'):
            return jsonify({"error": "该问题暂时无法由 AI 助手处理"}), 422

        # ── 按用户选择的 AI 数据权限拼接监护上下文 ──────────────
        context_summary = _build_context_summary(context)
        if context_summary:
            full_text = f"[当前监护摘要]\n{context_summary}\n\n[家属提问]\n{user_message}"
        else:
            full_text = user_message

        # ── 官方文档要求的正确请求体格式 ─────────────────────────
        payload = {
            "content": {
                "query": {
                    "prompt": [
                        {
                            "type": "text",
                            "content": {
                                "text": full_text
                            }
                        }
                    ]
                }
            },
            "type": "query",
            "project_id": COZE_PROJECT_ID
        }

        headers = {
            "Authorization": f"Bearer {COZE_API_TOKEN}",
            "Content-Type": "application/json"
        }

        resp = requests.post(
            COZE_STREAM_URL,
            headers=headers,
            json=payload,
            timeout=60,
            stream=True
        )
        resp.raise_for_status()

        ai_reply = _parse_sse_response(resp)

        output_result = _moderate_text('llm_response_moderation', ai_reply)
        if output_result['risk_level'] in ('high', 'medium') or _local_output_unsafe(ai_reply):
            return jsonify({"error": "AI 回复未通过安全检查"}), 422

        return jsonify({
            "reply": ai_reply,
            "model": "coze-doubao",
            "timestamp": int(time.time())
        })

    except ModerationUnavailable:
        return jsonify({"error": "内容安全检查暂时不可用，请稍后重试"}), 503
    except requests.exceptions.Timeout:
        return jsonify({"error": "AI 服务响应超时，请稍后重试"}), 504
    except requests.exceptions.HTTPError as e:
        coze_status = e.response.status_code
        app.logger.error("[ai_chat] upstream HTTP status=%s", coze_status)
        return jsonify({"error": "AI 服务暂时不可用，请稍后重试"}), 502
    except Exception as e:
        app.logger.error("[ai_chat] internal error type=%s", type(e).__name__)
        return jsonify({"error": "服务内部错误，请稍后重试"}), 500


def _parse_sse_response(resp) -> str:
    """
    解析扣子编程 stream_run 的 SSE 响应。
    实测格式：
      event: message
      data: {"type":"answer","content":{"answer":"文字"},"finish":false}
    提取 type=="answer" 时的 content.answer，拼接完整回复。
    """
    result_parts = []
    for raw_line in resp.iter_lines(decode_unicode=True):
        if not raw_line or not raw_line.startswith("data:"):
            continue
        json_str = raw_line[5:].strip()
        if not json_str or json_str == "[DONE]":
            continue
        try:
            chunk = json.loads(json_str)
            msg_type = chunk.get("type", "")
            if msg_type == "message_start":
                continue
            if msg_type == "answer":
                content = chunk.get("content", {})
                answer = content.get("answer", "") if isinstance(content, dict) else ""
                if answer:
                    result_parts.append(answer)
            if chunk.get("finish") is True:
                break
        except json.JSONDecodeError:
            continue

    reply = "".join(result_parts).strip()
    return reply if reply else "抱歉，AI 助手暂时无法回复，请稍后重试"


def _build_context_summary(context: dict) -> str:
    """按 AI 数据权限构建监护摘要。"""
    access_level = context.get('accessLevel', 'privacy') if context else 'privacy'
    if not context or access_level == 'basic':
        return ""
    parts = []
    fall      = context.get('fallCount7d', 0)
    sedentary = context.get('sedentaryCount7d', 0)
    last_fall = context.get('lastFallDaysAgo', -1)
    online    = context.get('deviceOnline', False)
    parts.append(f"设备状态：{'在线监护中' if online else '离线'}")
    parts.append(f"近7天摔倒次数：{fall}次")
    if last_fall >= 0:
        parts.append(f"最近一次摔倒：{last_fall}天前" if last_fall > 0 else "最近一次摔倒：今天")
    parts.append(f"近7天久坐告警：{sedentary}次")
    if access_level == 'full':
        parts.append(f"设备连接：{'已连接' if context.get('deviceConnected', False) else '未连接'}")
        current_status = context.get('currentStatus', '')
        latest_fall = context.get('latestFallRecord', '')
        latest_sedentary = context.get('latestSedentaryRecord', '')
        if current_status:
            parts.append(f"当前监护状态：{current_status}")
        if latest_fall:
            parts.append(f"最近摔倒记录：{latest_fall}")
        if latest_sedentary:
            parts.append(f"最近久坐记录：{latest_sedentary}")
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 管理后台
# ═══════════════════════════════════════════════════════════════

@app.before_request
def disable_admin_by_default():
    if request.path.startswith('/admin') and not ADMIN_ENABLED:
        return jsonify({"success": False, "message": "not found"}), 404


def admin_required(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin_logged_in'):
            if request.path.startswith('/admin/api'):
                return jsonify({"error": "请先登录管理后台"}), 401
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login_page():
    if request.method == 'POST':
        pwd = (request.form.get('password') or '').strip()
        if secrets.compare_digest(pwd, ADMIN_PASSWORD):
            session.clear()
            session.permanent = True
            session['admin_logged_in'] = True
            return redirect(url_for('admin_panel'))
        return _admin_login_html('密码错误')
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_panel'))
    return _admin_login_html()


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login_page'))


def _admin_login_html(error=''):
    error_html = f'<div class="error">{error}</div>' if error else ''
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>管理后台 · 登录</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f0f2f5; display:flex; align-items:center; justify-content:center; min-height:100vh; }}
.login-card {{ background:#fff; padding:40px; border-radius:12px; box-shadow:0 2px 12px rgba(0,0,0,0.08); width:360px; }}
.login-card h2 {{ text-align:center; margin-bottom:24px; color:#1a2332; font-size:20px; }}
.login-card input {{ width:100%; padding:10px 14px; border:1px solid #d9d9d9; border-radius:6px; font-size:14px; outline:none; }}
.login-card input:focus {{ border-color:#1677ff; box-shadow:0 0 0 2px rgba(22,119,255,0.1); }}
.login-card button {{ width:100%; padding:10px; margin-top:16px; background:#1677ff; color:#fff; border:none; border-radius:6px; font-size:14px; cursor:pointer; }}
.login-card button:hover {{ background:#4096ff; }}
.error {{ color:#ff4d4f; font-size:13px; margin-bottom:12px; text-align:center; }}
</style>
</head>
<body>
<div class="login-card">
<h2>Guardian DB Admin</h2>
{error_html}
<form method="post">
<input type="password" name="password" placeholder="管理员密码" autofocus>
<button type="submit">登 录</button>
</form>
</div>
</body>
</html>'''


@app.route('/admin')
@admin_required
def admin_panel():
    return _ADMIN_HTML


# ─── Admin REST API ──────────────────────────────────────────────

@app.route('/admin/api/users', methods=['GET'])
@admin_required
def admin_list_users():
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT username, nickname, phone, avatar_path, email, address, create_time
            FROM t_user
            ORDER BY create_time DESC
        """).fetchall()
        conn.close()
        return jsonify({"success": True, "data": [dict(r) for r in rows]})
    except Exception as error:
        return _internal_error('admin_list_users', error)


@app.route('/admin/api/users', methods=['POST'])
@admin_required
def admin_create_user():
    d = request.get_json(force=True) or {}
    username = (d.get('username') or '').strip()
    password = (d.get('password') or '').strip()
    if not username or not password:
        return jsonify({"success": False, "message": "用户名和初始密码不能为空"}), 400
    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT username FROM t_user WHERE username=?", (username,)
        ).fetchone()
        if existing:
            conn.close()
            return jsonify({"success": False, "message": "用户名已存在"}), 409
        conn.execute("""
            INSERT INTO t_user (username, nickname, phone, password_hash, avatar_path, email, address, create_time)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            username,
            d.get('nickname') or '',
            d.get('phone') or '',
            hash_password(password),
            d.get('avatar_path') or '',
            d.get('email') or '',
            d.get('address') or '',
            d.get('create_time') or int(time.time() * 1000),
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "创建成功"})
    except Exception as error:
        return _internal_error('admin_create_user', error)


@app.route('/admin/api/users/<username>', methods=['PUT'])
@admin_required
def admin_update_user(username):
    d = request.get_json(force=True) or {}
    if 'password_hash' in d or 'password' in d:
        return jsonify({"success": False, "message": "管理后台不能读取或直接改写密码"}), 400
    field_map = {
        'nickname': 'nickname', 'phone': 'phone',
        'avatar_path': 'avatar_path',
        'email': 'email', 'address': 'address', 'newUsername': 'username',
    }
    updates = {}
    for app_key, db_col in field_map.items():
        if app_key in d and d[app_key] is not None:
            updates[db_col] = d[app_key]
    if not updates:
        return jsonify({"success": True, "message": "无需更新"})
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        set_clause = ', '.join(f"{col}=?" for col in updates.keys())
        values = list(updates.values()) + [username]
        cursor = conn.execute(
            f"UPDATE t_user SET {set_clause} WHERE username=?", values
        )
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "用户不存在"}), 404
        if 'newUsername' in d and updates['username'] != username:
            conn.execute("DELETE FROM t_session WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as error:
        return _internal_error('admin_update_user', error)


@app.route('/admin/api/users/<username>', methods=['DELETE'])
@admin_required
def admin_delete_user(username):
    try:
        conn = get_db()
        conn.execute('BEGIN IMMEDIATE')
        cursor = conn.execute("DELETE FROM t_user WHERE username=?", (username,))
        if cursor.rowcount == 0:
            conn.rollback()
            conn.close()
            return jsonify({"success": False, "message": "用户不存在"}), 404
        conn.execute("DELETE FROM t_session WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "已删除"})
    except Exception as error:
        return _internal_error('admin_delete_user', error)


# ─── Admin Panel HTML (SPA) ───────────────────────────────────────

_ADMIN_HTML = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Guardian DB Admin</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:#f0f2f5; color:#1a2332; min-height:100vh; }

/* Header */
.header { background:#fff; border-bottom:1px solid #e8e8e8; padding:0 24px; height:56px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:10; }
.header h1 { font-size:16px; font-weight:600; color:#1677ff; }
.header .info { font-size:13px; color:#8c8c8c; }
.header a { color:#ff4d4f; text-decoration:none; font-size:13px; margin-left:16px; }
.header a:hover { text-decoration:underline; }

/* Toolbar */
.toolbar { max-width:1200px; margin:20px auto 0; padding:0 24px; display:flex; gap:12px; align-items:center; }
.toolbar input { flex:1; max-width:300px; padding:8px 12px; border:1px solid #d9d9d9; border-radius:6px; font-size:13px; outline:none; }
.toolbar input:focus { border-color:#1677ff; box-shadow:0 0 0 2px rgba(22,119,255,0.1); }
.btn { padding:8px 16px; border:none; border-radius:6px; font-size:13px; cursor:pointer; font-weight:500; }
.btn-primary { background:#1677ff; color:#fff; }
.btn-primary:hover { background:#4096ff; }
.btn-danger { background:#fff; color:#ff4d4f; border:1px solid #ff4d4f; }
.btn-danger:hover { background:#fff1f0; }
.btn-sm { padding:4px 10px; font-size:12px; }

/* Table */
.table-wrap { max-width:1200px; margin:16px auto 40px; padding:0 24px; }
.table-wrap .card { background:#fff; border-radius:8px; box-shadow:0 1px 4px rgba(0,0,0,0.06); overflow:hidden; }
table { width:100%; border-collapse:collapse; font-size:13px; }
thead { background:#fafafa; }
th { padding:10px 14px; text-align:left; font-weight:500; color:#8c8c8c; border-bottom:1px solid #f0f0f0; white-space:nowrap; }
td { padding:10px 14px; border-bottom:1px solid #fafafa; color:#434343; }
tr:last-child td { border-bottom:none; }
tr:hover td { background:#fafafa; }
.col-addr { max-width:160px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.actions { display:flex; gap:6px; }
.empty { text-align:center; padding:60px 20px; color:#8c8c8c; font-size:14px; }

/* Toast */
.toast { position:fixed; top:20px; left:50%; transform:translateX(-50%); padding:10px 24px; border-radius:6px; font-size:13px; z-index:9999; animation:fadeIn 0.2s; }
.toast.success { background:#f6ffed; border:1px solid #b7eb8f; color:#389e0d; }
.toast.error { background:#fff2f0; border:1px solid #ffccc7; color:#cf1322; }
@keyframes fadeIn { from { opacity:0; transform:translateX(-50%) translateY(-8px); } to { opacity:1; transform:translateX(-50%) translateY(0); } }

/* Modal */
.modal-overlay { display:none; position:fixed; inset:0; background:rgba(0,0,0,0.45); z-index:100; align-items:center; justify-content:center; }
.modal-overlay.show { display:flex; }
.modal { background:#fff; border-radius:10px; width:520px; max-height:85vh; overflow-y:auto; box-shadow:0 6px 30px rgba(0,0,0,0.15); }
.modal-header { padding:16px 20px; border-bottom:1px solid #f0f0f0; display:flex; align-items:center; justify-content:space-between; }
.modal-header h3 { font-size:16px; font-weight:600; }
.modal-close { background:none; border:none; font-size:18px; cursor:pointer; color:#8c8c8c; padding:4px; line-height:1; }
.modal-close:hover { color:#434343; }
.modal-body { padding:20px; }
.modal-footer { padding:12px 20px; border-top:1px solid #f0f0f0; display:flex; justify-content:flex-end; gap:8px; }
.form-group { margin-bottom:14px; }
.form-group label { display:block; font-size:13px; font-weight:500; color:#434343; margin-bottom:4px; }
.form-group input, .form-group textarea { width:100%; padding:8px 10px; border:1px solid #d9d9d9; border-radius:6px; font-size:13px; outline:none; font-family:inherit; }
.form-group input:focus, .form-group textarea:focus { border-color:#1677ff; box-shadow:0 0 0 2px rgba(22,119,255,0.1); }
.form-group textarea { resize:vertical; min-height:50px; }
.form-group .hint { font-size:11px; color:#8c8c8c; margin-top:2px; }
.required::after { content:" *"; color:#ff4d4f; }

/* Confirm dialog */
.confirm-text { font-size:14px; color:#434343; line-height:1.6; }
.confirm-text strong { color:#ff4d4f; }
</style>
</head>
<body>

<div class="header">
  <div style="display:flex;align-items:center;gap:12px;">
    <h1>Guardian DB Admin</h1>
    <span class="info" id="dbInfo"></span>
  </div>
  <div>
    <span class="info" id="rowCount"></span>
    <a href="/admin/logout">退出登录</a>
  </div>
</div>

<div class="toolbar">
  <input type="text" id="search" placeholder="搜索用户名 / 昵称 / 手机号 / 邮箱..." oninput="renderTable()">
  <button class="btn btn-primary" onclick="openAdd()">+ 添加用户</button>
</div>

<div class="table-wrap">
  <div class="card">
    <table>
      <thead>
        <tr>
          <th>用户名</th>
          <th>昵称</th>
          <th>手机号</th>
          <th>邮箱</th>
          <th>地址</th>
          <th>注册时间</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
</div>

<!-- Edit Modal -->
<div class="modal-overlay" id="editModal">
  <div class="modal">
    <div class="modal-header">
      <h3 id="modalTitle">编辑用户</h3>
      <button class="modal-close" onclick="closeModal()">&times;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="editOriginalUsername">
      <div class="form-group">
        <label class="required">用户名</label>
        <input type="text" id="editUsername" placeholder="唯一标识，不可与已有用户重复">
      </div>
      <div class="form-group">
        <label>昵称</label>
        <input type="text" id="editNickname">
      </div>
      <div class="form-group">
        <label>手机号</label>
        <input type="text" id="editPhone">
      </div>
      <div class="form-group">
        <label>邮箱</label>
        <input type="text" id="editEmail">
      </div>
      <div class="form-group">
        <label>地址</label>
        <textarea id="editAddress" rows="2"></textarea>
      </div>
      <div class="form-group" id="passwordGroup">
        <label>初始密码</label>
        <input type="password" id="editPassword" autocomplete="new-password">
        <div class="hint">仅创建账号时使用，后台不会显示或回传已存密码</div>
      </div>
      <div class="form-group">
        <label>头像路径</label>
        <input type="text" id="editAvatarPath">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn" style="background:#f5f5f5;color:#434343;" onclick="closeModal()">取消</button>
      <button class="btn btn-primary" id="modalSaveBtn" onclick="saveUser()">保存</button>
    </div>
  </div>
</div>

<!-- Delete Confirm Modal -->
<div class="modal-overlay" id="deleteModal">
  <div class="modal" style="width:400px;">
    <div class="modal-header">
      <h3>确认删除</h3>
      <button class="modal-close" onclick="closeDeleteModal()">&times;</button>
    </div>
    <div class="modal-body">
      <div class="confirm-text">确定要删除用户 <strong id="deleteUsername"></strong> 吗？此操作不可撤销。</div>
    </div>
    <div class="modal-footer">
      <button class="btn" style="background:#f5f5f5;color:#434343;" onclick="closeDeleteModal()">取消</button>
      <button class="btn btn-danger" id="deleteConfirmBtn" onclick="confirmDelete()">确认删除</button>
    </div>
  </div>
</div>

<script>
let allUsers = [];
let editMode = 'add'; // 'add' | 'edit'
let deleteTarget = null;

async function loadUsers() {
  try {
    const resp = await fetch('/admin/api/users');
    const data = await resp.json();
    if (!data.success) { showToast(data.message, 'error'); return; }
    allUsers = data.data;
    document.getElementById('rowCount').textContent = allUsers.length + ' 条记录';
    renderTable();
  } catch (e) {
    showToast('加载失败: ' + e.message, 'error');
  }
}

function renderTable() {
  const q = (document.getElementById('search').value || '').toLowerCase();
  const filtered = allUsers.filter(u => {
    if (!q) return true;
    return ['username','nickname','phone','email'].some(k => (u[k]||'').toLowerCase().includes(q));
  });

  const tbody = document.getElementById('tbody');
  if (filtered.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">' + (q ? '无匹配结果' : '暂无数据，点击「添加用户」开始') + '</td></tr>';
    return;
  }

  tbody.innerHTML = filtered.map(u => {
    const time = u.create_time ? new Date(u.create_time).toLocaleString('zh-CN') : '-';
    return `<tr>
      <td><strong>${esc(u.username)}</strong></td>
      <td>${esc(u.nickname || '-')}</td>
      <td>${esc(u.phone || '-')}</td>
      <td>${esc(u.email || '-')}</td>
      <td><div class="col-addr" title="${escAttr(u.address || '')}">${esc(u.address || '-')}</div></td>
      <td>${time}</td>
      <td>
        <div class="actions">
          <button class="btn btn-primary btn-sm" onclick="openEdit('${escAttr(u.username)}')">编辑</button>
          <button class="btn btn-danger btn-sm" onclick="openDelete('${escAttr(u.username)}')">删除</button>
        </div>
      </td>
    </tr>`;
  }).join('');
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function escAttr(s) {
  return s.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function findUser(username) {
  return allUsers.find(u => u.username === username);
}

// ── Add ──
function openAdd() {
  editMode = 'add';
  document.getElementById('modalTitle').textContent = '添加用户';
  document.getElementById('modalSaveBtn').textContent = '创建';
  document.getElementById('editOriginalUsername').value = '';
  document.getElementById('editUsername').value = '';
  document.getElementById('editUsername').readOnly = false;
  document.getElementById('editNickname').value = '';
  document.getElementById('editPhone').value = '';
  document.getElementById('editEmail').value = '';
  document.getElementById('editAddress').value = '';
  document.getElementById('editPassword').value = '';
  document.getElementById('passwordGroup').style.display = '';
  document.getElementById('editAvatarPath').value = '';
  document.getElementById('editModal').classList.add('show');
}

// ── Edit ──
function openEdit(username) {
  const u = findUser(username);
  if (!u) return;
  editMode = 'edit';
  document.getElementById('modalTitle').textContent = '编辑用户';
  document.getElementById('modalSaveBtn').textContent = '保存';
  document.getElementById('editOriginalUsername').value = u.username;
  document.getElementById('editUsername').value = u.username;
  document.getElementById('editUsername').readOnly = true;
  document.getElementById('editNickname').value = u.nickname || '';
  document.getElementById('editPhone').value = u.phone || '';
  document.getElementById('editEmail').value = u.email || '';
  document.getElementById('editAddress').value = u.address || '';
  document.getElementById('editPassword').value = '';
  document.getElementById('passwordGroup').style.display = 'none';
  document.getElementById('editAvatarPath').value = u.avatar_path || '';
  document.getElementById('editModal').classList.add('show');
}

function closeModal() {
  document.getElementById('editModal').classList.remove('show');
}

async function saveUser() {
  const body = {
    nickname: document.getElementById('editNickname').value.trim(),
    phone: document.getElementById('editPhone').value.trim(),
    email: document.getElementById('editEmail').value.trim(),
    address: document.getElementById('editAddress').value.trim(),
    avatar_path: document.getElementById('editAvatarPath').value.trim(),
  };

  if (editMode === 'add') {
    body.username = document.getElementById('editUsername').value.trim();
    body.password = document.getElementById('editPassword').value;
    if (!body.username) { showToast('用户名不能为空', 'error'); return; }
    if (!body.password) { showToast('初始密码不能为空', 'error'); return; }
    try {
      const resp = await fetch('/admin/api/users', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (!data.success) { showToast(data.message, 'error'); return; }
      showToast('创建成功', 'success');
      closeModal();
      loadUsers();
    } catch (e) {
      showToast('请求失败: ' + e.message, 'error');
    }
  } else {
    const origUsername = document.getElementById('editOriginalUsername').value;
    body.newUsername = document.getElementById('editUsername').value.trim();
    try {
      const resp = await fetch('/admin/api/users/' + encodeURIComponent(origUsername), {
        method: 'PUT',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      if (!data.success) { showToast(data.message, 'error'); return; }
      showToast('保存成功', 'success');
      closeModal();
      loadUsers();
    } catch (e) {
      showToast('请求失败: ' + e.message, 'error');
    }
  }
}

// ── Delete ──
function openDelete(username) {
  deleteTarget = username;
  document.getElementById('deleteUsername').textContent = username;
  document.getElementById('deleteModal').classList.add('show');
}

function closeDeleteModal() {
  deleteTarget = null;
  document.getElementById('deleteModal').classList.remove('show');
}

async function confirmDelete() {
  if (!deleteTarget) return;
  try {
    const resp = await fetch('/admin/api/users/' + encodeURIComponent(deleteTarget), {
      method: 'DELETE'
    });
    const data = await resp.json();
    if (!data.success) { showToast(data.message, 'error'); return; }
    showToast('已删除', 'success');
    closeDeleteModal();
    loadUsers();
  } catch (e) {
    showToast('请求失败: ' + e.message, 'error');
  }
}

// ── Toast ──
function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

// ── Init ──
loadUsers();
</script>
</body>
</html>'''


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8899, debug=False)
