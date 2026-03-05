#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
手动测试久坐检测 - 直接发送久坐消息
"""

import paho.mqtt.client as mqtt
import json
import time

BROKER = "192.168.137.100"
PORT = 1883

def on_connect(client, userdata, flags, rc):
    print(f"连接结果: {rc}")

def on_publish(client, userdata, mid):
    print(f"消息已发布: {mid}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_publish = on_publish

print("连接到MQTT服务器...")
client.connect(BROKER, PORT, 60)
client.loop_start()

time.sleep(1)

# 发送久坐消息
message = {
    "event": "sedentary",
    "confidence": 0.95,
    "timestamp": int(time.time() * 1000)
}

topic = "ai_guardian/alerts/sedentary"
payload = json.dumps(message, ensure_ascii=False)

print(f"\n发送久坐消息:")
print(f"主题: {topic}")
print(f"内容: {payload}")

result = client.publish(topic, payload, qos=1)
result.wait_for_publish()

print("\n✅ 消息已发送！")
print("\n请检查应用日志，应该看到:")
print("  - 事件字段原始值=\"sedentary\"")
print("  - hasSedentary=true")
print("  - 🟡🟡🟡 检测到久坐事件")
print("  - 主页显示黄色边框")

time.sleep(2)
client.loop_stop()
client.disconnect()
