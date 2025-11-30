#!/usr/bin/env python3
"""
测试 MQTT 摔倒检测脚本
向 MQTT Broker 发送模拟的摔倒检测消息
"""

import paho.mqtt.client as mqtt
import json
import time
from datetime import datetime

# MQTT 配置（与您的应用配置一致）
BROKER_HOST = '192.168.137.100'
BROKER_PORT = 1883
ALERT_TOPIC = 'ai_guardian/alerts/test'

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 已连接到 MQTT Broker: {BROKER_HOST}:{BROKER_PORT}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")

def send_fall_alert(client, event_type="fall"):
    """发送摔倒告警消息"""
    alert_data = {
        "device_id": "test_device",
        "event": event_type,
        "confidence": 0.95,
        "timestamp": int(time.time()),
        "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    message = json.dumps(alert_data, ensure_ascii=False)
    result = client.publish(ALERT_TOPIC, message, qos=1)
    
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print(f"📤 已发送 {event_type} 消息: {message}")
    else:
        print(f"❌ 发送失败: {result.rc}")
    
    return result.rc == mqtt.MQTT_ERR_SUCCESS

def main():
    print("=" * 60)
    print("MQTT 摔倒检测测试工具")
    print("=" * 60)
    
    # 创建 MQTT 客户端
    client = mqtt.Client(client_id="test_fall_sender")
    client.on_connect = on_connect
    
    try:
        print(f"正在连接到 {BROKER_HOST}:{BROKER_PORT}...")
        client.connect(BROKER_HOST, BROKER_PORT, 60)
        client.loop_start()
        
        # 等待连接建立
        time.sleep(2)
        
        print("\n开始测试...")
        print("-" * 60)
        
        # 测试 1: 发送第一次摔倒
        print("\n[测试 1] 发送第一次摔倒事件...")
        send_fall_alert(client, "fall")
        time.sleep(3)
        
        # 测试 2: 发送正常状态
        print("\n[测试 2] 发送正常状态...")
        send_fall_alert(client, "normal")
        time.sleep(2)
        
        # 测试 3: 发送第二次摔倒（应该被记录）
        print("\n[测试 3] 发送第二次摔倒事件...")
        send_fall_alert(client, "fall")
        time.sleep(3)
        
        # 测试 4: 快速发送第三次摔倒（可能被过滤）
        print("\n[测试 4] 快速发送第三次摔倒（< 2秒）...")
        send_fall_alert(client, "fall")
        time.sleep(1)
        
        # 测试 5: 等待后发送第四次摔倒（应该被记录）
        print("\n[测试 5] 等待 3 秒后发送第四次摔倒...")
        time.sleep(2)
        send_fall_alert(client, "fall")
        time.sleep(3)
        
        print("\n" + "=" * 60)
        print("✅ 测试完成！请查看应用的记录页面。")
        print("=" * 60)
        print("\n预期结果：")
        print("- 记录页面应显示 3 条摔倒记录（测试1、3、5）")
        print("- 测试 4 的记录应被过滤（< 2秒间隔）")
        print("- 最新的记录应该在最上面")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
    finally:
        client.loop_stop()
        client.disconnect()
        print("\n已断开连接")

if __name__ == "__main__":
    main()
