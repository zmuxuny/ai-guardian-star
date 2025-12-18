import sys
import os
import time
import cv2
import numpy as np
import traceback
import threading
# ---------------------- MQTT 相关 ----------------------
import paho.mqtt.client as mqtt
import json
from datetime import datetime
import uuid

# 保持工作区路径可用
current_file_dir = os.path.dirname(os.path.abspath(__file__))
if current_file_dir not in sys.path:
    sys.path.append(current_file_dir)

# 推流服务（网页 + MJPEG 流）由 ascend_video_stream.py 提供
from ascend_video_stream import start_stream, update_frame

# ---------------------- 导入 ACL Lite（昇腾）模块 ----------------------
try:
    from acllite.acllite_imageproc import AclLiteImageProc
    import acllite.constants as const
    from acllite.acllite_model import AclLiteModel
    from acllite.acllite_image import AclLiteImage
    from acllite.acllite_resource import AclLiteResource
    import acl
except ImportError as e:
    print("❌ 错误：无法导入 ACL Lite 模块。请确保 acllite 库已正确安装且路径设置正确。")
    print(f"详细错误: {e}")
    # 不退出，后续 init() 会失败并处理
    # sys.exit(1)

# ---------------------- 模型与参数 ----------------------
MODEL_PATH = "/root/yolo/best.om"
MODEL_WIDTH = 640
MODEL_HEIGHT = 640

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

# ---------------------- 工具函数（完整来自 ascend_yolo.py） ----------------------

def nms(boxes, scores, iou_threshold=0.5):
    """简单 NMS 实现"""
    if boxes.size == 0:
        return []
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        if order.size == 1:
            break
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
    """解析 YOLOv8-pose 输出（predictions: Nx56 等）"""
    detections = []
    for i, pred in enumerate(predictions):
        # pred 包含 cx, cy, w, h, obj_conf, 然后 51 个 keypoints (17*3=51)
        if len(pred) < 56:
            continue
        cx, cy, w, h, obj_conf = float(pred[0]), float(pred[1]), float(pred[2]), float(pred[3]), float(pred[4])
        if obj_conf < conf_threshold:
            continue
        x1, y1, x2, y2 = cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0
        kpts = np.array(pred[5:5+51], dtype=np.float32).reshape(17, 3)
        detection = {'box': [x1, y1, x2, y2], 'score': obj_conf, 'keypoints': kpts, 'class_id': 0}
        detections.append(detection)

    if not detections:
        return []
    boxes = np.array([d['box'] for d in detections])
    scores = np.array([d['score'] for d in detections])
    keep = nms(boxes, scores, iou_threshold=0.7)
    return [detections[i] for i in keep]


def pre_process_stream(cv_image, dvpp=None):
    """实时流预处理：letterbox -> NCHW float32"""
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
        nchw_img = np.ascontiguousarray(nchw_img)

        return nchw_img, {'scale': scale, 'pad_x': pad_x, 'pad_y': pad_y, 'orig_w': orig_w, 'orig_h': orig_h}
    except Exception as e:
        print(f"❌ Stream Pre-process error: {e}")
        return None, None


