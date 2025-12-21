#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
久坐检测调试脚本 - 发送各种格式的消息
"""

import paho.mqtt.publish as publish
import json
import time

BROKER = "192.168.137.100"
PORT = 1883
TOPIC = "ai_guardian/alerts/test"

messages = [
    {
        "desc": "纯JSON-英文",
        "data": {"event": "sedentary", "confidence": 0.95}
    },
    {
        "desc": "纯JSON-中文",
        "data": {"event": "久坐", "confidence": 0.92}
    },
    {
        "desc": "纯文本-英文",
        "data": "sedentary detected"
    },
    {
        "desc": "纯文本-中文",
        "data": "检测到久坐"
    },
]

print(f"连接到 {BROKER}:{PORT}")
print("=" * 60)

for i, msg in enumerate(messages, 1):
    if isinstance(msg["data"], dict):
        payload = json.dumps(msg["data"], ensure_ascii=False)
    else:
        payload = msg["data"]
    
    print(f"\n[{i}] {msg['desc']}")
    print(f"发送到: {TOPIC}")
    print(f"内容: {payload}")
    
    try:
        publish.single(TOPIC, payload, hostname=BROKER, port=PORT)
        print("✅ 发送成功")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
    
    print(f"等待5秒...")
    time.sleep(5)

print("\n" + "=" * 60)
print("测试完成！请检查应用日志")
