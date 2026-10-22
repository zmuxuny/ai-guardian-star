"""Account-owned saved residences. No device permission or external map dependency."""
import math
import time
import sqlite3
from flask import request, jsonify, g

MAX_ADDRESSES = 20


def create_address_schema(conn):
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS t_saved_address (
        id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
        label TEXT NOT NULL, detail TEXT NOT NULL, latitude REAL, longitude REAL,
        is_default INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS idx_saved_address_owner ON t_saved_address(username);
      CREATE UNIQUE INDEX IF NOT EXISTS idx_saved_address_default
        ON t_saved_address(username) WHERE is_default=1;
      CREATE TRIGGER IF NOT EXISTS saved_address_delete_user AFTER DELETE ON t_user
        BEGIN DELETE FROM t_saved_address WHERE username=OLD.username; END;
    ''')


class AddressError(Exception):
    def __init__(self, message, status=400):
        self.message, self.status = message, status


def validate_address(data):
    label, detail = data.get('label'), data.get('detail')
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 24:
        raise AddressError('请填写1至24字的住处名称')
    if not isinstance(detail, str) or not 5 <= len(detail.strip()) <= 300:
        raise AddressError('请填写5至300字的详细地址')
    if any(ord(char) < 32 and char not in '\n\r\t' for char in label + detail):
        raise AddressError('地址包含无效字符')
    latitude, longitude = data.get('latitude'), data.get('longitude')
    if (latitude is None) != (longitude is None):
        raise AddressError('纬度和经度需要同时填写，或同时留空')
    for value, limit, name in ((latitude, 90, '纬度'), (longitude, 180, '经度')):
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or abs(value) > limit):
            raise AddressError(f'{name}范围无效')
    if type(data.get('isDefault', False)) is not bool:
        raise AddressError('默认地址设置无效')
    return label.strip(), detail.strip(), latitude, longitude


def _bootstrap(conn, owner):
    """Preserve the legacy single address as the first default residence, once."""
    if conn.execute('SELECT 1 FROM t_saved_address WHERE username=? LIMIT 1', (owner,)).fetchone():
        return
    user = conn.execute('SELECT address FROM t_user WHERE username=?', (owner,)).fetchone()
    if user and isinstance(user['address'], str) and user['address'].strip():
        now = int(time.time() * 1000)
        conn.execute('''INSERT INTO t_saved_address(username,label,detail,is_default,created_at,updated_at)
                        VALUES(?,?,?,1,?,?)''', (owner, '家庭', user['address'].strip(), now, now))


def _owned(conn, owner, data):
    address_id, version = data.get('id'), data.get('version')
    if type(address_id) is not int or address_id <= 0 or type(version) is not int or version <= 0:
        raise AddressError('地址标识无效')
    row = conn.execute('SELECT * FROM t_saved_address WHERE id=? AND username=?', (address_id, owner)).fetchone()
    if row is None:
        raise AddressError('地址不存在或已被删除', 404)
    if row['version'] != version:
        raise AddressError('地址已在其他页面更新，请刷新后再编辑', 409)
    return row


def _default(conn, owner, address_id, now):
    conn.execute('''UPDATE t_saved_address SET is_default=0,version=version+1,updated_at=?
                    WHERE username=? AND is_default=1 AND id<>?''', (now, owner, address_id))
    conn.execute('''UPDATE t_saved_address SET is_default=1,version=version+1,updated_at=?
                    WHERE username=? AND id=? AND is_default=0''', (now, owner, address_id))


def _snapshot(conn, owner):
    rows = conn.execute('SELECT * FROM t_saved_address WHERE username=? ORDER BY is_default DESC,updated_at DESC,id DESC',
                        (owner,)).fetchall()
    addresses = [{'id': row['id'], 'label': row['label'], 'detail': row['detail'],
                  'latitude': row['latitude'], 'longitude': row['longitude'],
                  'isDefault': bool(row['is_default']), 'version': row['version']} for row in rows]
    primary = next((item['detail'] for item in addresses if item['isDefault']), '')
    # Keep the old profile field compatible with the current default residence.
    conn.execute('UPDATE t_user SET address=? WHERE username=?', (primary, owner))
    return {'success': True, 'addresses': addresses, 'defaultAddress': primary}


def register_address_routes(app, bearer_required, get_db):
    def handle(action):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(success=False, message='请求格式无效'), 400
        owner = g.current_username  # Never accept an owner from the request body.
        conn = get_db()
        try:
            conn.execute('BEGIN IMMEDIATE')
            if not conn.execute('SELECT 1 FROM t_user WHERE username=?', (owner,)).fetchone():
                raise AddressError('账号状态已变化，请重新登录', 401)
            _bootstrap(conn, owner)
            now = int(time.time() * 1000)
            if action == 'save':
                values = validate_address(data)
                address_id = data.get('id')
                if address_id is not None:
                    row = _owned(conn, owner, data)
                    # Unticking the current default cannot leave a populated list without one.
                    conn.execute('''UPDATE t_saved_address SET label=?,detail=?,latitude=?,longitude=?,
                                    version=version+1,updated_at=? WHERE username=? AND id=?''',
                                 (*values, now, owner, row['id']))
                    address_id = row['id']
                else:
                    count = conn.execute('SELECT count(*) FROM t_saved_address WHERE username=?', (owner,)).fetchone()[0]
                    if count >= MAX_ADDRESSES:
                        raise AddressError('最多保存20个常用住处，请先删除不再使用的地址')
                    cursor = conn.execute('''INSERT INTO t_saved_address
                        (username,label,detail,latitude,longitude,created_at,updated_at) VALUES(?,?,?,?,?,?,?)''',
                                          (owner, *values, now, now))
                    address_id = cursor.lastrowid
                if data.get('isDefault', False) or not conn.execute(
                    'SELECT 1 FROM t_saved_address WHERE username=? AND is_default=1', (owner,)).fetchone():
                    _default(conn, owner, address_id, now)
            elif action == 'default':
                row = _owned(conn, owner, data)
                _default(conn, owner, row['id'], now)
            elif action == 'delete':
                row = _owned(conn, owner, data)
                conn.execute('DELETE FROM t_saved_address WHERE username=? AND id=?', (owner, row['id']))
                if row['is_default']:
                    replacement = conn.execute('SELECT id FROM t_saved_address WHERE username=? ORDER BY updated_at DESC,id DESC LIMIT 1',
                                               (owner,)).fetchone()
                    if replacement:
                        _default(conn, owner, replacement['id'], now)
            result = _snapshot(conn, owner)
            conn.commit()
            response = jsonify(result)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except AddressError as error:
            conn.rollback()
            return jsonify(success=False, message=error.message), error.status
        except sqlite3.Error:
            conn.rollback()
            app.logger.error('saved address storage operation failed')
            return jsonify(success=False, message='地址服务暂不可用，请稍后重试'), 503
        finally:
            conn.close()

    @app.post('/api/addresses/list')
    @bearer_required
    def address_list():
        return handle('list')

    @app.post('/api/addresses/save')
    @bearer_required
    def address_save():
        return handle('save')

    @app.post('/api/addresses/default')
    @bearer_required
    def address_default():
        return handle('default')

    @app.post('/api/addresses/delete')
    @bearer_required
    def address_delete():
        return handle('delete')