def is_person_fallen(box, kpts, aspect_ratio_threshold):
    """通过结合检测框宽高比和关键点相对位置来判断是否摔倒。"""
    box_w, box_h = box[2] - box[0], box[3] - box[1]
    if box_w > 0 and box_h > 0:
        if (box_h / box_w) < aspect_ratio_threshold:
            return True

    conf_thresh = 0.4
    try:
        L_shoulder_y, L_shoulder_conf = kpts[5][1], kpts[5][2]
        R_shoulder_y, R_shoulder_conf = kpts[6][1], kpts[6][2]
        L_hip_x, L_hip_y, L_hip_conf = kpts[11][0], kpts[11][1], kpts[11][2]
        R_hip_x, R_hip_y, R_hip_conf = kpts[12][0], kpts[12][1], kpts[12][2]
        L_knee_x, L_knee_y, L_knee_conf = kpts[13][0], kpts[13][1], kpts[13][2]
        R_knee_x, R_knee_y, R_knee_conf = kpts[14][0], kpts[14][1], kpts[14][2]
        L_ankle_y, L_ankle_conf = kpts[15][1], kpts[15][2]
        R_ankle_y, R_ankle_conf = kpts[16][1], kpts[16][2]
    except Exception:
        return False

    fall_detected = False

    valid_shoulders_y = [y for y, conf in [(L_shoulder_y, L_shoulder_conf), (R_shoulder_y, R_shoulder_conf)] if conf > conf_thresh]
    valid_ankles_y = [y for y, conf in [(L_ankle_y, L_ankle_conf), (R_ankle_y, R_ankle_conf)] if conf > conf_thresh]

    if valid_shoulders_y and valid_ankles_y:
        min_shoulder_y = min(valid_shoulders_y)
        avg_ankle_y = sum(valid_ankles_y) / len(valid_ankles_y)
        if min_shoulder_y >= avg_ankle_y:
            fall_detected = True

    if fall_detected:
        return True

    valid_hips_x = [x for x, conf in [(L_hip_x, L_hip_conf), (R_hip_x, R_hip_conf)] if conf > conf_thresh]
    valid_hips_y = [y for y, conf in [(L_hip_y, L_hip_conf), (R_hip_y, R_hip_conf)] if conf > conf_thresh]
    valid_knees_x = [x for x, conf in [(L_knee_x, L_knee_conf), (R_knee_x, R_knee_conf)] if conf > conf_thresh]
    valid_knees_y = [y for y, conf in [(L_knee_y, L_knee_conf), (R_knee_y, R_knee_conf)] if conf > conf_thresh]

    if valid_hips_x and valid_knees_x:
        avg_hip_x = sum(valid_hips_x) / len(valid_hips_x)
        avg_hip_y = sum(valid_hips_y) / len(valid_hips_y)
        avg_knee_x = sum(valid_knees_x) / len(valid_knees_x)
        avg_knee_y = sum(valid_knees_y) / len(valid_knees_y)

        v_hip_knee = np.array([avg_knee_x - avg_hip_x, avg_knee_y - avg_hip_y])
        norm_v = np.linalg.norm(v_hip_knee)

        if norm_v > 1e-6:
            angle_rad = np.arccos(np.clip(np.dot(v_hip_knee, [1, 0]) / norm_v, -1.0, 1.0))
            angle_deg = np.degrees(angle_rad)
            if (angle_deg < 30) or (angle_deg > 150):
                fall_detected = True

    return fall_detected


def check_fall_and_stationary(detections, person_states, frame_time):
    """分析检测结果，更新追踪状态，并生成警报"""
    def calculate_iou(box1, box2):
        x1_inter, y1_inter = max(box1[0], box2[0]), max(box1[1], box2[1])
        x2_inter, y2_inter = min(box1[2], box2[2]), min(box1[3], box2[3])
        inter_area = max(0, x2_inter - x1_inter) * max(0, y2_inter - y1_inter)
        if inter_area == 0:
            return 0
        box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
        box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter_area / float(box1_area + box2_area - inter_area + 1e-6)

    current_alerts = []
    matched_detection_indices = set()
    TRACKING_MATCH_IOU_THRESHOLD = 0.5

    for person_id, state in list(person_states.items()):
        best_match_iou, best_match_idx = 0, -1
        for i, det in enumerate(detections):
            if i in matched_detection_indices:
                continue
            iou = calculate_iou(state['box'], det['box'])
            if iou > best_match_iou and iou >= TRACKING_MATCH_IOU_THRESHOLD:
                best_match_iou, best_match_idx = iou, i
        if best_match_idx != -1:
            matched_detection_indices.add(best_match_idx)
            det = detections[best_match_idx]
            box, kpts = det['box'], det['kpts']
            state.update({'box': box, 'last_seen': frame_time})
            status_text, color = "Normal", (0, 255, 0)

            is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
            state['is_fallen'] = is_fallen

            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            stationary_duration = 0
            if state.get('last_pos'):
                dist = np.sqrt((center_pos[0] - state['last_pos'][0]) ** 2 + (center_pos[1] - state['last_pos'][1]) ** 2)
                if dist < STATIONARY_PIXEL_THRESHOLD:
                    if state.get('stationary_start_time') is None:
                        state['stationary_start_time'] = frame_time
                    stationary_duration = frame_time - state['stationary_start_time']
                    if stationary_duration > STATIONARY_TIME_THRESHOLD_SECONDS:
                        status_text = f"Fallen & Still ({int(stationary_duration)}s)" if is_fallen else f"Stationary ({int(stationary_duration)}s)"
                        color = (0, 165, 255)
                else:
                    state['stationary_start_time'] = None
                    state['last_pos'] = center_pos
            else:
                state['last_pos'] = center_pos

            if is_fallen and (color == (0, 255, 0) or stationary_duration <= STATIONARY_TIME_THRESHOLD_SECONDS):
                status_text = "FALL DETECTED"
                color = (0, 0, 255)

            current_alerts.append({'box': box, 'kpts': kpts, 'status': status_text, 'color': color, 'id': person_id})

    next_person_id = max(person_states.keys()) + 1 if person_states else 0
    for i, det in enumerate(detections):
        if i not in matched_detection_indices:
            box, kpts = det['box'], det['kpts']
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
            person_states[next_person_id] = {
                'box': box, 'last_pos': center_pos, 'stationary_start_time': None,
                'is_fallen': is_fallen, 'last_seen': frame_time,
            }
            status_text = "New & FALL" if is_fallen else "New"
            color = (0, 0, 255) if is_fallen else (0, 255, 0)
            current_alerts.append({'box': box, 'kpts': kpts, 'status': status_text, 'color': color, 'id': next_person_id})
            next_person_id += 1

    for pid in [pid for pid, state in person_states.items() if frame_time - state.get('last_seen', frame_time) > 3.0]:
        del person_states[pid]

    return current_alerts


