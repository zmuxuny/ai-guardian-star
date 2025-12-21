#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
久坐检测MQTT测试脚本
模拟发送久坐事件到MQTT服务器
"""

import paho.mqtt.client as mqtt
import json
import time

# MQTT服务器配置
BROKER = "192.168.137.100"
PORT = 1883
TOPIC = "ai_guardian/alerts/sedentary"

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 成功连接到MQTT Broker: {BROKER}:{PORT}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")

def send_sedentary_alert():
    """发送久坐警报"""
    client = mqtt.Client()
    client.on_connect = on_connect
    
    try:
        print(f"正在连接到 {BROKER}:{PORT}...")
        client.connect(BROKER, PORT, 60)
        client.loop_start()
        time.sleep(1)  # 等待连接建立
        
        # 测试不同的久坐消息格式
        test_messages = [
            {
                "description": "标准久坐事件",
                "payload": {
                    "event": "sedentary",
                    "timestamp": int(time.time() * 1000),
                    "confidence": 0.95
                }
            },
            {
                "description": "中文久坐事件",
                "payload": {
                    "event": "久坐",
                    "timestamp": int(time.time() * 1000),
                    "confidence": 0.92
                }
            },
            {
                "description": "sitting_long事件",
                "payload": {
                    "alert_type": "sitting_long",
                    "timestamp": int(time.time() * 1000),
                    "confidence": 0.88
                }
            }
        ]
        
        print(f"\n📤 准备发送 {len(test_messages)} 条久坐测试消息到主题: {TOPIC}")
        print("=" * 60)
        
        for i, msg in enumerate(test_messages, 1):
            payload_str = json.dumps(msg["payload"], ensure_ascii=False)
            print(f"\n[消息 {i}/{len(test_messages)}] {msg['description']}")
            print(f"Payload: {payload_str}")
            
            result = client.publish(TOPIC, payload_str, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                print(f"✅ 消息 {i} 发送成功")
            else:
                print(f"❌ 消息 {i} 发送失败，错误码: {result.rc}")
            
            time.sleep(3)  # 等待3秒，避免去重逻辑
        
        print("\n" + "=" * 60)
        print("✅ 所有测试消息发送完成")
        print("\n💡 提示：")
        print("  - 请检查应用日志中是否有 '[mqtt]:🟡 检测到久坐事件'")
        print("  - 检查主页是否显示黄色氛围光")
        print("  - 检查记录页面是否有久坐记录")
        
    except Exception as e:
        print(f"❌ 发生错误: {e}")
    finally:
        time.sleep(1)
        client.loop_stop()
        client.disconnect()
        print("\n🔌 已断开MQTT连接")

if __name__ == "__main__":
    print("=" * 60)
    print("        久坐检测MQTT测试工具")
    print("=" * 60)
    send_sedentary_alert()
