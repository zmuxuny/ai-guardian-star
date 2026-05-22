"""
wenxin_proxy.py — 智护星 AI 助手 · 扣子编程智能体中转服务
部署在华为云 ECS 上，避免 API Token 暴露在 App 端

依赖安装：pip install flask flask-cors requests
后台运行：nohup python3 wenxin_proxy.py > /var/log/wenxin_proxy.log 2>&1 &
"""

from flask import Flask, request, jsonify, session, redirect, url_for
from flask_cors import CORS
import requests
import time
import json
import sqlite3
import os
import functools

app = Flask(__name__)
CORS(app)

# ─── 管理后台配置 ──────────────────────────────────────────────
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')
app.secret_key = os.environ.get('FLASK_SECRET_KEY') or os.urandom(24).hex()
# ──────────────────────────────────────────────────────────────

# ─── 配置区 ────────────────────────────────────────────────────
COZE_STREAM_URL = "https://yhgh6fywzc.coze.site/stream_run"
COZE_PROJECT_ID = "7627479213733445658"
COZE_API_TOKEN  = "YOUR_COZE_TOKEN_HERE"   # 填入 pat_erXhx... 令牌

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
    conn.commit()
    return conn


# ─── 账号接口 ──────────────────────────────────────────────────

@app.route('/api/register', methods=['POST'])
def api_register():
    d = request.get_json(force=True) or {}
    username = (d.get('username') or '').strip()
    pwd_hash = (d.get('passwordHash') or '').strip()
    if not username or not pwd_hash:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    try:
        conn = get_db()
        existing = conn.execute(
            "SELECT username FROM t_user WHERE username=?", (username,)
        ).fetchone()
        if existing:
            # 已存在：返回成功（幂等，App 侧注册时可能重复调用）
            conn.close()
            return jsonify({"success": True, "message": "账号已存在"})
        conn.execute("""
            INSERT INTO t_user
                (username, nickname, phone, password_hash, avatar_path, email, address, create_time)
            VALUES (?,?,?,?,?,?,?,?)
        """, (
            username,
            d.get('nickname') or username,
            d.get('phone') or '',
            pwd_hash,
            d.get('avatarPath') or '',
            d.get('email') or '',
            d.get('address') or '',
            d.get('createTime') or int(time.time() * 1000),
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "注册成功"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
        conn.close()
        if not row:
            return jsonify({"success": False, "message": "账号不存在"})
        if row['password_hash'] != pwd_hash:
            return jsonify({"success": False, "message": "密码错误"})
        return jsonify({
            "success": True,
            "message": "登录成功",
            "user": {
                "username":     row['username'],
                "nickname":     row['nickname'] or '',
                "phone":        row['phone'] or '',
                "passwordHash": row['password_hash'],
                "avatarPath":   row['avatar_path'] or '',
                "email":        row['email'] or '',
                "address":      row['address'] or '',
                "createTime":   row['create_time'],
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/updateUser', methods=['POST'])
def api_update_user():
    """
    更新用户资料。

    查找规则：用客户端传来的 `username` 字段作为「柔性 lookup key」，
      WHERE username=? OR phone=? OR email=?
    这样无论 App 传的是注册时的昵称、当前的手机号、邮箱还是华为 HW_ ID，
    都能唯一定位云端记录（这些字段彼此互不重叠）。

    其它字段（nickname/phone/avatarPath/email/address/passwordHash）是要写入的新值。
    若客户端希望修改 username（即昵称改名），可显式传 `newUsername`。
    """
    d = request.get_json(force=True) or {}
    lookup = (d.get('username') or '').strip()
    if not lookup:
        return jsonify({"success": False, "message": "lookup key 缺失"}), 400

    field_map = {
        'nickname': 'nickname', 'phone': 'phone',
        'avatarPath': 'avatar_path', 'email': 'email',
        'address': 'address', 'passwordHash': 'password_hash',
        'newUsername': 'username',
    }
    updates = {}
    for app_key, db_col in field_map.items():
        if app_key in d and d[app_key] is not None and str(d[app_key]) != '':
            updates[db_col] = d[app_key]

    if not updates:
        return jsonify({"success": True, "message": "无需更新"})

    try:
        conn = get_db()
        set_clause = ', '.join(f"{col}=?" for col in updates.keys())
        values = list(updates.values()) + [lookup, lookup, lookup]
        cursor = conn.execute(
            f"UPDATE t_user SET {set_clause} WHERE username=? OR phone=? OR email=?",
            values
        )
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        if affected == 0:
            return jsonify({"success": False, "message": "找不到对应账号"})
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/api/changePassword', methods=['POST'])
def api_change_password():
    """
    修改密码：必须验证旧密码哈希后才允许写新密码。
    lookup 规则同 updateUser，username 字段允许传昵称/手机/邮箱/HW_ID。
    """
    d = request.get_json(force=True) or {}
    lookup = (d.get('username') or '').strip()
    old_hash = (d.get('oldPasswordHash') or '').strip()
    new_hash = (d.get('newPasswordHash') or '').strip()
    if not lookup or not old_hash or not new_hash:
        return jsonify({"success": False, "message": "参数缺失"}), 400
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT username, password_hash FROM t_user WHERE username=? OR phone=? OR email=?",
            (lookup, lookup, lookup)
        ).fetchone()
        if not row:
            conn.close()
            return jsonify({"success": False, "message": "账号不存在"})
        if row['password_hash'] != old_hash:
            conn.close()
            return jsonify({"success": False, "message": "原密码不正确"})
        conn.execute(
            "UPDATE t_user SET password_hash=? WHERE username=?",
            (new_hash, row['username'])
        )
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "密码已更新"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "ok", "service": "coze-proxy", "time": int(time.time())})


@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    try:
        data = request.get_json(force=True)
        user_message = data.get('message', '').strip()
        context = data.get('context', {})

        if not user_message:
            return jsonify({"error": "message 不能为空"}), 400

        # ── 把监护上下文摘要拼到消息里（脱敏，仅统计数据）────────
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

        return jsonify({
            "reply": ai_reply,
            "model": "coze-doubao",
            "timestamp": int(time.time())
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "AI 服务响应超时，请稍后重试"}), 504
    except requests.exceptions.HTTPError as e:
        coze_status = e.response.status_code
        coze_body = ""
        try:
            coze_body = e.response.text[:500]
        except Exception:
            pass
        app.logger.error(f"[ai_chat] Coze HTTP {coze_status}: {coze_body}")
        return jsonify({"error": f"扣子 API 错误: {coze_status}", "detail": coze_body}), 502
    except Exception as e:
        app.logger.error(f"[ai_chat] exception: {e}")
        return jsonify({"error": "服务内部错误，请稍后重试", "detail": str(e)}), 500


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
    """将健康统计数据构建为自然语言摘要（只传聚合统计，不含任何PII）"""
    if not context:
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
    return "\n".join(parts)


# ═══════════════════════════════════════════════════════════════
# 管理后台
# ═══════════════════════════════════════════════════════════════

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
        if pwd == ADMIN_PASSWORD:
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
        rows = conn.execute("SELECT * FROM t_user ORDER BY create_time DESC").fetchall()
        conn.close()
        return jsonify({"success": True, "data": [dict(r) for r in rows]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/admin/api/users', methods=['POST'])
@admin_required
def admin_create_user():
    d = request.get_json(force=True) or {}
    username = (d.get('username') or '').strip()
    if not username:
        return jsonify({"success": False, "message": "用户名不能为空"}), 400
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
            d.get('password_hash') or '',
            d.get('avatar_path') or '',
            d.get('email') or '',
            d.get('address') or '',
            d.get('create_time') or int(time.time() * 1000),
        ))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "创建成功"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/admin/api/users/<username>', methods=['PUT'])
@admin_required
def admin_update_user(username):
    d = request.get_json(force=True) or {}
    field_map = {
        'nickname': 'nickname', 'phone': 'phone',
        'password_hash': 'password_hash', 'avatar_path': 'avatar_path',
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
        set_clause = ', '.join(f"{col}=?" for col in updates.keys())
        values = list(updates.values()) + [username]
        cursor = conn.execute(
            f"UPDATE t_user SET {set_clause} WHERE username=?", values
        )
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": "用户不存在"}), 404
        return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/admin/api/users/<username>', methods=['DELETE'])
@admin_required
def admin_delete_user(username):
    try:
        conn = get_db()
        cursor = conn.execute("DELETE FROM t_user WHERE username=?", (username,))
        conn.commit()
        conn.close()
        if cursor.rowcount == 0:
            return jsonify({"success": False, "message": "用户不存在"}), 404
        return jsonify({"success": True, "message": "已删除"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
.col-hash { max-width:100px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-family:monospace; font-size:11px; color:#8c8c8c; }
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
          <th>密码哈希</th>
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
      <div class="form-group">
        <label>密码哈希</label>
        <input type="text" id="editPasswordHash">
        <div class="hint">⚠ 修改此项会导致用户无法登录，除非填入正确的哈希值</div>
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
    tbody.innerHTML = '<tr><td colspan="8" class="empty">' + (q ? '无匹配结果' : '暂无数据，点击「添加用户」开始') + '</td></tr>';
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
      <td><div class="col-hash" title="${escAttr(u.password_hash || '')}">${esc(u.password_hash ? u.password_hash.substring(0,16)+'...' : '-')}</div></td>
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
  document.getElementById('editPasswordHash').value = '';
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
  document.getElementById('editPasswordHash').value = u.password_hash || '';
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
    password_hash: document.getElementById('editPasswordHash').value.trim(),
    avatar_path: document.getElementById('editAvatarPath').value.trim(),
  };

  if (editMode === 'add') {
    body.username = document.getElementById('editUsername').value.trim();
    if (!body.username) { showToast('用户名不能为空', 'error'); return; }
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
    app.run(host='0.0.0.0', port=8899, debug=False)
