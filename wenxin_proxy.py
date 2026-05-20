"""
wenxin_proxy.py — 智护星 AI 助手 · 扣子编程智能体中转服务
部署在华为云 ECS 上，避免 API Token 暴露在 App 端

依赖安装：pip install flask flask-cors requests
后台运行：nohup python3 wenxin_proxy.py > /var/log/wenxin_proxy.log 2>&1 &
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time
import json
import sqlite3
import os

app = Flask(__name__)
CORS(app)

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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899, debug=False)
