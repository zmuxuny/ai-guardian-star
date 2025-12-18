'''import sys
import os
import time
import cv2
import numpy as np
import traceback

# 1. ✅ 路径配置
# 确保 'acllite' 库的路径正确，通常它位于当前目录的 acllite 子目录中
sys.path.append(os.path.join(os.path.dirname(__file__), "acllite"))

# 导入 ACL Lite 模块
try:
    from acllite_imageproc import AclLiteImageProc
    import constants as const
    from acllite_model import AclLiteModel
    from acllite_image import AclLiteImage
    from acllite_resource import AclLiteResource
    import acl
except ImportError:
    print("❌ 错误：无法导入 ACL Lite 模块。请确保 acllite 库已正确安装且路径设置正确。")
    sys.exit(1)


# 2. ✅ 模型和配置参数
MODEL_PATH = "/root/yolo/best.om"  # 确保这个路径指向你的 YOLOv8-pose OM 模型
MODEL_WIDTH = 640
MODEL_HEIGHT = 640

# COCO keypoints names and SKELETON for drawing
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
FALL_ASPECT_RATIO_THRESHOLD = 0.8  # 高宽比 < 0.8 视为可能摔倒
STATIONARY_PIXEL_THRESHOLD = 20    # 移动距离小于 20 像素视为静止
STATIONARY_TIME_THRESHOLD_SECONDS = 10 # 静止超过 10 秒触发警报


# 3. ✅ 核心工具函数

def nms(boxes, scores, iou_threshold=0.5):
    """简单 NMS 实现 (与之前代码相同)"""
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
    """解析 YOLOv8-pose 输出 [8400, 56]（输出已是像素坐标）"""
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
    keep = nms(boxes, scores, iou_threshold=0.6)
    return [detections[i] for i in keep]

def pre_process_stream(cv_image, dvpp):
    """实时流预处理：BGR -> RGB, Resize + Pad, NCHW (使用 NumPy/CV2)"""
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
    """通过检测框和关键点判断是否摔倒 (与之前代码相同)"""
    box_w, box_h = box[2] - box[0], box[3] - box[1]
    if box_w > 0 and box_h > 0 and (box_h / box_w) < aspect_ratio_threshold:
        return True # 宽高比触发

    try:
        # 检查关键点相对位置 (索引: 5,6 是肩膀; 11,12 是臀部)
        shoulders_y, hips_y = [], []
        if kpts[5][2] > 0.4: shoulders_y.append(kpts[5][1])
        if kpts[6][2] > 0.4: shoulders_y.append(kpts[6][1])
        if kpts[11][2] > 0.4: hips_y.append(kpts[11][1])
        if kpts[12][2] > 0.4: hips_y.append(kpts[12][1])

        if shoulders_y and hips_y:
            avg_shoulder_y = sum(shoulders_y) / len(shoulders_y)
            avg_hip_y = sum(hips_y) / len(hips_y)
            # 如果肩膀的平均 y 坐标大于臀部（更靠下），则判断为摔倒
            if avg_shoulder_y > avg_hip_y:
                return True
    except IndexError: pass
    
    return False

def check_fall_and_stationary(detections, person_states, frame_time):
    """分析检测结果，更新追踪状态，并生成警报 (与之前代码相同)"""
    def calculate_iou(box1, box2):
        x1_inter, y1_inter = max(box1[0], box2[0]), max(box1[1], box2[1])
        x2_inter, y2_inter = min(box1[2], box2[2]), min(box1[3], box2[3])
        inter_area = max(0, x2_inter - x1_inter) * max(0, y2_inter - y1_inter)
        if inter_area == 0: return 0
        box1_area, box2_area = (box1[2] - box1[0]) * (box1[3] - box1[1]), (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter_area / float(box1_area + box2_area - inter_area)

    current_alerts = []
    matched_detection_indices = set()
    
    # 1. 匹配和更新现有追踪者
    for person_id, state in list(person_states.items()):
        best_match_iou, best_match_idx = 0, -1
        for i, det in enumerate(detections):
            if i in matched_detection_indices: continue
            iou = calculate_iou(state['box'], det['box'])
            if iou > best_match_iou: best_match_iou, best_match_idx = iou, i

        if best_match_iou > 0.4:
            matched_detection_indices.add(best_match_idx)
            det = detections[best_match_idx]
            box, kpts = det['box'], det['kpts']
            
            state.update({'box': box, 'last_seen': frame_time})
            status_text, color = "Normal", (0, 255, 0) # 绿色 BGR

            # 摔倒检测
            is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
            state['is_fallen'] = is_fallen
            
            # 静止检测
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            if state.get('last_pos'):
                dist = np.sqrt((center_pos[0] - state['last_pos'][0])**2 + (center_pos[1] - state['last_pos'][1])**2)
                
                if dist < STATIONARY_PIXEL_THRESHOLD:
                    if state.get('stationary_start_time') is None: state['stationary_start_time'] = frame_time
                    stationary_duration = frame_time - state['stationary_start_time']
                    if stationary_duration > STATIONARY_TIME_THRESHOLD_SECONDS:
                        status_text = f"Fallen & Still ({int(stationary_duration)}s)" if is_fallen else f"Stationary ({int(stationary_duration)}s)"
                        color = (0, 165, 255) # 橙色
                else:
                    state['stationary_start_time'] = None
                    state['last_pos'] = center_pos
            else:
                state['last_pos'] = center_pos
            
            # 摔倒状态覆盖
            if is_fallen and (color == (0, 255, 0) or stationary_duration < STATIONARY_TIME_THRESHOLD_SECONDS):
                status_text, color = "FALL DETECTED", (0, 0, 255) # 红色
            
            current_alerts.append({'box': box, 'kpts': kpts, 'status': status_text, 'color': color, 'id': person_id})
            
    # 2. 添加新的追踪者
    next_person_id = max(person_states.keys()) + 1 if person_states else 0
    for i, det in enumerate(detections):
        if i not in matched_detection_indices:
            box = det['box']
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            is_fallen = is_person_fallen(box, det['kpts'], FALL_ASPECT_RATIO_THRESHOLD)
            
            person_states[next_person_id] = {
                'box': box, 'last_pos': center_pos, 'stationary_start_time': None,
                'is_fallen': is_fallen, 'last_seen': frame_time,
            }
            status_text = "New"
            color = (0, 255, 0)
            if is_fallen: status_text, color = "New & FALL", (0, 0, 255)
            
            current_alerts.append({'box': box, 'kpts': det['kpts'], 'status': status_text, 'color': color, 'id': next_person_id})
            next_person_id += 1

    # 3. 移除长时间未出现的追踪者
    for pid in [pid for pid, state in person_states.items() if frame_time - state.get('last_seen', frame_time) > 3.0]:
        del person_states[pid]
        
    return current_alerts

def draw_results(display_image, alerts):
    """在图像上绘制所有检测结果和警报 (与之前代码相同)"""
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        kpts, status, color, pid = alert['kpts'], alert['status'], alert['color'], alert['id']

        # 绘制检测框和状态文本
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), color, 2)
        text = f"ID {pid} | {status}"
        cv2.putText(display_image, text, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # 绘制关键点和骨骼 (BGR: 蓝色点，黄绿色线)
        for kx, ky, kconf in kpts:
            if kconf > 0.3: cv2.circle(display_image, (int(kx), int(ky)), 3, (255, 0, 0), -1) # 蓝色点
        for start, end in SKELETON:
            if kpts[start][2] > 0.3 and kpts[end][2] > 0.3:
                pt1, pt2 = (int(kpts[start][0]), int(kpts[start][1])), (int(kpts[end][0]), int(kpts[end][1]))
                cv2.line(display_image, pt1, pt2, (255, 255, 0), 2) # 黄绿色线
    return display_image


# 4. ✅ 实时流检测器类

class AclLiteStreamDetector:
    """ACL Lite 实时流检测器，用于统一管理资源和状态"""
    # 默认 USB 摄像头索引为 1
    def __init__(self, model_path=MODEL_PATH, camera_index=1): 
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
            # 初始化 Ascend 资源
            self._acl_resource = AclLiteResource()
            self._acl_resource.init()
            self.model = AclLiteModel(self.model_path)
            self.dvpp = AclLiteImageProc(self._acl_resource)
            
            # 初始化摄像头
            self.cap = cv2.VideoCapture(self.camera_index)
            # 尝试设置分辨率以获得更好的性能，如果不成功则使用默认
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

            if not self.cap.isOpened():
                raise Exception(f"Failed to open camera index {self.camera_index}. Try changing the index.")
            
            self.running = True
            print(f"✅ StreamDetector initialized (Camera Index: {self.camera_index}).")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize StreamDetector: {e}")
            traceback.print_exc()
            self.stop()
            return False

    def get_detected_frame(self):
        """捕获一帧，进行推理、后处理、状态分析并绘制结果。"""
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
                # 检查输出形状并进行转置 (YOLOv8-pose)
                if isinstance(output, np.ndarray) and len(output.shape) == 3:
                    if output.shape[1] == 56 and output.shape[2] == 8400: output = np.transpose(output, (0, 2, 1))
                    raw_detections = parse_predictions(output[0], conf_threshold=0.5)

            current_frame_detections = []
            for det in raw_detections:
                # 映射 box 和 kpts 坐标到原图大小
                box = [(val - pp_params[pad]) / pp_params['scale'] 
                       for val, pad in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                kpts = [((k[0] - pp_params['pad_x']) / pp_params['scale'], 
                         (k[1] - pp_params['pad_y']) / pp_params['scale'], k[2]) 
                        for k in det['keypoints']]
                current_frame_detections.append({'box': box, 'kpts': kpts})

            # 4. 摔倒和静止状态分析 (核心逻辑)
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
        # if self.model: del self.model
        # if self.dvpp: del self.dvpp
        print("Detector stopped and Ascend resources released.")


# 5. ✅ 实时流主函数 (OpenCV 版本)

def run_cv2_stream(camera_index=1, model_path=MODEL_PATH):
    """使用 OpenCV 运行实时检测流并显示窗口"""
    detector = AclLiteStreamDetector(model_path=model_path, camera_index=camera_index)
    if not detector.init():
        return

    # 创建一个窗口用于显示视频流
    window_name = "ACL Lite Real-time Fall/Stationary Detection"
    cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    
    total_frames = 0
    start_time = time.time()
    
    print(f"--- 实时流启动 (尝试使用摄像头索引: {camera_index})，按 'q' 或 'Esc' 退出 ---")

    try:
        while detector.running:
            result = detector.get_detected_frame()
            
            if result is None:
                detector.running = False
                break
            
            frame, det_count = result
            total_frames += 1
            
            elapsed_time = time.time() - start_time
            fps = total_frames / (elapsed_time + 1e-6)

            # 绘制 FPS 和状态信息
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            cv2.putText(frame, f"Detected: {det_count}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
            
            cv2.imshow(window_name, frame)
            
            # 检查用户退出键 ('q' 或 'Esc')
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
                
    finally:
        detector.stop()
        cv2.destroyAllWindows()
        print("✨ Real-time detection finished.")


def main():
    # 默认使用 USB 摄像头索引 1
    # 如果你的 USB 摄像头不是 1，请在此处修改：
    # 例如：camera_index = 0 (内置摄像头) 或 2
    camera_index_to_use = 0
    
    # 命令行参数解析：允许用户通过命令行覆盖摄像头索引
    for arg in sys.argv[1:]:
        if arg.startswith("--camera="):
            try:
                camera_index_to_use = int(arg.split('=')[1])
                print(f"Using camera index specified in arguments: {camera_index_to_use}")
            except ValueError:
                print("⚠️ Invalid camera index specified. Using default 1.")

    try:
        run_cv2_stream(camera_index=camera_index_to_use) 
    except Exception as e:
        print(f"❌ Application crashed: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()

'''