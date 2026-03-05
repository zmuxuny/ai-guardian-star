import paho.mqtt.publish as publish
import json

BROKER = "192.168.137.100"
PORT = 1883
TOPIC = "ai_guardian/alerts/sedentary"

# 发送久坐消息
message = {
    "event": "sedentary",
    "timestamp": 1764933520150,
    "confidence": 0.95
}

print(f"发送久坐消息到 {BROKER}:{PORT}/{TOPIC}")
print(f"消息内容: {json.dumps(message, ensure_ascii=False)}")

try:
    publish.single(TOPIC, json.dumps(message), hostname=BROKER, port=PORT)
    print("✅ 消息发送成功!")
except Exception as e:
    print(f"❌ 发送失败: {e}")
