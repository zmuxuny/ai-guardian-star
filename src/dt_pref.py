import sys
import os
import time
import cv2
import numpy as np
import traceback

# 1. ✅ 路径配置
current_file_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_file_dir)

# 导入 ACL Lite 模块
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
    sys.path.pop() 
    sys.exit(1)

# 2. ✅ 模型和配置参数
MODEL_PATH = "/root/yolo/best.om"
MODEL_WIDTH = 640
MODEL_HEIGHT = 640

# COCO keypoints names and SKELETON
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

# 摔倒和长时间静止监测配置
FALL_ASPECT_RATIO_THRESHOLD = 0.8
STATIONARY_PIXEL_THRESHOLD = 20
STATIONARY_TIME_THRESHOLD_SECONDS = 10

# 3. ✅ 核心工具函数

def nms(boxes, scores, iou_threshold=0.5):
    """简单 NMS 实现"""
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)
    order = scores.argsort()[::-1]
    keep = []
    while order.size > 0:
        i = order[0]
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1)
        h = np.maximum(0.0, yy2 - yy1)
        inter = w * h
        iou = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(iou <= iou_threshold)[0]
        order = order[inds + 1]
    return keep

def parse_predictions(predictions, conf_threshold=0.5):
    """解析 YOLOv8-pose 输出"""
    detections = []
    for i, pred in enumerate(predictions):
        cx, cy, w, h, obj_conf = pred[0], pred[1], pred[2], pred[3], pred[4]
        if obj_conf < conf_threshold: continue

        x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        kpts = pred[5:56].reshape(17, 3)
        detection = {'box': [x1, y1, x2, y2], 'score': obj_conf, 'keypoints': kpts, 'class_id': 0}
        detections.append(detection)

    if not detections: return []
    boxes = np.array([d['box'] for d in detections])
    scores = np.array([d['score'] for d in detections])
    
    # 💥 修改点 1: 提高 NMS IOU 阈值，更严格地合并高度重叠的检测框
    keep = nms(boxes, scores, iou_threshold=0.7) 
    return [detections[i] for i in keep]

