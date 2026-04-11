"""
wenxin_proxy.py — 智护星 AI 助手 · 文心千帆中转服务
部署在华为云 ECS 上，避免 API Key 暴露在 App 端

依赖安装：pip install flask flask-cors requests
启动命令：python wenxin_proxy.py
后台运行：nohup python wenxin_proxy.py > /var/log/wenxin_proxy.log 2>&1 &
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import json
import time

app = Flask(__name__)
CORS(app)

# ─── 配置区（申请后填入）───────────────────────────────────────
# 去 https://console.bce.baidu.com/qianfan 申请 API Key
QIANFAN_API_KEY = "YOUR_API_KEY"

# 使用 ERNIE-4.5（文心系列，符合4C大赛指定工具）
WENXIN_MODEL = "ernie-4.5-turbo-128k"
QIANFAN_URL = "https://qianfan.baidubce.com/v2/chat/completions"
# ─────────────────────────────────────────────────────────────

GUARDIAN_SYSTEM_PROMPT = """你是"智护星"AI健康助手，专为老人家属提供居家监护健康咨询服务。

你的职责：
1. 根据监护数据，分析老人的健康风险并给出专业建议
2. 解答家属对老人健康状况的疑问，语气温暖专业
3. 在发现高风险情况时，主动提示联系医生或拨打急救电话
4. 保持回答简洁（200字以内），避免专业术语堆砌

注意事项：
- 你不是医生，建议仅供参考，不能替代专业医疗诊断
- 涉及紧急情况（连续摔倒、意识不清）时必须建议立即就医
- 严格保护用户隐私，不主动询问或重复用户个人信息"""


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查接口，App 启动时 ping 一下"""
    return jsonify({"status": "ok", "service": "wenxin-proxy", "time": int(time.time())})


@app.route('/ai/chat', methods=['POST'])
def ai_chat():
    """
    AI 对话接口
    请求体：
    {
        "message": "用户消息",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}],
        "context": {
            "fallCount7d": 2,
            "sedentaryCount7d": 5,
            "lastFallDaysAgo": 3,
            "deviceOnline": true
        }
    }
    """
    try:
        data = request.get_json(force=True)
        user_message = data.get('message', '').strip()
        history = data.get('history', [])
        context = data.get('context', {})

        if not user_message:
            return jsonify({"error": "message 不能为空"}), 400

        # ── 构建上下文摘要（脱敏，仅统计数据）──────────────────
        context_summary = _build_context_summary(context)

        # ── 构建消息列表 ────────────────────────────────────────
        messages = [{"role": "system", "content": GUARDIAN_SYSTEM_PROMPT}]

        # 历史对话（最多保留最近10轮，防止 token 超限）
        if history:
            messages.extend(history[-20:])  # 每轮2条，保留10轮

        # 当前用户消息（附加上下文摘要）
        full_user_msg = user_message
        if context_summary:
            full_user_msg = f"[当前监护摘要]\n{context_summary}\n\n[家属提问]\n{user_message}"

        messages.append({"role": "user", "content": full_user_msg})

        # ── 调用千帆 API ────────────────────────────────────────
        headers = {
            "Authorization": f"Bearer {QIANFAN_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": WENXIN_MODEL,
            "messages": messages,
            "max_completion_tokens": 512,
            "temperature": 0.7,
        }

        resp = requests.post(QIANFAN_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        result = resp.json()

        # 提取回复文本
        ai_reply = result['choices'][0]['message']['content']

        return jsonify({
            "reply": ai_reply,
            "model": WENXIN_MODEL,
            "timestamp": int(time.time())
        })

    except requests.exceptions.Timeout:
        return jsonify({"error": "AI 服务响应超时，请稍后再试"}), 504
    except requests.exceptions.HTTPError as e:
        return jsonify({"error": f"千帆 API 错误: {e.response.status_code}"}), 502
    except Exception as e:
        app.logger.error(f"ai_chat error: {e}")
        return jsonify({"error": "服务内部错误，请稍后再试"}), 500


def _build_context_summary(context: dict) -> str:
    """将健康统计数据构建为自然语言摘要（只传聚合统计，不含任何PII）"""
    if not context:
        return ""
    parts = []
    fall = context.get('fallCount7d', 0)
    sedentary = context.get('sedentaryCount7d', 0)
    last_fall = context.get('lastFallDaysAgo', -1)
    online = context.get('deviceOnline', False)

    parts.append(f"设备状态：{'在线监护中' if online else '离线'}")
    parts.append(f"近7天摔倒次数：{fall}次")
    if last_fall >= 0:
        parts.append(f"最近一次摔倒：{last_fall}天前" if last_fall > 0 else "最近一次摔倒：今天")
    parts.append(f"近7天久坐告警：{sedentary}次")
    return "\n".join(parts)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8899, debug=False)
