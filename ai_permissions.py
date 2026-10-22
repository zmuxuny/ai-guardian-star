"""Account-owned AI consent and bounded, minimized model inputs."""
import re
import sqlite3
from flask import g, request, jsonify

LEVELS = ('basic', 'privacy', 'full')


class AiPermissionError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def create_ai_schema(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS t_ai_permission (
        username TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 0,
        access_level TEXT NOT NULL DEFAULT 'privacy', version INTEGER NOT NULL DEFAULT 1);
      CREATE TRIGGER IF NOT EXISTS ai_permission_delete_user AFTER DELETE ON t_user
        BEGIN DELETE FROM t_ai_permission WHERE username=OLD.username; END;
      CREATE TRIGGER IF NOT EXISTS ai_permission_rename_user AFTER UPDATE OF username ON t_user
        BEGIN UPDATE t_ai_permission SET username=NEW.username WHERE username=OLD.username; END;
    ''')


def read_permission(conn, username):
    if not conn.execute('SELECT 1 FROM t_user WHERE username=?', (username,)).fetchone():
        raise AiPermissionError('账号不存在或已退出', 401)
    row = conn.execute('SELECT * FROM t_ai_permission WHERE username=?', (username,)).fetchone()
    if row is None:
        return dict(enabled=False, accessLevel='privacy', version=0)
    return dict(enabled=bool(row['enabled']), accessLevel=row['access_level'], version=row['version'])


def require_permission(conn, username, version):
    policy = read_permission(conn, username)
    if not policy['enabled']:
        raise AiPermissionError('AI 助手已关闭，请在个人中心开启', 403)
    if type(version) is not int or version != policy['version']:
        raise AiPermissionError('AI 权限已变化，请重新发送问题', 409)
    return policy


def redact_sensitive_text(text):
    # Handles labels next to Chinese characters as well as plain identifiers.
    text = re.sub(r'(?<![A-Za-z0-9])[1-9]\d{16}[0-9Xx](?![A-Za-z0-9])', '[身份证号已隐藏]', text)
    text = re.sub(r'(?<!\d)(?:\+?86[ -]?)?1[3-9](?:[ -]?\d){9}(?!\d)', '[手机号已隐藏]', text)
    return re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱已隐藏]', text)


def validate_context(context, access_level):
    if not isinstance(context, dict) or context.get('accessLevel') not in LEVELS:
        raise AiPermissionError('监护数据权限格式无效')
    if context['accessLevel'] != access_level:
        raise AiPermissionError('AI 权限已变化，请重新发送问题', 409)
    result = dict(accessLevel=access_level)
    if access_level == 'basic':
        return result
    for key, lower, upper in (('fallCount7d', 0, 1000000), ('sedentaryCount7d', 0, 1000000),
                              ('lastFallDaysAgo', -1, 36500)):
        value = context.get(key, lower)
        if type(value) is not int or not lower <= value <= upper:
            raise AiPermissionError('监护统计格式无效，请刷新后重试')
        result[key] = value
    for key in ('deviceOnline', 'deviceConnected') if access_level == 'full' else ('deviceOnline',):
        value = context.get(key, False)
        if type(value) is not bool:
            raise AiPermissionError('设备状态格式无效')
        result[key] = value
    if access_level == 'full':
        for key, limit in (('currentStatus', 500), ('latestFallRecord', 40), ('latestSedentaryRecord', 40)):
            value = context.get(key, '')
            if not isinstance(value, str) or len(value) > limit:
                raise AiPermissionError('监护状态内容过长或格式无效')
            result[key] = redact_sensitive_text(value)
    return result


def validate_history(history):
    if not isinstance(history, list) or len(history) > 20:
        raise AiPermissionError('对话记录格式无效或过长')
    result = []
    total = 0
    for item in history:
        if not isinstance(item, dict) or item.get('role') not in ('user', 'assistant'):
            raise AiPermissionError('对话角色无效')
        content = item.get('content')
        if not isinstance(content, str) or len(content) > 2000:
            raise AiPermissionError('对话内容格式无效或过长')
        total += len(content)
        if total > 16000:
            raise AiPermissionError('对话记录过长，请开始新的对话', 413)
        result.append(dict(role=item['role'], content=redact_sensitive_text(content)))
    return result


def register_ai_permission_routes(app, bearer_required, get_db):
    @app.post('/api/ai/settings/read')
    @bearer_required
    def ai_settings_read():
        conn = get_db()
        try:
            return jsonify(success=True, settings=read_permission(conn, g.current_username))
        except AiPermissionError as error:
            return jsonify(success=False, message=error.message), error.status
        finally:
            conn.close()

    @app.post('/api/ai/settings/save')
    @bearer_required
    def ai_settings_save():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or type(data.get('enabled')) is not bool \
                or data.get('accessLevel') not in LEVELS or type(data.get('version')) is not int:
            return jsonify(success=False, message='AI 权限设置格式无效'), 400
        conn = get_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            old = read_permission(conn, g.current_username)
            if old['version'] != data['version']:
                raise AiPermissionError('其他设备已更新 AI 权限，请刷新后重试', 409)
            version = old['version'] + 1
            conn.execute('''INSERT INTO t_ai_permission(username,enabled,access_level,version) VALUES(?,?,?,?)
                ON CONFLICT(username) DO UPDATE SET enabled=excluded.enabled,
                  access_level=excluded.access_level,version=excluded.version''',
                (g.current_username, int(data['enabled']), data['accessLevel'], version))
            conn.commit()
            return jsonify(success=True, settings=dict(enabled=data['enabled'],
                           accessLevel=data['accessLevel'], version=version))
        except AiPermissionError as error:
            conn.rollback()
            return jsonify(success=False, message=error.message), error.status
        except sqlite3.Error:
            conn.rollback()
            app.logger.error('[ai_settings] persistence failed')
            return jsonify(success=False, message='权限保存失败，请重试'), 500
        finally:
            conn.close()

    @app.after_request
    def ai_no_store(response):
        if request.path.startswith('/api/ai/') or request.path == '/ai/chat':
            response.headers['Cache-Control'] = 'private, no-store'
        return response
