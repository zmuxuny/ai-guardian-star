# ascend_main.py
import sys
import os
import time
import cv2
import numpy as np
import traceback
import threading
import json
from datetime import datetime
import uuid

# ---------------------- 外部依赖 ----------------------
import paho.mqtt.client as mqtt
import websocket # pip install websocket-client

# 保持工作区路径可用
current_file_dir = os.path.dirname(os.path.abspath(__file__))
if current_file_dir not in sys.path:
    sys.path.append(current_file_dir)

# 导入本地模块
from ascend_video_stream import start_stream, update_frame
import ascend_voice_stream as audio_hw  # 导入音频硬件模块

# ---------------------- 昇腾 ACL 导入 ----------------------
try:
    from acllite.acllite_imageproc import AclLiteImageProc
    import acllite.constants as const
    from acllite.acllite_model import AclLiteModel
    from acllite.acllite_image import AclLiteImage
    from acllite.acllite_resource import AclLiteResource
    import acl
except ImportError as e:
    print("❌ 错误：无法导入 ACL Lite 模块。")
    # sys.exit(1)

# ---------------------- 配置参数 ----------------------
# 1. 模型配置
MODEL_PATH = "/root/yolo/best.om"
MODEL_WIDTH = 640
MODEL_HEIGHT = 640

# 2. MQTT 配置
MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
ALERT_TOPIC = "ai_guardian/alerts/fall"
DEVICE_ID = "ascend_board"

# 3. 语音对讲配置 (WebSocket)
# !!! 请将此处 IP 修改为你运行 server.py 的电脑 IP !!!
AUDIO_WS_URL = "ws://192.168.1.100:8000/ws/device" 

# ---------------------- 常量定义 ----------------------
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]
SKELETON = [
    [15, 13], [13, 11], [16, 14], [14, 12], [11, 12],
    [5, 11], [6, 12], [5, 6], [5, 7], [6, 8], [7, 9], [8, 10],
    [1, 2], [0, 1], [0, 2], [1, 3], [2, 4], [3, 5], [4, 6]
]
FALL_ASPECT_RATIO_THRESHOLD = 0.8
STATIONARY_PIXEL_THRESHOLD = 20
STATIONARY_TIME_THRESHOLD_SECONDS = 10

# ---------------------- 语音对讲逻辑 ----------------------

def start_intercom_system():
    """启动语音对讲子系统（包含硬件线程和网络线程）"""
    print("Starting Intercom System...")

    # 1. 启动硬件音频服务 (在独立线程中，因为它包含 PyAudio 循环)
    hw_thread = threading.Thread(target=audio_hw.start_audio_service, daemon=True)
    hw_thread.start()

    # 2. 定义 WebSocket 回调
    def on_message(ws, message):
        """收到服务器音频 -> 播放"""
        if isinstance(message, bytes):
            audio_hw.put_audio_frame(message)

    def on_error(ws, error):
        print(f"⚠️ [Intercom] WebSocket 错误: {error}")

    def on_close(ws, close_status_code, close_msg):
        print("⚠️ [Intercom] 连接断开")

    def on_open(ws):
        print("✅ [Intercom] 连接成功，开始传输音频")
        
        def send_audio_thread():
            """录音 -> 发送给服务器"""
            while ws.sock and ws.sock.connected:
                frame = audio_hw.get_audio_frame()
                if frame:
                    try:
                        ws.send(frame, opcode=websocket.ABNF.OPCODE_BINARY)
                    except Exception as e:
                        print(f"Send Error: {e}")
                        break
                else:
                    time.sleep(0.001) # 避免空转

        threading.Thread(target=send_audio_thread, daemon=True).start()

    # 3. 启动 WebSocket 连接 (在独立线程中，因为 run_forever 阻塞)
    def ws_runner():
        # websocket.enable_trace(True) # 调试时开启
        while True: # 断线重连机制
            try:
                ws = websocket.WebSocketApp(AUDIO_WS_URL,
                                          on_open=on_open,
                                          on_message=on_message,
                                          on_error=on_error,
                                          on_close=on_close)
                ws.run_forever()
            except Exception as e:
                print(f"❌ WebSocket 连接失败: {e}")
            
            print("Running retry in 5 seconds...")
            time.sleep(5)

    ws_thread = threading.Thread(target=ws_runner, daemon=True)
    ws_thread.start()