def pre_process_stream(cv_image, dvpp):
    """实时流预处理"""
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
    
    # 条件 1: 宽高比
    box_w, box_h = box[2] - box[0], box[3] - box[1]
    if box_w > 0 and box_h > 0:
        if (box_h / box_w) < aspect_ratio_threshold:
            return True 

    # 提取关键点
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
    except IndexError:
        return False

    fall_detected = False

    # 条件 2: 
    valid_shoulders_y = [y for y, conf in [(L_shoulder_y, L_shoulder_conf), (R_shoulder_y, R_shoulder_conf)] if conf > conf_thresh]
    valid_ankles_y = [y for y, conf in [(L_ankle_y, L_ankle_conf), (R_ankle_y, R_ankle_conf)] if conf > conf_thresh]

    if valid_shoulders_y and valid_ankles_y:
        min_shoulder_y = min(valid_shoulders_y)
        avg_ankle_y = sum(valid_ankles_y) / len(valid_ankles_y)
        if min_shoulder_y >= avg_ankle_y:
            fall_detected = True

    if fall_detected: return True

    # 条件 3: 臀部-膝盖连线角度
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
        if inter_area == 0: return 0
        box1_area, box2_area = (box1[2] - box1[0]) * (box1[3] - box1[1]), (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter_area / float(box1_area + box2_area - inter_area)

    current_alerts = []
    matched_detection_indices = set()
    
    # 💥 修改点 2: 使用更高的 IOU 阈值来确保匹配的可靠性
    TRACKING_MATCH_IOU_THRESHOLD = 0.5 
    
    # 1. 匹配和更新现有追踪者
    for person_id, state in list(person_states.items()):
        best_match_iou, best_match_idx = 0, -1
        for i, det in enumerate(detections):
            if i in matched_detection_indices: continue
            iou = calculate_iou(state['box'], det['box'])
            
            # 只有当 IOU 满足阈值且是最佳匹配时才考虑
            if iou > best_match_iou and iou >= TRACKING_MATCH_IOU_THRESHOLD: 
                best_match_iou, best_match_idx = iou, i

        if best_match_idx != -1:
            matched_detection_indices.add(best_match_idx)
            det = detections[best_match_idx]
            box, kpts = det['box'], det['kpts']
            
            state.update({'box': box, 'last_seen': frame_time})
            status_text, color = "Normal", (0, 255, 0)

            # 摔倒检测
            is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
            state['is_fallen'] = is_fallen
            
            # 静止检测
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            stationary_duration = 0
            if state.get('last_pos'):
                dist = np.sqrt((center_pos[0] - state['last_pos'][0])**2 + (center_pos[1] - state['last_pos'][1])**2)
                
                if dist < STATIONARY_PIXEL_THRESHOLD:
                    if state.get('stationary_start_time') is None: state['stationary_start_time'] = frame_time
                    stationary_duration = frame_time - state['stationary_start_time']
                    if stationary_duration > STATIONARY_TIME_THRESHOLD_SECONDS:
                        status_text = f"Fallen & Still ({int(stationary_duration)}s)" if is_fallen else f"Stationary ({int(stationary_duration)}s)"
                        color = (0, 165, 255)
                else:
                    state['stationary_start_time'] = None
                    state['last_pos'] = center_pos
            else:
                state['last_pos'] = center_pos
            
            # 摔倒状态覆盖 (如果未触发静止警告)
            if is_fallen and (color == (0, 255, 0) or stationary_duration <= STATIONARY_TIME_THRESHOLD_SECONDS):
                status_text = "FALL DETECTED"
                color = (0, 0, 255)
            
            current_alerts.append({'box': box, 'kpts': kpts, 'status': status_text, 'color': color, 'id': person_id})
            
    # 2. 添加新的追踪者
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

    # 3. 移除长时间未出现的追踪者
    for pid in [pid for pid, state in person_states.items() if frame_time - state.get('last_seen', frame_time) > 3.0]:
        del person_states[pid]
        
    return current_alerts

def draw_results(display_image, alerts):
    """绘制边界框、关键点、骨架和状态文本。"""
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        kpts, status, color, pid = alert['kpts'], alert['status'], alert['color'], alert['id']

        # 绘制边界框和状态文本
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), color, 2)
        text = f"ID {pid} | {status}"
        # 在边界框上方绘制文本，背景为黑色矩形
        (text_w, text_h), baseline = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
        cv2.rectangle(display_image, (box[0], box[1] - text_h - baseline - 5), (box[0] + text_w, box[1]), (0, 0, 0), -1)
        cv2.putText(display_image, text, (box[0], box[1] - baseline - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        # 绘制关键点 (蓝色点) 和骨架 (青色线)
        for kx, ky, kconf in kpts:
            if kconf > 0.3: cv2.circle(display_image, (int(kx), int(ky)), 3, (255, 0, 0), -1) # BGR: 蓝色
        for start, end in SKELETON:
            if kpts[start][2] > 0.3 and kpts[end][2] > 0.3:
                pt1 = (int(kpts[start][0]), int(kpts[start][1]))
                pt2 = (int(kpts[end][0]), int(kpts[end][1]))
                cv2.line(display_image, pt1, pt2, (255, 255, 0), 2) # BGR: 青色
    return display_image


# 4. ✅ 实时流检测器类

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
        self.person_states = {} # 实时追踪状态

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
            # 1. 预处理
            resized_image, pp_params = pre_process_stream(frame, self.dvpp)
            if resized_image is None: return frame, 0

            # 2. 推理
            result = self.model.execute([resized_image])

            # 3. 后处理和坐标映射
            raw_detections = []
            if result and result[0] is not None:
                output = result[0]
                if isinstance(output, np.ndarray) and len(output.shape) == 3:
                    if output.shape[1] == 56 and output.shape[2] == 8400: output = np.transpose(output, (0, 2, 1))
                    raw_detections = parse_predictions(output[0], conf_threshold=0.5)

            current_frame_detections = []
            for det in raw_detections:
                # 映射 box 和 keypoints 到原图坐标
                box = [(val - pp_params[pad]) / pp_params['scale'] 
                       for val, pad in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                kpts = [((k[0] - pp_params['pad_x']) / pp_params['scale'], 
                          (k[1] - pp_params['pad_y']) / pp_params['scale'], k[2]) 
                         for k in det['keypoints']]
                current_frame_detections.append({'box': box, 'kpts': kpts})

            # 4. 摔倒和静止状态分析
            alerts = check_fall_and_stationary(current_frame_detections, self.person_states, time.time())
            
            # 5. 绘制结果
            display_image = draw_results(frame.copy(), alerts)
            self.frame_count += 1
            
            return display_image, len(alerts)

        except Exception as e:
            print(f"❌ Frame processing error: {e}")
            traceback.print_exc()
            return frame, 0

    def stop(self):
        """释放所有资源"""
        if self.running: self.running = False
        if self.cap: self.cap.release()
        if self.model: del self.model
        if self.dvpp: del self.dvpp
        print("Detector stopped and Ascend resources released.")


# 5. ✅ 实时流主函数 (OpenCV GUI 版本)

def run_cv2_stream(camera_index=0, model_path=MODEL_PATH):
    """运行实时流，并使用 OpenCV GUI 显示窗口"""
    detector = AclLiteStreamDetector(model_path=model_path, camera_index=camera_index)
    if not detector.init():
        return

    window_name = "ACL Lite Real-time Fall/Stationary Detection"

    try:
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    except cv2.error as e:
        print("\n" + "="*80)
        print("⚠️ 致命错误: 无法创建 GUI 窗口。请确保您已开启 X11 转发 (ssh -X) 或在桌面环境下运行。")
        print(f"   OpenCV 错误: {e}")
        print("="*80 + "\n")
        detector.stop()
        return

    total_frames = 0
    start_time = time.time()
    
    print(f"--- Real-time stream started (Camera Index: {camera_index}). Press 'q' or 'Esc' to quit ---")

    try:
        while detector.running:
            result = detector.get_detected_frame()

            if result is None:
                print("\nCamera stream ended or error reading frame.")
                detector.running = False
                break

            frame, det_count = result
            total_frames += 1

            current_time = time.time()
            elapsed_time = current_time - start_time
            fps = total_frames / (elapsed_time + 1e-6)
            
            # 绘制 FPS
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            cv2.putText(frame, f"Detected: {det_count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

            # 显示帧
            cv2.imshow(window_name, frame)

            # 检查退出键 ('q' 或 Esc)
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break

    finally:
        detector.stop()
        cv2.destroyAllWindows()
        print("\n✨ Real-time detection finished.")


def main():
    camera_index_to_use = 0 
    for arg in sys.argv[1:]:
        if arg.startswith("--camera="):
            try:
                camera_index_to_use = int(arg.split('=')[1])
                print(f"Using camera index specified in arguments: {camera_index_to_use}")
            except ValueError:
                print("⚠️ Invalid camera index specified. Using default 0.")

    try:
        run_cv2_stream(camera_index=camera_index_to_use) 
    except Exception as e:
        print(f"❌ Application crashed: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()