def draw_results(display_image, alerts):
    """绘制边界框、关键点、骨架和状态文本。"""
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        kpts, status, color, pid = alert['kpts'], alert['status'], alert['color'], alert['id']
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), color, 2)
        text = f"ID {pid} | {status}"
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(display_image, (box[0], box[1] - text_h - baseline - 5), (box[0] + text_w, box[1]), (0, 0, 0), -1)
        cv2.putText(display_image, text, (box[0], box[1] - baseline - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        for kx, ky, kconf in kpts:
            if kconf > 0.3:
                cv2.circle(display_image, (int(kx), int(ky)), 3, (255, 0, 0), -1)
        for start, end in SKELETON:
            if kpts[start][2] > 0.3 and kpts[end][2] > 0.3:
                pt1 = (int(kpts[start][0]), int(kpts[start][1]))
                pt2 = (int(kpts[end][0]), int(kpts[end][1]))
                cv2.line(display_image, pt1, pt2, (255, 255, 0), 2)
    return display_image

# ---------------------- MQTT 客户端类 ----------------------

MQTT_BROKER = "127.0.0.1"
MQTT_PORT = 1883
ALERT_TOPIC = "ai_guardian/alerts/fall"
DEVICE_ID = "ascend_board"

class MQTTAlertClient:
    def __init__(self):
        self.client = mqtt.Client(
            client_id=f"{DEVICE_ID}_{uuid.uuid4().hex[:6]}",
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
        self.client.on_connect = self.on_connect
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            print(f"❌ MQTT 连接失败: {e}")
        self.last_alert_time = 0
        self.alert_cooldown = 5

    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            print("✅ MQTT 连接成功")
        else:
            print(f"❌ MQTT 连接失败，错误码: {rc}")

    def publish_fall_alert(self, confidence=0.9):
        current_time = time.time()
        if current_time - self.last_alert_time < self.alert_cooldown:
            return
        alert_msg = {
            "device_id": DEVICE_ID,
            "event": "fall_detected",
            "confidence": float(confidence),
            "timestamp": datetime.timestamp(datetime.now()),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        self.client.publish(ALERT_TOPIC, json.dumps(alert_msg), qos=1)
        print(f"🚀 已发送摔倒告警: {alert_msg['datetime']}")
        self.last_alert_time = current_time

# ---------------------- AclLiteStreamDetector (完整复制并保留) ----------------------

class AclLiteStreamDetector:
    """ACL Lite 实时流检测器，用于统一管理资源和状态"""

    def __init__(self, model_path=MODEL_PATH, camera_index=0):
        self._acl_resource = None
        self.model = None
        self.dvpp = None
        self.cap = None
        self.running = False
        self.frame_count = 0
        self.start_time = time.time()
        self.model_path = model_path
        self.camera_index = camera_index
        self.person_states = {}  # 实时追踪状态

    def init(self):
        try:
            self._acl_resource = AclLiteResource()
            self._acl_resource.init()
            self.model = AclLiteModel(self.model_path)
            self.dvpp = AclLiteImageProc(self._acl_resource)

            self.cap = cv2.VideoCapture(self.camera_index)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            if not self.cap.isOpened():
                raise Exception(f"Failed to open camera index {self.camera_index}.")

            self.running = True
            print(f"✅ StreamDetector initialized (Camera Index: {self.camera_index}).")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize StreamDetector: {e}")
            traceback.print_exc()
            self.stop()
            return False

    def get_detected_frame(self):
        """捕获帧、运行推理、分析、绘制结果。"""
        if not self.running or not self.cap or not self.cap.isOpened():
            return None

        ret, frame = self.cap.read()
        if not ret:
            self.running = False
            return None

        try:
            resized_image, pp_params = pre_process_stream(frame, self.dvpp)
            if resized_image is None:
                return frame, []

            # 执行模型推理
            result = self.model.execute([resized_image])

            raw_detections = []
            if result and result[0] is not None:
                output = result[0]
                # 尝试转换为 numpy 数组以统一处理
                try:
                    output = np.array(output)
                except Exception:
                    pass

                if isinstance(output, np.ndarray):
                    # 常见输出格式处理：
                    # - (batch, N, 56) 或 (batch, 56, N)
                    # - (N, 56)
                    if output.ndim == 3:
                        # 若是 (batch, 56, N) 则转为 (batch, N, 56)
                        if output.shape[1] == 56 and output.shape[2] >= 1:
                            output = np.transpose(output, (0, 2, 1))
                        raw_detections = parse_predictions(output[0], conf_threshold=0.5)
                    elif output.ndim == 2:
                        # (N,56)
                        raw_detections = parse_predictions(output, conf_threshold=0.5)
                    else:
                        # 非预期维度，打印信息供调试
                        print(f"⚠️ 未知模型输出维度: {output.shape}")
                else:
                    print(f"⚠️ 未知模型输出类型: {type(output)}")

            # 将检测结果映射回原始图像尺寸并组织为 kpts 列表格式
            current_frame_detections = []
            for det in raw_detections:
                # parse_predictions 返回 'box' 和 'keypoints'
                box = [(val - pp_params[pad]) / pp_params['scale']
                       for val, pad in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                # keypoints 可能为 numpy array (17,3)
                kpts_src = det.get('keypoints') if 'keypoints' in det else det.get('kpts', None)
                if kpts_src is None:
                    continue
                kpts = [((float(k[0]) - pp_params['pad_x']) / pp_params['scale'],
                         (float(k[1]) - pp_params['pad_y']) / pp_params['scale'], float(k[2]))
                        for k in kpts_src]
                current_frame_detections.append({'box': box, 'kpts': kpts})

            alerts = check_fall_and_stationary(current_frame_detections, self.person_states, time.time())
            display_image = draw_results(frame.copy(), alerts)
            self.frame_count += 1
            return display_image, alerts

        except Exception as e:
            print(f"❌ Frame processing error: {e}")
            traceback.print_exc()
            return frame, []

    def stop(self):
        """释放所有资源"""
        if self.running:
            self.running = False
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
        if self.model:
            try:
                del self.model
            except:
                pass
        if self.dvpp:
            try:
                del self.dvpp
            except:
                pass
        print("Detector stopped and Ascend resources released.")

# ---------------------- 主运行逻辑（将 ascend_yolo 完全放入 ascend_main，启动推流服务） ----------------------

def run_stream_and_infer(camera_index=0, model_path=None):
    threading.Thread(target=start_stream, daemon=True).start()
    print("视频流服务已启动，访问 http://<开发板IP>:5000 查看实时画面")

    # 初始化 MQTT 客户端
    mqtt_client = MQTTAlertClient()

    detector = AclLiteStreamDetector(model_path=model_path or MODEL_PATH, camera_index=camera_index)
    if not detector.init():
        print("检测器初始化失败，退出。")
        return

    total_frames = 0
    start_time = time.time()
    try:
        while detector.running:
            res = detector.get_detected_frame()
            if res is None:
                print("摄像头流结束或读取失败，退出推理循环。")
                break
            frame, alerts = res
            
            # 检查是否有摔倒警报并发送 MQTT
            for alert in alerts:
                if "FALL" in alert.get('status', ''):
                    mqtt_client.publish_fall_alert()
                    break # 每帧只发送一次

            # 更新到视频流
            try:
                update_frame(frame)
            except Exception as e:
                print(f"⚠️ update_frame 出错: {e}")
            total_frames += 1
            if total_frames % 30 == 0:
                elapsed = time.time() - start_time
                fps = total_frames / (elapsed + 1e-6)
                print(f"[Stream] Frames: {total_frames}, FPS: {fps:.2f}, Detections: {len(alerts)}")
            # 控制稍微的延时以降低占用
            time.sleep(0.005)
    except KeyboardInterrupt:
        print("检测器收到中断信号，停止中...")
    except Exception as e:
        print(f"运行时错误: {e}")
        traceback.print_exc()
    finally:
        detector.stop()
        print("主循环退出。")

def parse_args_and_run():
    camera_index = 0
    model_path = None
    for a in sys.argv[1:]:
        if a.startswith("--camera="):
            try:
                camera_index = int(a.split("=", 1)[1])
            except:
                pass
        elif a.startswith("--model="):
            model_path = a.split("=", 1)[1]
    run_stream_and_infer(camera_index=camera_index, model_path=model_path)

if __name__ == "__main__":
    parse_args_and_run()