# ---------------------- 视觉算法工具函数 ----------------------

def nms(boxes, scores, iou_threshold=0.5):
    if boxes.size == 0: return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1: break
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    return keep

def parse_predictions(predictions, conf_threshold=0.5):
    detections = []
    for i, pred in enumerate(predictions):
        if len(pred) < 56: continue
        cx, cy, w, h, obj_conf = float(pred[0]), float(pred[1]), float(pred[2]), float(pred[3]), float(pred[4])
        if obj_conf < conf_threshold: continue
        x1, y1, x2, y2 = cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0
        kpts = np.array(pred[5:5+51], dtype=np.float32).reshape(17, 3)
        detections.append({'box': [x1, y1, x2, y2], 'score': obj_conf, 'keypoints': kpts, 'class_id': 0})
    if not detections: return []
    boxes = np.array([d['box'] for d in detections])
    scores = np.array([d['score'] for d in detections])
    keep = nms(boxes, scores, iou_threshold=0.7)
    return [detections[i] for i in keep]

def pre_process_stream(cv_image, dvpp=None):
    try:
        orig_h, orig_w = cv_image.shape[:2]
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
        scale = min(MODEL_WIDTH / orig_w, MODEL_HEIGHT / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        pad_x, pad_y = (MODEL_WIDTH - new_w) // 2, (MODEL_HEIGHT - new_h) // 2
        resized_img = cv2.resize(rgb_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        padded_img = np.full((MODEL_HEIGHT, MODEL_WIDTH, 3), 114, dtype=np.uint8)
        padded_img[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized_img
        rgb_np = np.array(padded_img, dtype=np.float32) / 255.0
        nchw_img = np.transpose(rgb_np, (2, 0, 1))[np.newaxis, :, :, :]
        return np.ascontiguousarray(nchw_img), {'scale': scale, 'pad_x': pad_x, 'pad_y': pad_y, 'orig_w': orig_w, 'orig_h': orig_h}
    except Exception as e:
        print(f"❌ Stream Pre-process error: {e}")
        return None, None

def is_person_fallen(box, kpts, aspect_ratio_threshold):
    # 简化版摔倒检测逻辑
    box_w, box_h = box[2] - box[0], box[3] - box[1]
    if box_w > 0 and box_h > 0 and (box_h / box_w) < aspect_ratio_threshold:
        return True
    
    conf_thresh = 0.4
    try:
        shoulders_y = [kpts[5][1], kpts[6][1]]
        shoulders_conf = [kpts[5][2], kpts[6][2]]
        ankles_y = [kpts[15][1], kpts[16][1]]
        ankles_conf = [kpts[15][2], kpts[16][2]]
        
        valid_s = [y for y, c in zip(shoulders_y, shoulders_conf) if c > conf_thresh]
        valid_a = [y for y, c in zip(ankles_y, ankles_conf) if c > conf_thresh]
        
        if valid_s and valid_a:
            if min(valid_s) >= sum(valid_a)/len(valid_a): # 头比脚低
                return True
    except: pass
    return False

def check_fall_and_stationary(detections, person_states, frame_time):
    current_alerts = []
    # 这里省略了复杂的追踪逻辑，使用简化匹配
    for i, det in enumerate(detections):
        box, kpts = det['box'], det['kpts']
        is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
        status = "FALL DETECTED" if is_fallen else "Normal"
        color = (0, 0, 255) if is_fallen else (0, 255, 0)
        current_alerts.append({'box': box, 'kpts': kpts, 'status': status, 'color': color, 'id': i})
    return current_alerts

def draw_results(display_image, alerts):
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), alert['color'], 2)
        cv2.putText(display_image, alert['status'], (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, alert['color'], 2)
        # 简单画骨架
        for start, end in SKELETON:
            kpts = alert['kpts']
            if kpts[start][2] > 0.3 and kpts[end][2] > 0.3:
                pt1 = (int(kpts[start][0]), int(kpts[start][1]))
                pt2 = (int(kpts[end][0]), int(kpts[end][1]))
                cv2.line(display_image, pt1, pt2, (255, 255, 0), 2)
    return display_image

# ---------------------- MQTT & Detector 类 ----------------------

class MQTTAlertClient:
    def __init__(self):
        self.client = mqtt.Client(client_id=f"{DEVICE_ID}_{uuid.uuid4().hex[:6]}", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
            print("✅ MQTT Connected")
        except:
            print("❌ MQTT Connection Failed")
        self.last_alert_time = 0

    def publish_fall_alert(self):
        if time.time() - self.last_alert_time < 5: return
        alert = {"event": "fall_detected", "timestamp": str(datetime.now())}
        self.client.publish(ALERT_TOPIC, json.dumps(alert))
        print(f"🚀 Alert Sent: {alert}")
        self.last_alert_time = time.time()

class AclLiteStreamDetector:
    def __init__(self, model_path=MODEL_PATH, camera_index=0):
        self.model_path = model_path
        self.camera_index = camera_index
        self.running = False
        self.cap = None
        self.person_states = {}

    def init(self):
        try:
            self._acl_resource = AclLiteResource()
            self._acl_resource.init()
            self.model = AclLiteModel(self.model_path)
            self.dvpp = AclLiteImageProc(self._acl_resource)
            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(3, 640)
            self.cap.set(4, 480)
            if not self.cap.isOpened(): raise Exception("Camera open failed")
            self.running = True
            return True
        except Exception as e:
            print(f"Init Error: {e}")
            return False

    def get_detected_frame(self):
        if not self.running: return None
        ret, frame = self.cap.read()
        if not ret: return None
        
        try:
            resized, pp = pre_process_stream(frame, self.dvpp)
            result = self.model.execute([resized])
            
            # 解析输出 (假设输出格式正确，根据实际模型调整)
            output = result[0]
            if isinstance(output, np.ndarray):
                if output.ndim == 3 and output.shape[1] == 56: output = np.transpose(output, (0, 2, 1))
                detections = parse_predictions(output[0] if output.ndim==3 else output)
            else: detections = []

            # 坐标还原
            final_dets = []
            for det in detections:
                box = [(val - pp[p]) / pp['scale'] for val, p in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                kpts = [((k[0]-pp['pad_x'])/pp['scale'], (k[1]-pp['pad_y'])/pp['scale'], k[2]) for k in det['keypoints']]
                final_dets.append({'box': box, 'kpts': kpts})
            
            alerts = check_fall_and_stationary(final_dets, self.person_states, time.time())
            return draw_results(frame, alerts), alerts
        except Exception as e:
            # traceback.print_exc()
            return frame, []

    def stop(self):
        self.running = False
        if self.cap: self.cap.release()
        print("Detector Stopped")

# ---------------------- 主运行入口 ----------------------

def run_stream_and_infer(camera_index=0, model_path=None):
    # 1. 启动视频推流 (HTTP)
    threading.Thread(target=start_stream, daemon=True).start()
    print("🎥 Video Stream: http://<Board-IP>:5000")

    # 2. 启动语音对讲 (WebSocket + PyAudio)
    start_intercom_system()
    print("🎤 Audio Intercom system started in background.")

    # 3. 初始化推理与MQTT
    mqtt_client = MQTTAlertClient()
    detector = AclLiteStreamDetector(model_path=model_path or MODEL_PATH, camera_index=camera_index)
    
    if not detector.init(): return

    # 4. 主循环：只负责视频推理，音频在后台线程跑
    print("🚀 Main Inference Loop Started...")
    try:
        while detector.running:
            res = detector.get_detected_frame()
            if res is None: break
            frame, alerts = res
            
            for alert in alerts:
                if "FALL" in alert['status']:
                    mqtt_client.publish_fall_alert()
                    break
            
            update_frame(frame) # 推送视频帧
            time.sleep(0.001)   # 让出CPU
            
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        detector.stop()
        audio_hw.stop_audio_service()

if __name__ == "__main__":
    cam_idx = 0
    mod_pth = None
    for a in sys.argv[1:]:
        if "--camera=" in a: cam_idx = int(a.split("=")[1])
        if "--model=" in a: mod_pth = a.split("=")[1]
    
    run_stream_and_infer(cam_idx, mod_pth)