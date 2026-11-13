'''import sys
import os
import time
import cv2

# ✅ 必须在所有导入之前添加路径！
sys.path.append(os.path.join(os.path.dirname(__file__), "acllite"))

import numpy as np
import acl
from PIL import Image, ImageDraw, ImageFont
from acllite_imageproc import AclLiteImageProc
import constants as const
from acllite_model import AclLiteModel
from acllite_image import AclLiteImage
from acllite_resource import AclLiteResource
import traceback

# YOLOv8-pose 只检测人
labels = ["person"]

MODEL_PATH = "/root/yolo/best.om"
MODEL_WIDTH = 640
MODEL_HEIGHT = 640

# COCO keypoints names
KEYPOINT_NAMES = [
    "nose", "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist", "left_hip", "right_hip",
    "left_knee", "right_knee", "left_ankle", "right_ankle"
]

# 骨骼连接线（用于可视化）
SKELETON = [
    [15, 13], [13, 11], [16, 14], [14, 12], [11, 12],
    [5, 11], [6, 12], [5, 6], [5, 7], [6, 8], [7, 9], [8, 10],
    [1, 2], [0, 1], [0, 2], [1, 3], [2, 4], [3, 5], [4, 6]
]

# ============================================================================
# 🚀 摔倒和长时间静止监测配置
# ============================================================================
FALL_ASPECT_RATIO_THRESHOLD = 0.8
STATIONARY_PIXEL_THRESHOLD = 20
STATIONARY_TIME_THRESHOLD_SECONDS = 10
# ============================================================================

# 全局变量：用于实时流中追踪每个人的状态
# person_states: {id: {'box': [x1,y1,x2,y2], 'last_pos': (cx, cy), 'stationary_start_time': None/float, 'is_fallen': bool, 'last_seen': float}}
global_person_states = {}


def sigmoid(x):
    return 1 / (1 + np.exp(-np.clip(x, -10, 10)))

def nms(boxes, scores, iou_threshold=0.5):
    """简单 NMS 实现"""
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
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

        if obj_conf < conf_threshold:
            continue

        x1, y1, x2, y2 = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
        kpts = pred[5:56].reshape(17, 3)
        # 类别置信度在 YOLOv8-pose 的 Ascend 版本中经常被合并，我们假设它是 person (index 0)
        detection = {'box': [x1, y1, x2, y2], 'score': obj_conf, 'keypoints': kpts, 'class_id': 0}
        detections.append(detection)

    if not detections:
        return []

    boxes = np.array([d['box'] for d in detections])
    scores = np.array([d['score'] for d in detections])
    keep = nms(boxes, scores, iou_threshold=0.6)
    return [detections[i] for i in keep]

# --- 实时流专用的预处理函数 (使用 cv2 图像作为输入) ---
def pre_process_stream(cv_image, dvpp):
    """
    预处理：使用 cv2 图像，resize + pad 到 640x640。
    注意：这里避免了 PIL 库的磁盘I/O，直接操作 np 数组。
    """
    try:
        orig_h, orig_w = cv_image.shape[:2]
        
        # 1. BGR -> RGB (模型输入需要 RGB)
        rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)

        # 2. 计算缩放和填充
        scale = min(MODEL_WIDTH / orig_w, MODEL_HEIGHT / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)
        pad_x, pad_y = (MODEL_WIDTH - new_w) // 2, (MODEL_HEIGHT - new_h) // 2

        # 3. Resize
        resized_img = cv2.resize(rgb_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        
        # 4. Padding (np.pad 更快)
        padded_img = np.full((MODEL_HEIGHT, MODEL_WIDTH, 3), 114, dtype=np.uint8) # 灰色填充
        padded_img[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized_img
        
        # 5. 归一化和 NCHW 转换 (模型输入要求)
        rgb_np = np.array(padded_img, dtype=np.float32) / 255.0
        nchw_img = np.transpose(rgb_np, (2, 0, 1))[np.newaxis, :, :, :]
        nchw_img = np.ascontiguousarray(nchw_img)
        
        return nchw_img, {'scale': scale, 'pad_x': pad_x, 'pad_y': pad_y, 'orig_w': orig_w, 'orig_h': orig_h}
    except Exception as e:
        print(f"❌ Stream Pre-process error: {e}")
        return None, None

def is_person_fallen(box, kpts, aspect_ratio_threshold):
    """通过检测框宽高比和关键点相对位置来判断是否摔倒。"""
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
            # 如果肩膀的平均 y 坐标大于臀部（在图像中更靠下），则判断为摔倒
            if avg_shoulder_y > avg_hip_y:
                return True
    except IndexError: pass
    
    return False

def check_fall_and_stationary(detections, person_states, frame_time):
    """分析当前帧的检测结果，更新每个人的状态，并检测摔倒和静止。"""
    def calculate_iou(box1, box2):
        x1_inter, y1_inter = max(box1[0], box2[0]), max(box1[1], box2[1])
        x2_inter, y2_inter = min(box1[2], box2[2]), min(box1[3], box2[3])
        inter_area = max(0, x2_inter - x1_inter) * max(0, y2_inter - y1_inter)
        if inter_area == 0: return 0
        box1_area, box2_area = (box1[2] - box1[0]) * (box1[3] - box1[1]), (box2[2] - box2[0]) * (box2[3] - box2[1])
        return inter_area / float(box1_area + box2_area - inter_area)

    current_alerts = []
    matched_detection_indices = set()
    
    # 1. 尝试将当前帧的检测结果与已追踪的人进行匹配
    for person_id, state in list(person_states.items()):
        best_match_iou, best_match_idx = 0, -1
        for i, det in enumerate(detections):
            if i in matched_detection_indices: continue
            iou = calculate_iou(state['box'], det['box'])
            if iou > best_match_iou:
                best_match_iou, best_match_idx = iou, i

        if best_match_iou > 0.4:  # IoU阈值，匹配成功
            matched_detection_indices.add(best_match_idx)
            det = detections[best_match_idx]
            box, kpts = det['box'], det['kpts']
            
            state.update({'box': box, 'last_seen': frame_time})
            status_text, color = "Normal", (0, 255, 0) # 绿色 BGR

            # a. 摔倒检测
            is_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD)
            state['is_fallen'] = is_fallen

            # b. 静止检测
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            # 只有当 'last_pos' 存在时才计算距离，新人的 'last_pos' 在第 2 步初始化
            if state.get('last_pos'):
                dist = np.sqrt((center_pos[0] - state['last_pos'][0])**2 + (center_pos[1] - state['last_pos'][1])**2)
                
                if dist < STATIONARY_PIXEL_THRESHOLD:
                    if state.get('stationary_start_time') is None:
                        state['stationary_start_time'] = frame_time
                    stationary_duration = frame_time - state['stationary_start_time']
                    if stationary_duration > STATIONARY_TIME_THRESHOLD_SECONDS:
                        status_text = f"Fallen & Still ({int(stationary_duration)}s)" if is_fallen else f"Stationary ({int(stationary_duration)}s)"
                        color = (0, 165, 255) # 橙色
                else:
                    state['stationary_start_time'] = None
                    state['last_pos'] = center_pos
            else:
                state['last_pos'] = center_pos
            
            # 如果是摔倒状态，覆盖颜色为红色
            if is_fallen and (color != (0, 165, 255) or stationary_duration < STATIONARY_TIME_THRESHOLD_SECONDS):
                status_text, color = "FALL DETECTED", (0, 0, 255)  # 红色
            
            current_alerts.append({'box': box, 'kpts': kpts, 'status': status_text, 'color': color, 'id': person_id})
            
    # 2. 将未匹配的检测结果视为新出现的人
    next_person_id = max(person_states.keys()) + 1 if person_states else 0
    for i, det in enumerate(detections):
        if i not in matched_detection_indices:
            box = det['box']
            center_pos = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
            person_states[next_person_id] = {
                'box': box, 'last_pos': center_pos, 'stationary_start_time': None,
                'is_fallen': is_person_fallen(box, det['kpts'], FALL_ASPECT_RATIO_THRESHOLD), 
                'last_seen': frame_time,
            }
            status_text = "New"
            color = (0, 255, 0)
            if person_states[next_person_id]['is_fallen']:
                 status_text, color = "New & FALL", (0, 0, 255)
            
            current_alerts.append({'box': box, 'kpts': det['kpts'], 'status': status_text, 'color': color, 'id': next_person_id})
            next_person_id += 1

    # 3. 移除长时间未出现的追踪者 (超过 3 秒)
    for pid in [pid for pid, state in person_states.items() if frame_time - state.get('last_seen', frame_time) > 3.0]:
        del person_states[pid]
        
    return current_alerts

def draw_results(display_image, alerts):
    """在图像上绘制所有检测结果和警报"""
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        kpts, status, color, pid = alert['kpts'], alert['status'], alert['color'], alert['id']

        # 绘制检测框和状态文本
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), color, 2)
        text = f"ID {pid} | {status}"
        cv2.putText(display_image, text, (box[0], box[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        
        # 绘制关键点和骨骼
        for kx, ky, kconf in kpts:
            if kconf > 0.3: cv2.circle(display_image, (int(kx), int(ky)), 3, (255, 0, 0), -1)
        for start, end in SKELETON:
            if kpts[start][2] > 0.3 and kpts[end][2] > 0.3:
                pt1, pt2 = (int(kpts[start][0]), int(kpts[start][1])), (int(kpts[end][0]), int(kpts[end][1]))
                cv2.line(display_image, pt1, pt2, (0, 255, 255), 2)
    return display_image

# ============================================================================
# 🚨 实时流重构：使用 OpenCV/ACL Lite 进行实时检测
# ============================================================================

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
            if not self.cap.isOpened():
                raise Exception(f"Failed to open camera {self.camera_index}")
            
            self.running = True
            print("✅ StreamDetector initialized successfully.")
            return True
        except Exception as e:
            print(f"❌ Failed to initialize StreamDetector: {e}")
            self.stop()
            return False

    def get_detected_frame(self):
        """
        捕获一帧，进行推理、后处理、状态分析并绘制结果。
        Returns: tuple(cv_image, det_count) or None
        """
        if not self.running or not self.cap or not self.cap.isOpened():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            self.running = False
            return None
            
        try:
            # 1. 预处理
            resized_image, pp_params = pre_process_stream(frame, self.dvpp)
            if resized_image is None:
                return frame, 0

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
                # 将 box 坐标从 640x640 映射回原图大小
                box = [(val - pp_params[pad]) / pp_params['scale'] 
                       for val, pad in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                # 将关键点 kpts 坐标从 640x640 映射回原图大小
                kpts = [((k[0] - pp_params['pad_x']) / pp_params['scale'], 
                         (k[1] - pp_params['pad_y']) / pp_params['scale'], k[2]) 
                        for k in det['keypoints']]
                current_frame_detections.append({'box': box, 'kpts': kpts})

            # 4. 摔倒和静止状态分析 (核心逻辑)
            current_time = time.time()
            alerts = check_fall_and_stationary(current_frame_detections, self.person_states, current_time)

            # 5. 绘制结果
            display_image = draw_results(frame.copy(), alerts)
            
            self.frame_count += 1
            
            return display_image, len(alerts)

        except Exception as e:
            print(f"❌ Frame processing error: {e}")
            traceback.print_exc()
            return frame, 0


    def stop(self):
        if self.running:
            self.running = False
            print("Stopping detector...")
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.model:
            del self.model
            self.model = None
        if self.dvpp:
            del self.dvpp
            self.dvpp = None
        if self._acl_resource:
            self._acl_resource.release()
            self._acl_resource = None
        
        # 清理全局状态
        global global_person_states
        global_person_states = {}
        
        print("Detector stopped and resources released.")

# ============================================================================
# 🚨 实时流主函数 (OpenCV 版本)
# ============================================================================

def run_cv2_stream(camera_index=0, model_path=MODEL_PATH):
    """使用 OpenCV 运行实时检测流并显示窗口"""
    detector = AclLiteStreamDetector(model_path=model_path, camera_index=camera_index)
    if not detector.init():
        return

    cv2.namedWindow("ACL Lite Real-time Fall Detection", cv2.WINDOW_AUTOSIZE)
    
    total_frames = 0
    start_time = time.time()
    
    print("--- 实时流启动，按 'q' 或 'Esc' 退出 ---")

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
            
            cv2.imshow("ACL Lite Real-time Fall Detection", frame)
            
            # 检查用户退出键 ('q' 或 'Esc')
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == 27:
                break
                
    finally:
        detector.stop()
        cv2.destroyAllWindows()
        print("✨ Real-time detection finished.")

# ============================================================================
# 🚨 主函数入口调整
# ============================================================================
def main():
    # 简化主函数，直接启动实时流
    try:
        # 您可以根据需要修改 camera_index (例如，使用 sys.argv 解析)
        run_cv2_stream(camera_index=0) 
    except Exception as e:
        print(f"❌ Application crashed: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    main()

# --- 旧代码兼容性说明 ---
# 
# def single_detect(): # 移除，使用原有的 ACL Lite 框架中的 process_image 代替
#     pass 
#
# # if __name__ == "__main__":
# #     run_matplotlib_stream() # 已被 run_cv2_stream 替代
# 
# 
# # 原有的 ACL Lite 代码中的 process_video 和 process_camera 函数不再需要，
# # 因为新的 run_cv2_stream 已经包含了实时摄像头的核心逻辑。
'''