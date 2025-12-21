#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MQTT 消息监控 - 查看应用实际收到什么
"""

import paho.mqtt.client as mqtt

BROKER = "192.168.137.100"
PORT = 1883
TOPIC = "ai_guardian/alerts/#"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 连接成功")
        client.subscribe(TOPIC)
        print(f"📡 订阅主题: {TOPIC}")
    else:
        print(f"❌ 连接失败: {rc}")

def on_message(client, userdata, msg):
    print("\n" + "="*60)
    print(f"📨 收到消息")
    print(f"主题: {msg.topic}")
    print(f"内容: {msg.payload.decode('utf-8')}")
    print("="*60)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print(f"连接到 {BROKER}:{PORT}...")
client.connect(BROKER, PORT, 60)

print("开始监听... (按 Ctrl+C 退出)")
client.loop_forever()
