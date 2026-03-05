#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
发送久坐测试消息
"""

import paho.mqtt.publish as publish
import json
import time

BROKER = "192.168.137.100"
PORT = 1883

# 测试不同的主题和消息
tests = [
    {
        "name": "测试1: 标准久坐事件",
        "topic": "ai_guardian/alerts/sedentary",
        "message": {"event": "sedentary", "confidence": 0.95}
    },
    {
        "name": "测试2: 中文久坐事件",
        "topic": "ai_guardian/alerts/sedentary",
        "message": {"event": "久坐", "confidence": 0.92}
    },
    {
        "name": "测试3: sitting_long事件",
        "topic": "ai_guardian/alerts/sitting",
        "message": {"alert_type": "sitting_long", "confidence": 0.88}
    },
    {
        "name": "测试4: 纯文本久坐",
        "topic": "ai_guardian/alerts/test",
        "message": "sedentary detected"
    }
]

print("="*60)
print("久坐检测消息发送器")
print("="*60)

for i, test in enumerate(tests, 1):
    print(f"\n{'='*60}")
    print(f"[{i}/{len(tests)}] {test['name']}")
    print(f"主题: {test['topic']}")
    
    if isinstance(test['message'], dict):
        payload = json.dumps(test['message'], ensure_ascii=False)
    else:
        payload = test['message']
    
    print(f"消息: {payload}")
    
    try:
        publish.single(test['topic'], payload, hostname=BROKER, port=PORT, qos=1)
        print("✅ 发送成功")
    except Exception as e:
        print(f"❌ 发送失败: {e}")
    
    if i < len(tests):
        print(f"\n等待10秒后发送下一条...")
        time.sleep(10)

print("\n" + "="*60)
print("所有测试消息发送完成！")
print("="*60)
print("\n请检查应用日志：")
print("  1. 查找 '🔍 事件字段小写值' 确认收到的事件类型")
print("  2. 查找 '关键词检测' 确认各标志位的值")
print("  3. 查找 '🟡🟡🟡 检测到久坐事件' 确认是否正确识别")
