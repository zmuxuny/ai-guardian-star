import paho.mqtt.publish as publish
import json

# 发送久坐消息
msg = json.dumps({"event": "sedentary"})
publish.single("ai_guardian/alerts/sedentary", msg, hostname="192.168.137.100", port=1883)
print("已发送久坐消息: " + msg)
