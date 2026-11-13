"""Authenticated cloud API for forwarding bounded face enrollment to the board."""

import hashlib
import os
import re

from flask import g, jsonify, request

import board_face_bridge as board_bridge
from mqtt_access import allowed_users


MAX_FACE_BYTES = 8 * 1024 * 1024
MAX_MULTIPART_BYTES = MAX_FACE_BYTES + 512 * 1024
ALLOWED_MIME_TYPES = {'image/jpeg', 'image/png'}


def account_face_id(username):
    if isinstance(username, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', username):
        return username
    digest = hashlib.sha256(str(username).encode('utf-8')).hexdigest()[:32]
    return 'acct_' + digest


def valid_face_name(name):
    return (isinstance(name, str) and 0 < len(name) <= 64 and name.strip() not in ('', '.', '..')
            and not any(char in name for char in ('/', '\\', '\x00'))
            and not any(ord(char) < 32 for char in name))


def register_face_routes(app, bearer_required):
    def authorized():
        users_file = os.environ.get('MQTT_USERS_FILE', '/etc/wenxin/mqtt-users.json')
        return g.current_username in allowed_users(users_file)

    @app.post('/api/face/enroll')
    @bearer_required
    def face_enroll():
        if not authorized():
            return jsonify(success=False, message='当前账号未获准管理监护设备'), 403
        if request.content_length is not None and request.content_length > MAX_MULTIPART_BYTES:
            return jsonify(success=False, message='图片不能超过 8 MiB'), 413

        name = request.form.get('name', '').strip()
        uploaded = request.files.get('file')
        if not valid_face_name(name):
            return jsonify(success=False, message='姓名无效'), 400
        if uploaded is None or uploaded.mimetype not in ALLOWED_MIME_TYPES:
            return jsonify(success=False, message='请选择 JPG 或 PNG 人脸照片'), 400

        image_bytes = uploaded.stream.read(MAX_FACE_BYTES + 1)
        if not image_bytes:
            return jsonify(success=False, message='上传文件为空'), 400
        if len(image_bytes) > MAX_FACE_BYTES:
            return jsonify(success=False, message='图片不能超过 8 MiB'), 413

        try:
            result = board_bridge.enroll(
                name, account_face_id(g.current_username), image_bytes, uploaded.mimetype)
        except board_bridge.BoardFaceRejected as exc:
            return jsonify(success=False, message=exc.message), exc.status_code
        except board_bridge.BoardFaceUnavailable:
            return jsonify(success=False, message='开发板人脸服务暂不可用，请稍后重试'), 503

        response = jsonify(
            success=True,
            message='人脸录入成功',
            recognitionStatus=result.get('recognition_status', ''),
            photoCount=result.get('photo_count'),
            hint=result.get('hint', ''),
        )
        response.headers['Cache-Control'] = 'no-store'
        return response
