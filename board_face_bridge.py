"""Cloud-only bridge for authenticated face enrollment on the edge board."""

import os
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


class BoardFaceUnavailable(RuntimeError):
    pass


class BoardFaceRejected(RuntimeError):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = build_opener(_NoRedirect)


def _settings():
    base = os.environ.get('BOARD_FACE_BASE_URL', '').rstrip('/')
    token = os.environ.get('BOARD_FACE_ADMIN_TOKEN', '')
    parsed = urlsplit(base)
    try:
        port = parsed.port
    except ValueError:
        raise BoardFaceUnavailable('board face bridge is not configured') from None
    if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost')
            or port is None or parsed.username or parsed.password
            or parsed.path or parsed.query or parsed.fragment or not token):
        raise BoardFaceUnavailable('board face bridge is not configured')
    return base, token


def enroll(name, user_id, image_bytes, mime_type):
    base, token = _settings()
    boundary = 'GuardianFace' + uuid.uuid4().hex
    chunks = []
    for key, value in (('name', name), ('user_id', user_id)):
        chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"'
                       f'\r\n\r\n{value}\r\n').encode('utf-8'))
    chunks.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                   f'filename="face.jpg"\r\nContent-Type: {mime_type}\r\n\r\n').encode('ascii'))
    chunks.extend((image_bytes, f'\r\n--{boundary}--\r\n'.encode('ascii')))
    body = b''.join(chunks)
    request = Request(
        base + '/api/face/enroll',
        data=body,
        method='POST',
        headers={
            'X-Admin-Token': token,
            'Content-Type': 'multipart/form-data; boundary=' + boundary,
        },
    )
    try:
        with _OPENER.open(request, timeout=30) as response:
            status_code = response.status
            raw = response.read(65537)
    except HTTPError as exc:
        status_code = exc.code
        raw = exc.read(65537)
    except (URLError, TimeoutError, OSError) as exc:
        raise BoardFaceUnavailable(type(exc).__name__) from None
    if len(raw) > 65536:
        raise BoardFaceUnavailable('board response too large')
    try:
        payload = json.loads(raw.decode('utf-8'))
    except (ValueError, TypeError, UnicodeError):
        raise BoardFaceUnavailable('invalid board response') from None
    if not isinstance(payload, dict):
        raise BoardFaceUnavailable('invalid board response')
    if status_code == 200 and payload.get('ok') is True:
        return payload
    if status_code in (400, 413):
        detail = payload.get('detail')
        message = detail if isinstance(detail, str) and 0 < len(detail) <= 200 else '人脸照片不符合要求'
        raise BoardFaceRejected(status_code, message)
    raise BoardFaceUnavailable('board rejected face enrollment')
