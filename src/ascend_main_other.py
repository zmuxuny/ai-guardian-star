# ascend_main_other.py
import sys
import os
import time
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
import cv2
cv2.setNumThreads(1)
import numpy as np
import traceback
import threading
import json
import queue
import glob
from datetime import datetime
import uuid
from collections import deque

# ---------------------- 外部依赖 ----------------------
import paho.mqtt.client as mqtt
import websocket # pip install websocket-client

# 保持工作区路径可用
current_file_dir = os.path.dirname(os.path.abspath(__file__))
if current_file_dir not in sys.path:
    sys.path.append(current_file_dir)

# 导入本地模块
from ascend_video_stream import start_stream, update_frame
try:
    import ascend_voice_stream as audio_hw  # 导入音频硬件模块
except Exception:
    class _AudioStub:
        @staticmethod
        def start_audio_service():
            return None

        @staticmethod
        def get_audio_frame():
            return None

        @staticmethod
        def put_audio_frame(_frame):
            return None

    audio_hw = _AudioStub()

try:
    from vlm_client import VLMClient
except Exception:
    VLMClient = None

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
    print(f"   导入详情: {e}")
    print("   请先执行: source /usr/local/Ascend/ascend-toolkit/set_env.sh")
    raise RuntimeError("ACL Lite environment is not ready") from e

# ---------------------- 配置参数 ----------------------
# 1. 模型配置
MODEL_CANDIDATES = [
    os.path.join(current_file_dir, "best.om"),
    os.path.join(os.getcwd(), "best.om"),
    os.path.join(os.path.dirname(current_file_dir), "best.om"),
    "/root/yolo/src/best.om",
    "/root/yolo/best.om",
]
MODEL_PATH = next((path for path in MODEL_CANDIDATES if os.path.exists(path)), MODEL_CANDIDATES[-1])
MODEL_WIDTH = 640
MODEL_HEIGHT = 640
ACL_MODEL_EXEC_LOCK = threading.Lock()

# 2. MQTT 配置
MQTT_BROKER = "47.108.167.0"
MQTT_PORT = 8883
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_CA_CERT = os.environ.get("MQTT_CA_CERT", "")
ALERT_TOPIC = "ai_guardian/alerts/fall"
STRANGER_ALERT_TOPIC = "ai_guardian/alerts/stranger"
SIT_ALERT_TOPIC = "ai_guardian/alerts/sit"
FACE_ALERT_TOPIC = "ai_guardian/alerts/face"
DEVICE_ID = "ascend_board"
KNOWN_FACE_DIR = os.path.join(current_file_dir, "known_faces")
FACE_DEBUG_DIR = os.path.join(current_file_dir, "debug_faces")
FACE_DET_MODEL_CANDIDATES = [
    os.path.join(current_file_dir, "shufflev2_face.om"),
    os.path.join(current_file_dir, "models", "shufflev2_face.om"),
    "/root/yolo/src/shufflev2_face.om",
    "/root/yolo/shufflev2_face.om",
    os.path.join(current_file_dir, "best_face.om"),
    os.path.join(current_file_dir, "models", "best_face.om"),
    "/root/yolo/src/best_face.om",
    "/root/yolo/best_face.om",
    os.path.join(current_file_dir, "last_pose.om"),
    os.path.join(current_file_dir, "last.om"),
    os.path.join(current_file_dir, "models", "last_pose.om"),
    os.path.join(current_file_dir, "models", "last.om"),
    "/root/yolo/src/last_pose.om",
    "/root/yolo/src/last.om",
    "/root/yolo/last_pose.om",
    "/root/yolo/last.om",
]
FACE_DET_MODEL_PATH = next((path for path in FACE_DET_MODEL_CANDIDATES if os.path.exists(path)), None)
FACE_REC_MODEL_CANDIDATES = [
    os.path.join(current_file_dir, "face_rec_mbf.om"),
    os.path.join(current_file_dir, "models", "face_rec_mbf.om"),
    "/root/yolo/src/face_rec_mbf.om",
    "/root/yolo/face_rec_mbf.om",
    os.path.join(current_file_dir, "face_rec_arc_82.om"),
    os.path.join(current_file_dir, "face_rec_arc.om"),
    os.path.join(current_file_dir, "face_rec_arcface.om"),
    os.path.join(current_file_dir, "models", "face_rec_arc_82.om"),
    os.path.join(current_file_dir, "models", "face_rec_arc.om"),
    os.path.join(current_file_dir, "models", "face_rec_arcface.om"),
    "/root/yolo/src/face_rec_arc_82.om",
    "/root/yolo/src/face_rec_arc.om",
    "/root/yolo/src/face_rec_arcface.om",
    "/root/yolo/face_rec_arc_82.om",
    "/root/yolo/face_rec_arc.om",
    "/root/yolo/face_rec_arcface.om",
]
USE_ARCFACE_ON_BOARD = True
FACE_REC_MODEL_PATH = (
    next((path for path in FACE_REC_MODEL_CANDIDATES if os.path.exists(path)), None)
    if USE_ARCFACE_ON_BOARD
    else None
)
FACE_RECOGNITION_COOLDOWN = 3.0
FACE_GLOBAL_RECOGNITION_COOLDOWN = 4.0
FACE_TRACK_MAX_AGE = 4.0
FACE_MATCH_THRESHOLD = 0.62
FACE_MATCH_SIMILARITY_ARCFACE = 0.45
FACE_MATCH_SIMILARITY_ARCFACE_STRONG = FACE_MATCH_SIMILARITY_ARCFACE
FACE_SINGLE_IDENTITY_SIMILARITY_ARCFACE = 0.45
FACE_MATCH_SIMILARITY_MARGIN_ARCFACE = 0.08
FACE_MATCH_SIMILARITY_MARGIN_FALLBACK = 0.10
FACE_STRANGER_DISTANCE_FALLBACK = 0.74
FACE_STRANGER_SIMILARITY_ARCFACE = FACE_MATCH_SIMILARITY_ARCFACE
FACE_STRANGER_SIMILARITY_ARCFACE_SINGLE_ID = 0.05
FACE_STABLE_TIME = 0.2
FACE_RETRY_UNKNOWN_INTERVAL = 8.0
FACE_VOTE_WINDOW = 4
FACE_VOTE_MIN_KNOWN = 2
FACE_VOTE_MIN_UNKNOWN = 3
FACE_STRANGER_MIN_AGE = 2.0
FACE_TRACK_REUSE_IOU_STRICT = 0.45
FACE_TRACK_REUSE_DIST_STRICT = 0.18
FACE_TRACK_MATCH_MIN_IOU = 0.08
FACE_TRACK_MATCH_MAX_NORM_DIST = 0.55
FACE_TRACK_KNOWN_SCORE_BONUS = 0.12
FACE_TRACK_KNOWN_REID_TTL = 6.0
FACE_TRACK_KNOWN_REID_MAX_NORM_DIST = 0.42
FACE_KNOWN_OWNER_TTL = 2.5
FACE_ACTIVE_KNOWN_TRANSFER_IOU = 0.35
FACE_ACTIVE_KNOWN_TRANSFER_NORM_DIST = 0.22
FACE_DET_BOX_DISPLAY_TTL = 8.0
FACE_DET_BOX_PAD_RATIO = 0.45
FACE_DET_INTERVAL = 1.50
FACE_RECOG_MIN_FACEDET_SCORE = 0.55
FACE_RECOG_MIN_CROP_SCORE = 0.80
FACE_RECOG_MIN_QUALITY_SCORE = 1.05
SAVE_FACE_DEBUG_IMAGES = False
SAVE_STRANGER_FACE_DEBUG_IMAGES = False
SAVE_FACE_RECOG_INPUTS = os.getenv("AI_GUARDIAN_SAVE_FACE_RECOG_INPUTS", "0").lower() in ("1", "true", "on", "yes")

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
FALL_CONFIRM_SECONDS = 0.6
FALL_RELEASE_SECONDS = 1.0
FRAME_EDGE_MARGIN = 12
VLM_EVENTS_ENABLED = os.getenv("AI_GUARDIAN_VLM_ENABLED", "1").lower() not in ("0", "false", "off", "no")
VLM_NEW_PERSON_DELAY_SECONDS = float(os.getenv("AI_GUARDIAN_VLM_NEW_PERSON_DELAY", "1.2"))
VLM_LONG_SIT_THRESHOLD_SECONDS = float(os.getenv("AI_GUARDIAN_VLM_LONG_SIT_SECONDS", str(STATIONARY_TIME_THRESHOLD_SECONDS)))
VLM_MAX_SUMMARY_LENGTH = int(os.getenv("AI_GUARDIAN_VLM_MAX_SUMMARY_LENGTH", "80"))
VLM_RETRY_INTERVAL_SECONDS = float(os.getenv("AI_GUARDIAN_VLM_RETRY_SECONDS", "5.0"))
VLM_PERIODIC_ENABLED = os.getenv("AI_GUARDIAN_VLM_PERIODIC_ENABLED", "1").lower() not in ("0", "false", "off", "no")
VLM_PERIODIC_INTERVAL_SECONDS = float(os.getenv("AI_GUARDIAN_VLM_PERIODIC_SECONDS", "5.0"))


def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def save_face_debug_image(face_bgr, person_id, face_score, now_ts, force=False):
    if (not SAVE_FACE_DEBUG_IMAGES and not force) or face_bgr is None or face_bgr.size == 0:
        return None

    ensure_dir(FACE_DEBUG_DIR)
    timestamp = datetime.fromtimestamp(now_ts).strftime("%Y%m%d_%H%M%S_%f")
    score_text = "na" if face_score is None else f"{face_score:.3f}"
    file_name = f"person_{person_id}_{timestamp}_score_{score_text}.jpg"
    save_path = os.path.join(FACE_DEBUG_DIR, file_name)
    try:
        cv2.imwrite(save_path, face_bgr)
        return save_path
    except Exception as e:
        print(f"[FaceDebug] save failed: {e}")
        return None


def clamp(value, lower, upper):
    return max(lower, min(upper, value))


def get_pose_keypoint(kpts, idx, conf_thresh=0.35):
    if idx >= len(kpts):
        return None
    x, y, conf = kpts[idx]
    if float(conf) <= conf_thresh:
        return None
    return float(x), float(y)


def compute_iou(box_a, box_b):
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter = inter_w * inter_h
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter + 1e-6
    return inter / union


def box_center(box):
    return ((box[0] + box[2]) * 0.5, (box[1] + box[3]) * 0.5)


def box_diag(box):
    return max(1.0, ((box[2] - box[0]) ** 2 + (box[3] - box[1]) ** 2) ** 0.5)


def build_face_embedding(face_bgr):
    if face_bgr is None or face_bgr.size == 0:
        return None

    gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_LINEAR)
    small = gray.astype(np.float32) / 255.0

    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten().astype(np.float32)
    hist /= (np.linalg.norm(hist) + 1e-6)

    feature = np.concatenate([small.flatten(), hist], axis=0).astype(np.float32)
    feature /= (np.linalg.norm(feature) + 1e-6)
    return feature


def build_face_embedding_from_gray(face_gray):
    if face_gray is None or face_gray.size == 0:
        return None
    gray = cv2.equalizeHist(face_gray)
    gray = cv2.resize(gray, (48, 48), interpolation=cv2.INTER_LINEAR)
    small = gray.astype(np.float32) / 255.0

    hist = cv2.calcHist([gray], [0], None, [32], [0, 256]).flatten().astype(np.float32)
    hist /= (np.linalg.norm(hist) + 1e-6)

    grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    grad = cv2.magnitude(grad_x, grad_y)
    grad_small = cv2.resize(grad, (24, 24), interpolation=cv2.INTER_LINEAR).flatten()
    grad_small /= (np.linalg.norm(grad_small) + 1e-6)

    feature = np.concatenate([small.flatten(), hist, grad_small], axis=0).astype(np.float32)
    feature /= (np.linalg.norm(feature) + 1e-6)
    return feature


class ArcFaceRecognizerACL:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.enabled = False
        self._infer_lock = threading.Lock()
        self._last_fail_ts = 0.0
        self._permanently_disabled = False
        model_name = os.path.basename(model_path).lower() if model_path else ""
        self.input_layout = "NHWC" if "arc_82" in model_name or "face_rec_arc" in model_name else "NCHW"
        self.input_dtype = np.float32
        self._trial_modes = [
            ("NCHW", np.float32),
            ("NHWC", np.float32),
        ]

    def init(self):
        if not self.model_path or not os.path.exists(self.model_path):
            if not USE_ARCFACE_ON_BOARD:
                print("[FaceRec] recognizer disabled on board, fallback to lightweight embedding.")
            else:
                print("[FaceRec] recognizer model not found, fallback to lightweight embedding.")
            return
        try:
            self.model = AclLiteModel(self.model_path)
            self.enabled = True
            print(
                f"[FaceRec] recognizer loaded: {self.model_path} | "
                f"trial={self.input_layout} {self.input_dtype.__name__}"
            )
            self._log_model_info()
        except Exception as e:
            self.model = None
            self.enabled = False
            print(f"[FaceRec] recognizer init failed, fallback to lightweight embedding: {e}")

    def _log_model_info(self):
        try:
            model_desc = getattr(self.model, "_model_desc", None)
            if model_desc is None:
                return
            num_inputs = self._safe_call(acl.mdl.get_num_inputs, model_desc)
            num_outputs = self._safe_call(acl.mdl.get_num_outputs, model_desc)
            print(f"[FaceRec] Model IO count: inputs={num_inputs} outputs={num_outputs}")
            if isinstance(num_inputs, int):
                for i in range(num_inputs):
                    dims = self._safe_call(acl.mdl.get_input_dims, model_desc, i)
                    size = self._safe_call(acl.mdl.get_input_size_by_index, model_desc, i)
                    print(f"[FaceRec] Input[{i}] dims={dims} size={size}")
            if isinstance(num_outputs, int):
                for i in range(num_outputs):
                    dims = self._safe_call(acl.mdl.get_output_dims, model_desc, i)
                    size = self._safe_call(acl.mdl.get_output_size_by_index, model_desc, i)
                    print(f"[FaceRec] Output[{i}] dims={dims} size={size}")
        except Exception as e:
            print(f"[FaceRec] Model info probe failed: {e}")

    def _safe_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def infer(self, face_bgr):
        if not self.enabled or self.model is None or face_bgr is None or face_bgr.size == 0:
            return None
        if self._permanently_disabled:
            return None
        if time.time() - self._last_fail_ts < 1.0:
            return None

        resized = cv2.resize(face_bgr, (112, 112), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        normalized = (rgb - 127.5) / 128.0

        preferred = [(self.input_layout, self.input_dtype)]
        fallbacks = [mode for mode in self._trial_modes if mode != preferred[0]]

        last_error = None
        with self._infer_lock:
            for layout, dtype in preferred + fallbacks:
                try:
                    if layout == "NHWC":
                        model_input = normalized[np.newaxis, :, :, :]
                    else:
                        model_input = np.transpose(normalized, (2, 0, 1))[np.newaxis, :, :, :]
                    model_input = np.ascontiguousarray(model_input, dtype=dtype)
                    with ACL_MODEL_EXEC_LOCK:
                        result = self.model.execute([model_input])
                    if result is None or result[0] is None:
                        raise RuntimeError("AclLiteModel.execute returned empty result")
                    embedding = np.array(result[0]).astype(np.float32).reshape(-1)
                    if embedding.size == 0:
                        raise RuntimeError("face embedding is empty")
                    embedding /= (np.linalg.norm(embedding) + 1e-6)
                    if (layout, dtype) != (self.input_layout, self.input_dtype):
                        self.input_layout = layout
                        self.input_dtype = dtype
                        print(f"[FaceRec] Switched input mode to {layout} {dtype.__name__}")
                    return embedding
                except Exception as e:
                    last_error = e
                    continue

        self._last_fail_ts = time.time()
        self.enabled = False
        self._permanently_disabled = True
        print(f"[FaceRec] recognizer inference failed, disabling ACL recognizer: {last_error}")
        return None


class YoloFaceDetectorACL:
    def __init__(self, model_path):
        self.model_path = model_path
        self.model = None
        self.enabled = False
        self.input_dtype = np.float32
        self.input_layout = "NCHW"

    def init(self):
        if not self.model_path or not os.path.exists(self.model_path):
            print("[FaceDet] Face detector model not found, fallback to pose head crop.")
            return
        try:
            self.model = AclLiteModel(self.model_path)
            self.enabled = True
            print(
                f"[FaceDet] Face detector loaded: {self.model_path} | "
                f"trial={self.input_layout} {self.input_dtype.__name__}"
            )
        except Exception as e:
            self.model = None
            self.enabled = False
            print(f"[FaceDet] init failed, fallback to pose head crop: {e}")

    def detect(self, bgr_image, conf_threshold=0.35):
        if not self.enabled or self.model is None or bgr_image is None or bgr_image.size == 0:
            return []

        try:
            model_input, pp = pre_process_stream(
                bgr_image,
                input_dtype=self.input_dtype,
                input_layout=self.input_layout,
            )
            if model_input is None or pp is None:
                return []
            with ACL_MODEL_EXEC_LOCK:
                result = self.model.execute([model_input])
            if result is None or result[0] is None:
                return []
            output = result[0]
            if not isinstance(output, np.ndarray):
                output = np.array(output)
            if output.ndim == 3 and output.shape[1] == 5:
                output = np.transpose(output, (0, 2, 1))
            predictions = output[0] if output.ndim == 3 else output
            detections = parse_face_predictions(predictions, conf_threshold=conf_threshold)

            final_boxes = []
            for det in detections:
                x1, y1, x2, y2 = det["box"]
                mapped = [
                    (x1 - pp["pad_x"]) / pp["scale"],
                    (y1 - pp["pad_y"]) / pp["scale"],
                    (x2 - pp["pad_x"]) / pp["scale"],
                    (y2 - pp["pad_y"]) / pp["scale"],
                ]
                final_boxes.append({"box": mapped, "score": det["score"]})
            return final_boxes
        except Exception as e:
            print(f"[FaceDet] detect failed: {e}")
            return []


class FaceLibrary:
    def __init__(self, library_dir=KNOWN_FACE_DIR, recognizer=None):
        self.library_dir = library_dir
        self.arcface = recognizer
        self.entries = []
        self.centroids = {}
        self.enabled = False
        self.recognizer = None
        self.label_to_name = {}
        self.face_cascade = None
        self._diag_last_log = {}

    def _log_diag(self, key, message, interval=5.0):
        now = time.time()
        if now - self._diag_last_log.get(key, 0.0) >= interval:
            print(message)
            self._diag_last_log[key] = now

    def _rebuild_lbph(self, train_images, train_labels):
        self.recognizer = None
        self.label_to_name = {}
        if not train_images:
            return
        for label_id, person_name in train_labels:
            self.label_to_name[label_id] = person_name
        if hasattr(cv2, "face"):
            try:
                recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
                images = [np.array(img, dtype=np.uint8) for img in train_images]
                labels = np.array([label_id for label_id, _ in train_labels], dtype=np.int32)
                recognizer.train(images, labels)
                self.recognizer = recognizer
            except Exception as e:
                self.recognizer = None
                print(f"[Face] LBPH unavailable, fallback to embedding only: {e}")

    def _ensure_detector(self):
        if self.face_cascade is not None:
            return
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        self.face_cascade = cascade if not cascade.empty() else None

    def _rebuild_centroids(self):
        grouped = {}
        for entry in self.entries:
            name = entry.get("name")
            embedding = entry.get("embedding")
            if not name or embedding is None:
                continue
            grouped.setdefault(name, []).append(np.array(embedding, dtype=np.float32))

        centroids = {}
        for name, embeddings in grouped.items():
            if not embeddings:
                continue
            matrix = np.stack(embeddings, axis=0)
            if len(embeddings) >= 3:
                mean = np.mean(matrix, axis=0)
                distances = np.linalg.norm(matrix - mean, axis=1)
                keep_count = max(2, int(np.ceil(len(embeddings) * 0.8)))
                keep_indices = np.argsort(distances)[:keep_count]
                matrix = matrix[keep_indices]
            centroid = np.mean(matrix, axis=0).astype(np.float32)
            centroid /= (np.linalg.norm(centroid) + 1e-6)
            centroids[name] = centroid
        self.centroids = centroids

    def _extract_face_bgr(self, image):
        if image is None or image.size == 0:
            return None
        self._ensure_detector()

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        if self.face_cascade is not None:
            faces = self.face_cascade.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=4,
                minSize=(36, 36),
            )
            if len(faces) > 0:
                x, y, w, h = max(faces, key=lambda item: item[2] * item[3])
                crop = image[y:y + h, x:x + w]
            else:
                crop = image
        else:
            crop = image

        if crop is None or crop.size == 0 or crop.shape[0] < 24 or crop.shape[1] < 24:
            return None
        return crop

    def _extract_face_gray(self, image):
        face_bgr = self._extract_face_bgr(image)
        if face_bgr is None:
            return None
        gray = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        return cv2.resize(gray, (128, 128), interpolation=cv2.INTER_LINEAR)

    def load(self):
        ensure_dir(self.library_dir)
        self.entries = []
        self.centroids = {}
        self.label_to_name = {}
        train_images = []
        train_labels = []
        label_id = 0

        for person_name in sorted(os.listdir(self.library_dir)):
            person_dir = os.path.join(self.library_dir, person_name)
            if not os.path.isdir(person_dir):
                continue
            person_has_sample = False

            for file_name in sorted(os.listdir(person_dir)):
                if not file_name.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                    continue
                img_path = os.path.join(person_dir, file_name)
                image = cv2.imread(img_path)
                face_bgr = image if self.arcface is not None and self.arcface.enabled else self._extract_face_bgr(image)
                face_gray = self._extract_face_gray(image)
                embedding = None
                if self.arcface is not None and self.arcface.enabled:
                    if face_bgr is None:
                        print(f"[FaceDiag] skip sample, no usable face crop: {img_path}")
                        continue
                    embedding = self.arcface.infer(face_bgr)
                    if embedding is None:
                        print(f"[FaceDiag] ACL recognizer failed, fallback to CPU embedding: {img_path}")
                elif self.arcface is not None and face_bgr is not None:
                    embedding = self.arcface.infer(face_bgr)
                if embedding is None:
                    embedding = (
                        build_face_embedding_from_gray(face_gray)
                        if face_gray is not None
                        else build_face_embedding(image)
                    )
                if embedding is None:
                    print(f"[Face] Skip invalid face sample: {img_path}")
                    continue
                self.entries.append({
                    "name": person_name,
                    "embedding": embedding,
                    "path": img_path,
                })
                if face_gray is not None:
                    train_images.append(face_gray)
                    train_labels.append((label_id, person_name))
                    person_has_sample = True

            if person_has_sample:
                self.label_to_name[label_id] = person_name
                label_id += 1

        self._rebuild_lbph(train_images, train_labels)
        self._rebuild_centroids()

        self.enabled = len(self.entries) > 0
        print(
            f"[Face] library_dir={self.library_dir} loaded={len(self.entries)} "
            f"identities={len(self.centroids)} "
            f"recognizer={'on' if self.arcface is not None and self.arcface.enabled else 'off'} "
            f"lbph={'on' if self.recognizer is not None else 'off'}"
        )
        if not self.enabled:
            print("[Face] No known faces found. Add images to known_faces/<person_name>/*.jpg")

    def recognize(self, face_bgr):
        if not self.enabled:
            self._log_diag("library_disabled", "[FaceDiag] face library is disabled or empty")
            return "unregistered", None

        face_gray = self._extract_face_gray(face_bgr)
        face_color = face_bgr if self.arcface is not None and self.arcface.enabled else self._extract_face_bgr(face_bgr)
        if self.recognizer is not None and face_gray is not None and not (self.arcface is not None and self.arcface.enabled):
            try:
                label_id, confidence = self.recognizer.predict(face_gray)
                if label_id in self.label_to_name and confidence < 65.0:
                    return f"known:{self.label_to_name[label_id]}", float(confidence)
            except Exception:
                pass

        embedding = None
        if self.arcface is not None and self.arcface.enabled and face_color is None:
            self._log_diag("live_face_crop_empty", "[FaceDiag] live face crop is empty")
            return "unknown", None
        if self.arcface is not None and face_color is not None:
            embedding = self.arcface.infer(face_color)
            if self.arcface.enabled and embedding is None:
                shape = getattr(face_color, "shape", None)
                self._log_diag("live_arcface_failed", f"[FaceDiag] live ACL face embedding failed, face_shape={shape}")
                return "unknown", None
        if embedding is None:
            embedding = (
                build_face_embedding_from_gray(face_gray)
                if face_gray is not None
                else build_face_embedding(face_bgr)
            )
        if embedding is None:
            self._log_diag("live_embedding_empty", "[FaceDiag] live face embedding is empty")
            return "unknown", None

        best_name = None
        best_distance = 999.0
        best_similarity = -999.0
        second_best_similarity = -999.0
        best_sample_similarity = -999.0
        second_best_sample_similarity = -999.0
        centroid_items = list(self.centroids.items()) if self.centroids else []

        if self.arcface is not None and self.arcface.enabled:
            ranked_names = []
            for name, centroid in centroid_items:
                if centroid is None or len(centroid) != len(embedding):
                    continue
                similarity = float(np.dot(embedding, centroid))
                ranked_names.append((name, similarity))

            sample_best_by_name = {}
            for entry in self.entries:
                name = entry.get("name")
                sample_embedding = entry.get("embedding")
                if not name or sample_embedding is None or len(sample_embedding) != len(embedding):
                    continue
                similarity = float(np.dot(embedding, sample_embedding))
                if similarity > sample_best_by_name.get(name, -999.0):
                    sample_best_by_name[name] = similarity

            ranked_samples = sorted(
                sample_best_by_name.items(),
                key=lambda item: item[1],
                reverse=True,
            )
            if ranked_samples:
                sample_best_name, best_sample_similarity = ranked_samples[0]
                if best_name is None:
                    best_name = sample_best_name
                if len(ranked_samples) > 1:
                    second_best_sample_similarity = ranked_samples[1][1]

            ranked_names = sorted(
                ranked_names,
                key=lambda item: item[1],
                reverse=True,
            )
            if ranked_names:
                best_name, best_similarity = ranked_names[0]
                best_distance = 1.0 - best_similarity
                if len(ranked_names) > 1:
                    second_best_similarity = ranked_names[1][1]
            elif centroid_items:
                centroid_dims = [len(c) for _, c in centroid_items if c is not None]
                self._log_diag(
                    "arcface_dim_mismatch",
                    f"[FaceDiag] ArcFace embedding dim mismatch, live_dim={len(embedding)} centroid_dims={centroid_dims}",
                )
        else:
            ranked_names = []
            for name, centroid in centroid_items:
                if centroid is None or len(centroid) != len(embedding):
                    continue
                distance = float(np.linalg.norm(embedding - centroid))
                ranked_names.append((name, distance))
            ranked_names = sorted(ranked_names, key=lambda item: item[1])
            if ranked_names:
                best_name, best_distance = ranked_names[0]
                if len(ranked_names) > 1:
                    second_best_distance = ranked_names[1][1]
                else:
                    second_best_distance = 999.0

        if self.arcface is not None and self.arcface.enabled:
            similarity_margin = (
                best_similarity - second_best_similarity
                if second_best_similarity > -998.0
                else 1.0
            )
            sample_margin = (
                best_sample_similarity - second_best_sample_similarity
                if second_best_sample_similarity > -998.0
                else 1.0
            )
            min_similarity = (
                FACE_SINGLE_IDENTITY_SIMILARITY_ARCFACE
                if len(centroid_items) <= 1
                else FACE_MATCH_SIMILARITY_ARCFACE
            )
            if (
                best_name is not None
                and best_sample_similarity >= min_similarity
                and sample_margin >= FACE_MATCH_SIMILARITY_MARGIN_ARCFACE
            ):
                return f"known:{best_name}", best_sample_similarity
            self._log_diag(
                "arcface_low_similarity",
                f"[FaceDiag] recognizer low similarity best={best_name} "
                f"centroid={best_similarity:.3f} sample={best_sample_similarity:.3f} "
                f"margin={sample_margin:.3f} threshold={min_similarity:.3f}",
            )
            return "unknown", best_sample_similarity

        distance_margin = (
            second_best_distance - best_distance
            if 'second_best_distance' in locals()
            else 999.0
        )
        if (
            best_name is not None
            and best_distance <= FACE_MATCH_THRESHOLD
            and distance_margin >= FACE_MATCH_SIMILARITY_MARGIN_FALLBACK
        ):
            return f"known:{best_name}", best_distance
        return "unknown", best_distance

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

# def nms(boxes, scores, iou_threshold=0.5):
#     if boxes.size == 0: return []
#     x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
#     areas = (x2 - x1) * (y2 - y1)
#     order = scores.argsort()[::-1]
#     keep = []
#     while order.size > 0:
#         i = order[0]
#         keep.append(i)
#         if order.size == 1: break
#         xx1 = np.maximum(x1[i], x1[order[1:]])
#         yy1 = np.maximum(y1[i], y1[order[1:]])
#         xx2 = np.minimum(x2[i], x2[order[1:]])
#         yy2 = np.minimum(y2[i], y2[order[1:]])
#         w = np.maximum(0.0, xx2 - xx1)
#         h = np.maximum(0.0, yy2 - yy1)
#         inter = w * h
#         iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-6)
#         inds = np.where(iou <= iou_threshold)[0]
#         order = order[inds + 1]
#     return keep

# def parse_predictions(predictions, conf_threshold=0.5):
#     detections = []
#     for i, pred in enumerate(predictions):
#         if len(pred) < 56: continue
#         cx, cy, w, h, obj_conf = float(pred[0]), float(pred[1]), float(pred[2]), float(pred[3]), float(pred[4])
#         if obj_conf < conf_threshold: continue
#         x1, y1, x2, y2 = cx - w / 2.0, cy - h / 2.0, cx + w / 2.0, cy + h / 2.0
#         kpts = np.array(pred[5:5+51], dtype=np.float32).reshape(17, 3)
#         detections.append({'box': [x1, y1, x2, y2], 'score': obj_conf, 'keypoints': kpts, 'class_id': 0})
#     if not detections: return []
#     boxes = np.array([d['box'] for d in detections])
#     scores = np.array([d['score'] for d in detections])
#     keep = nms(boxes, scores, iou_threshold=0.7)
#     return [detections[i] for i in keep]


#     # 💥 核心优化：调用 OpenCV C++ 底层实现的 NMS
#     indices = cv2.dnn.NMSBoxes(boxes_for_nms, scores_for_nms, conf_threshold, 0.7)

#     if len(indices) > 0:
#         return [detections[i] for i in indices.flatten()]
#     return []


# def pre_process_stream(cv_image, dvpp=None):
#     try:
#         orig_h, orig_w = cv_image.shape[:2]
#         rgb_image = cv2.cvtColor(cv_image, cv2.COLOR_BGR2RGB)
#         scale = min(MODEL_WIDTH / orig_w, MODEL_HEIGHT / orig_h)
#         new_w, new_h = int(orig_w * scale), int(orig_h * scale)
#         pad_x, pad_y = (MODEL_WIDTH - new_w) // 2, (MODEL_HEIGHT - new_h) // 2
#         resized_img = cv2.resize(rgb_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
#         padded_img = np.full((MODEL_HEIGHT, MODEL_WIDTH, 3), 114, dtype=np.uint8)
#         padded_img[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized_img
#         rgb_np = np.array(padded_img, dtype=np.float32) / 255.0
#         nchw_img = np.transpose(rgb_np, (2, 0, 1))[np.newaxis, :, :, :]
#         return np.ascontiguousarray(nchw_img), {'scale': scale, 'pad_x': pad_x, 'pad_y': pad_y, 'orig_w': orig_w, 'orig_h': orig_h}
#     except Exception as e:
#         print(f"❌ Stream Pre-process error: {e}")
#         return None, None

#     except Exception as e:
#         print(f"❌ Stream Pre-process error: {e}")
#         return None, None
# 🔥 警告：请把以前写的纯 Python 版 `def nms(...)` 函数整段删掉！
# 我们再也不用那种让 CPU 跑到冒烟的慢代码了。

def parse_predictions(predictions, conf_threshold=0.5):
    """
    极致加速版：利用 NumPy 矩阵运算和 OpenCV C++ 底层，将 2秒 的耗时压缩到 0.005秒！
    """
    if len(predictions) == 0: return []

    # 💥 1. 矩阵化过滤：一瞬间把 8400 个框里置信度低于 0.5 的 8300 多个垃圾框直接砍掉
    scores = predictions[:, 4]
    valid_mask = scores >= conf_threshold

    valid_preds = predictions[valid_mask]
    valid_scores = scores[valid_mask]

    if len(valid_preds) == 0:
        return []

    # 💥 2. 矩阵化计算坐标：一瞬间把剩下有效框的 x, y, w, h 算出来，零 Python 循环！
    cx = valid_preds[:, 0]
    cy = valid_preds[:, 1]
    w  = valid_preds[:, 2]
    h  = valid_preds[:, 3]

    x_top_left = cx - w / 2.0
    y_top_left = cy - h / 2.0

    # 转成 OpenCV C++ 需要的格式
    boxes_for_nms = np.column_stack((x_top_left, y_top_left, w, h)).tolist()
    scores_for_nms = valid_scores.tolist()

    # 💥 3. C++ 级非极大值抑制 (NMS)：不到 1 毫秒就能找出最优的框
    indices = cv2.dnn.NMSBoxes(boxes_for_nms, scores_for_nms, conf_threshold, 0.45)

    if len(indices) == 0:
        return []

    # 兼容不同版本 OpenCV 的返回值格式
    indices = np.array(indices).flatten()

    # 💥 4. 此时 indices 里只剩下画面里真正的人（通常只有 1~5 个）
    # 现在用 Python 循环这几个数，CPU 连汗都不会出一滴
    detections = []
    for idx in indices:
        pred = valid_preds[idx]
        x1, y1, w_box, h_box = boxes_for_nms[idx]
        x2, y2 = x1 + w_box, y1 + h_box

        # 提取 17 个关键点
        kpts = np.array(pred[5:56], dtype=np.float32).reshape(17, 3)

        detections.append({
            'box': [x1, y1, x2, y2],
            'score': scores_for_nms[idx],
            'keypoints': kpts,
            'class_id': 0
        })

    return detections


def parse_face_predictions(predictions, conf_threshold=0.35):
    if len(predictions) == 0:
        return []

    scores = predictions[:, 4]
    valid_mask = scores >= conf_threshold
    valid_preds = predictions[valid_mask]
    valid_scores = scores[valid_mask]
    if len(valid_preds) == 0:
        return []

    cx = valid_preds[:, 0]
    cy = valid_preds[:, 1]
    w = valid_preds[:, 2]
    h = valid_preds[:, 3]

    x_top_left = cx - w / 2.0
    y_top_left = cy - h / 2.0
    boxes_for_nms = np.column_stack((x_top_left, y_top_left, w, h)).tolist()
    scores_for_nms = valid_scores.tolist()
    indices = cv2.dnn.NMSBoxes(boxes_for_nms, scores_for_nms, conf_threshold, 0.45)
    if len(indices) == 0:
        return []

    indices = np.array(indices).flatten()
    detections = []
    for idx in indices:
        x1, y1, w_box, h_box = boxes_for_nms[idx]
        x2, y2 = x1 + w_box, y1 + h_box
        detections.append({
            "box": [x1, y1, x2, y2],
            "score": scores_for_nms[idx],
            "class_id": 0,
        })
    return detections

def pre_process_stream(cv_image, dvpp=None, input_dtype=np.float32, input_layout="NCHW"):
    """
    极致加速版：纯 C++ 预处理，释放 CPU
    """
    try:
        orig_h, orig_w = cv_image.shape[:2]
        scale = min(MODEL_WIDTH / orig_w, MODEL_HEIGHT / orig_h)
        new_w, new_h = int(orig_w * scale), int(orig_h * scale)

        # 1. OpenCV 缩放 (C++)
        resized_img = cv2.resize(cv_image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        pad_x = (MODEL_WIDTH - new_w) // 2
        pad_y = (MODEL_HEIGHT - new_h) // 2

        # 2. OpenCV 边缘填充 (C++)
        padded_img = cv2.copyMakeBorder(
            resized_img,
            pad_y, MODEL_HEIGHT - new_h - pad_y,
            pad_x, MODEL_WIDTH - new_w - pad_x,
            cv2.BORDER_CONSTANT, value=(114, 114, 114)
        )

        rgb_img = cv2.cvtColor(padded_img, cv2.COLOR_BGR2RGB)
        normalized = rgb_img.astype(np.float32) / 255.0

        if input_layout == "NHWC":
            model_input = normalized[np.newaxis, :, :, :].astype(input_dtype)
        else:
            model_input = np.transpose(normalized, (2, 0, 1))[np.newaxis, :, :, :].astype(input_dtype)

        # 保证内存连续交给昇腾 NPU
        return np.ascontiguousarray(model_input), {'scale': scale, 'pad_x': pad_x, 'pad_y': pad_y, 'orig_w': orig_w, 'orig_h': orig_h}
    except Exception as e:
        print(f"❌ Stream Pre-process error: {e}")
        return None, None

def is_person_fallen(box, kpts, aspect_ratio_threshold, frame_shape=None):
    box_w = max(1.0, box[2] - box[0])
    box_h = max(1.0, box[3] - box[1])
    aspect_ratio = box_h / box_w
    horizontal_box = aspect_ratio < aspect_ratio_threshold

    conf_thresh = 0.4

    def visible_point(idx):
        if idx >= len(kpts):
            return None
        x, y, conf = kpts[idx]
        if float(conf) <= conf_thresh:
            return None
        return float(x), float(y)

    def center(indices):
        pts = [visible_point(idx) for idx in indices]
        pts = [pt for pt in pts if pt is not None]
        if not pts:
            return None
        xs = [pt[0] for pt in pts]
        ys = [pt[1] for pt in pts]
        return float(sum(xs) / len(xs)), float(sum(ys) / len(ys))

    shoulders_center = center([5, 6])
    hips_center = center([11, 12])
    knees_center = center([13, 14])
    ankles_center = center([15, 16])

    lower_body_visible = knees_center is not None or ankles_center is not None
    truncated_bottom = False
    truncated_left_right = False
    if frame_shape is not None:
        frame_h, frame_w = frame_shape[:2]
        truncated_bottom = box[3] >= frame_h - FRAME_EDGE_MARGIN
        truncated_left_right = box[0] <= FRAME_EDGE_MARGIN or box[2] >= frame_w - FRAME_EDGE_MARGIN

    torso_horizontal = False
    if shoulders_center is not None and hips_center is not None:
        dx = abs(shoulders_center[0] - hips_center[0])
        dy = abs(shoulders_center[1] - hips_center[1])
        torso_horizontal = dx > dy * 1.1

    body_horizontal = False
    visible_body_pts = [pt for pt in [shoulders_center, hips_center, knees_center, ankles_center] if pt is not None]
    if len(visible_body_pts) >= 3:
        xs = [pt[0] for pt in visible_body_pts]
        ys = [pt[1] for pt in visible_body_pts]
        horizontal_span = max(xs) - min(xs)
        vertical_span = max(ys) - min(ys)
        body_horizontal = horizontal_span > vertical_span * 1.05

    inverted = False
    if shoulders_center is not None and ankles_center is not None:
        inverted = shoulders_center[1] >= ankles_center[1] - 4.0

    # Guard against the common false positive where only upper body is visible near the camera.
    if horizontal_box and not lower_body_visible and (truncated_bottom or truncated_left_right):
        return False

    if inverted:
        return True
    if horizontal_box and torso_horizontal:
        return True
    if horizontal_box and lower_body_visible and body_horizontal:
        return True
    return False


def analyze_fall_motion(state, frame_shape):
    history = list(state.get("box_history", []))
    if len(history) < 2 or frame_shape is None:
        return False

    frame_h = float(frame_shape[0])
    latest_ts, latest_center_y, latest_h, latest_aspect = history[-1]
    for past_ts, past_center_y, past_h, past_aspect in history[:-1]:
        dt = latest_ts - past_ts
        if dt <= 0.08 or dt > 1.0:
            continue

        down_delta = latest_center_y - past_center_y
        aspect_flip = past_aspect > 1.15 and latest_aspect < 0.95
        height_drop = latest_h < past_h * 0.82
        rapid_descent = down_delta > max(frame_h * 0.10, past_h * 0.28)
        if rapid_descent and (aspect_flip or height_drop):
            return True
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


def compute_face_crop_rect(frame_shape, box, kpts):
    frame_h, frame_w = frame_shape[:2]
    head_points = []
    for idx in [0, 1, 2, 3, 4]:
        pt = get_pose_keypoint(kpts, idx, 0.35)
        if pt is not None:
            head_points.append(pt)

    if head_points:
        xs = [pt[0] for pt in head_points]
        ys = [pt[1] for pt in head_points]
        x1 = min(xs)
        y1 = min(ys)
        x2 = max(xs)
        y2 = max(ys)
        width = max(20.0, x2 - x1)
        height = max(20.0, y2 - y1)
        pad_x = width * 0.9
        pad_y_top = height * 1.1
        pad_y_bottom = height * 1.4
        crop_x1 = int(clamp(x1 - pad_x, 0, frame_w - 1))
        crop_y1 = int(clamp(y1 - pad_y_top, 0, frame_h - 1))
        crop_x2 = int(clamp(x2 + pad_x, 0, frame_w))
        crop_y2 = int(clamp(y2 + pad_y_bottom, 0, frame_h))
    else:
        box_x1, box_y1, box_x2, box_y2 = [int(v) for v in box]
        box_w = max(1, box_x2 - box_x1)
        box_h = max(1, box_y2 - box_y1)
        crop_x1 = int(clamp(box_x1 + box_w * 0.15, 0, frame_w - 1))
        crop_x2 = int(clamp(box_x2 - box_w * 0.15, 0, frame_w))
        crop_y1 = int(clamp(box_y1, 0, frame_h - 1))
        crop_y2 = int(clamp(box_y1 + box_h * 0.38, 0, frame_h))

    if crop_x2 - crop_x1 < 24 or crop_y2 - crop_y1 < 24:
        return None
    return crop_x1, crop_y1, crop_x2, crop_y2


def extract_face_crop(frame, box, kpts):
    rect = compute_face_crop_rect(frame.shape, box, kpts)
    if rect is None:
        return None
    crop_x1, crop_y1, crop_x2, crop_y2 = rect
    return frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()


def extract_aligned_face_crop(frame, box, kpts):
    rect = compute_face_crop_rect(frame.shape, box, kpts)
    if rect is None:
        return None

    crop_x1, crop_y1, crop_x2, crop_y2 = rect
    face_crop = frame[crop_y1:crop_y2, crop_x1:crop_x2].copy()
    if face_crop.size == 0:
        return None

    left_eye = get_pose_keypoint(kpts, 1)
    right_eye = get_pose_keypoint(kpts, 2)
    nose = get_pose_keypoint(kpts, 0)
    if left_eye is None or right_eye is None or nose is None:
        return face_crop

    if left_eye[0] > right_eye[0]:
        left_eye, right_eye = right_eye, left_eye

    src = np.float32([
        [left_eye[0] - crop_x1, left_eye[1] - crop_y1],
        [right_eye[0] - crop_x1, right_eye[1] - crop_y1],
        [nose[0] - crop_x1, nose[1] - crop_y1],
    ])
    dst = np.float32([
        [38.0, 40.0],
        [74.0, 40.0],
        [56.0, 68.0],
    ])

    try:
        matrix = cv2.getAffineTransform(src, dst)
        return cv2.warpAffine(
            face_crop,
            matrix,
            (112, 112),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REFLECT101,
        )
    except Exception:
        return face_crop


def score_face_crop(face_crop, kpts):
    if face_crop is None or face_crop.size == 0:
        return 0.0
    h, w = face_crop.shape[:2]
    area_score = min(1.0, (w * h) / 20000.0)
    visible = 0
    conf_sum = 0.0
    for idx in [0, 1, 2]:
        if idx < len(kpts):
            conf = float(kpts[idx][2])
            if conf > 0.3:
                visible += 1
                conf_sum += conf
    conf_score = conf_sum / max(1, visible)
    frontal_bonus = 0.2 if visible >= 3 else 0.0
    return area_score + conf_score + frontal_bonus


def is_front_face_candidate(kpts):
    left_eye = get_pose_keypoint(kpts, 1)
    right_eye = get_pose_keypoint(kpts, 2)
    nose = get_pose_keypoint(kpts, 0)
    if left_eye is None or right_eye is None or nose is None:
        return False

    if left_eye[0] > right_eye[0]:
        left_eye, right_eye = right_eye, left_eye

    eye_dx = right_eye[0] - left_eye[0]
    eye_dy = abs(right_eye[1] - left_eye[1])
    if eye_dx < 8.0:
        return False
    if eye_dy > eye_dx * 0.55:
        return False

    nose_min = left_eye[0] + eye_dx * 0.10
    nose_max = right_eye[0] - eye_dx * 0.10
    if not (nose_min <= nose[0] <= nose_max):
        return False

    eye_y = (left_eye[1] + right_eye[1]) * 0.5
    if nose[1] <= eye_y - eye_dx * 0.10:
        return False

    return True


def extract_person_roi(frame, box):
    if frame is None or frame.size == 0:
        return None, None
    frame_h, frame_w = frame.shape[:2]
    box_x1, box_y1, box_x2, box_y2 = [int(v) for v in box]
    box_w = max(1, box_x2 - box_x1)
    box_h = max(1, box_y2 - box_y1)
    roi_x1 = int(clamp(box_x1 + box_w * 0.05, 0, frame_w - 1))
    roi_x2 = int(clamp(box_x2 - box_w * 0.05, 0, frame_w))
    roi_y1 = int(clamp(box_y1, 0, frame_h - 1))
    roi_y2 = int(clamp(box_y1 + box_h * 0.55, 0, frame_h))
    if roi_x2 - roi_x1 < 24 or roi_y2 - roi_y1 < 24:
        return None, None
    return frame[roi_y1:roi_y2, roi_x1:roi_x2].copy(), (roi_x1, roi_y1, roi_x2, roi_y2)


def expand_face_box(box, frame_shape, pad_ratio=FACE_DET_BOX_PAD_RATIO):
    frame_h, frame_w = frame_shape[:2]
    x1, y1, x2, y2 = [int(v) for v in box]
    face_w = max(1, x2 - x1)
    face_h = max(1, y2 - y1)
    pad_x = int(face_w * pad_ratio)
    pad_y = int(face_h * pad_ratio)
    x1 = max(0, min(x1 - pad_x, frame_w - 1))
    y1 = max(0, min(y1 - pad_y, frame_h - 1))
    x2 = max(x1 + 1, min(x2 + pad_x, frame_w))
    y2 = max(y1 + 1, min(y2 + pad_y, frame_h))
    return [x1, y1, x2, y2]


def body_contains_face(body_box, face_box):
    bx1, by1, bx2, by2 = body_box
    fx1, fy1, fx2, fy2 = face_box
    cx = (fx1 + fx2) * 0.5
    cy = (fy1 + fy2) * 0.5
    body_h = max(1.0, by2 - by1)
    return bx1 <= cx <= bx2 and by1 <= cy <= by1 + body_h * 0.65

def draw_results(display_image, alerts):
    for alert in alerts:
        box = [int(p) for p in alert['box']]
        cv2.rectangle(display_image, (box[0], box[1]), (box[2], box[3]), alert['color'], 2)
        face_det_box = alert.get('face_det_box')
        face_det_box_ts = float(alert.get('face_det_box_ts', 0.0) or 0.0)
        now_ts = float(alert.get('now_ts', 0.0) or 0.0)
        if face_det_box and now_ts - face_det_box_ts <= FACE_DET_BOX_DISPLAY_TTL:
            fx1, fy1, fx2, fy2 = [int(v) for v in face_det_box]
            cv2.rectangle(display_image, (fx1, fy1), (fx2, fy2), (255, 128, 0), 2)
            cv2.putText(display_image, 'FaceDet', (fx1, max(18, fy1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 128, 0), 2)
        face_label = alert.get('face_label', 'pending')
        if str(face_label).startswith('known:'):
            face_color = (0, 255, 0)
        elif face_label in ('stranger', 'unknown'):
            face_color = (0, 0, 255)
        else:
            face_color = (0, 255, 255)
        label_lines = [
            f"ID:{alert.get('id', -1)} {alert['status']}",
            f"Face:{face_label}",
        ]
        for idx, text in enumerate(label_lines):
            y = max(20, box[1] - 10 - idx * 22)
            color = alert['color'] if idx == 0 else face_color
            cv2.putText(display_image, text, (box[0], y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)
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
        if MQTT_USERNAME:
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        if MQTT_CA_CERT:
            self.client.tls_set(ca_certs=MQTT_CA_CERT)
        try:
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
            print("✅ MQTT Connected")
        except:
            print("❌ MQTT Connection Failed")
        self.last_alert_time = 0
        self.last_stranger_alert_time = 0
        self.last_sit_alert_time = 0
        self.last_face_alert_time = 0

    def publish_fall_alert(self):
        if time.time() - self.last_alert_time < 5: return
        alert = {"event": "fall_detected", "timestamp": str(datetime.now())}
        self.client.publish(ALERT_TOPIC, json.dumps(alert))
        print(f"🚀 Alert Sent: {alert}")
        self.last_alert_time = time.time()

    def publish_stranger_alert(self, person_id=None, score=None):
        if time.time() - self.last_stranger_alert_time < 5:
            return
        alert = {
            "event": "stranger_detected",
            "timestamp": str(datetime.now()),
            "person_id": person_id,
            "score": None if score is None else float(score),
        }
        self.client.publish(STRANGER_ALERT_TOPIC, json.dumps(alert))
        print(f"馃殌 Alert Sent: {alert}")
        self.last_stranger_alert_time = time.time()

    def publish_sit_alert(self, duration_seconds=None, person_id=None):
        if time.time() - self.last_sit_alert_time < 30:
            return
        alert = {
            "event": "sit_detected",
            "timestamp": str(datetime.now()),
            "duration_seconds": round(float(duration_seconds), 1) if duration_seconds else 0,
            "person_id": person_id,
        }
        self.client.publish(SIT_ALERT_TOPIC, json.dumps(alert))
        print(f"[MQTT] Sit Alert Sent: {alert}")
        self.last_sit_alert_time = time.time()

    def publish_face_alert(self, name=None, score=None, person_id=None):
        if time.time() - self.last_face_alert_time < 10:
            return
        alert = {
            "event": "face_recognized",
            "timestamp": str(datetime.now()),
            "name": name,
            "score": round(float(score), 3) if score else None,
            "person_id": person_id,
        }
        self.client.publish(FACE_ALERT_TOPIC, json.dumps(alert))
        print(f"[MQTT] Face Alert Sent: {alert}")
        self.last_face_alert_time = time.time()

class AclLiteStreamDetector:
    def __init__(self, model_path=MODEL_PATH, camera_index=0):
        self.model_path = model_path
        env_cam = os.getenv("AI_GUARDIAN_CAMERA_INDEX", "").strip()
        if env_cam != "":
            try:
                camera_index = int(env_cam)
            except Exception:
                pass
        self.camera_index = camera_index
        self.running = False
        self.cap = None
        self.camera_connected = False
        self.camera_connected_since = 0.0
        self.last_camera_frame_at = 0.0
        self.camera_stop = threading.Event()
        self.camera_thread = None
        self.person_states = {}

        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.frame_ready = threading.Event()

        self.latest_result = None
        self.result_lock = threading.Lock()
        self.result_ready = threading.Event()

        self.capture_fps_limit = 18.0
        self.infer_fps_limit = 10.0
        self._capture_interval = 1.0 / self.capture_fps_limit
        self._infer_interval = 1.0 / self.infer_fps_limit
        self._last_capture_ts = 0.0
        self._last_infer_ts = 0.0

        self._perf_window = deque(maxlen=60)
        self._last_perf_log = 0.0
        self._infer_fail_count = 0
        self._last_infer_error_log = 0.0
        self.input_dtype = np.float32
        self.input_layout = "NCHW"
        self.inference_enabled = True
        self.face_detector = YoloFaceDetectorACL(FACE_DET_MODEL_PATH)
        self.face_recognizer = ArcFaceRecognizerACL(FACE_REC_MODEL_PATH)
        self.face_library = FaceLibrary(recognizer=self.face_recognizer)
        self.face_library_loaded = False
        self.face_library_loading = False
        self.next_person_id = 1
        self.person_state_lock = threading.Lock()
        self.recent_known_tracks = deque(maxlen=12)
        self.face_det_cache = []
        self.face_det_last_run = 0.0
        self.face_global_last_check = 0.0
        self._face_det_ms = 0.0
        self._face_rec_ms = 0.0
        self.vlm_last_periodic_scene_ts = 0.0
        self.vlm_client = VLMClient() if VLM_EVENTS_ENABLED and VLMClient is not None else None
        self.vlm_enabled = self.vlm_client is not None
        self._vlm_warned = False

    def _camera_candidates(self):
        env_list = os.getenv("AI_GUARDIAN_CAMERA_CANDIDATES", "").strip()
        candidates = []
        if env_list:
            for item in env_list.split(','):
                item = item.strip()
                if not item:
                    continue
                try:
                    candidates.append(int(item))
                except Exception:
                    continue

        # USB口变动时，/dev/video索引可能变化；自动扫描已有节点补充候选。
        for dev in sorted(glob.glob('/dev/video*')):
            base = os.path.basename(dev)
            if not base.startswith('video'):
                continue
            suffix = base[5:]
            if suffix.isdigit():
                candidates.append(int(suffix))

        if not candidates:
            candidates = [self.camera_index, 0, 1, 2, 3]

        seen = set()
        uniq = []
        for idx in candidates:
            if idx in seen:
                continue
            seen.add(idx)
            uniq.append(idx)
        return uniq

    def _open_camera_with_fallback(self):
        for idx in self._camera_candidates():
            cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            if not cap.isOpened():
                cap.release()
                continue

            ok, _ = cap.read()
            if not ok:
                cap.release()
                continue

            self.cap = cap
            self.camera_index = idx
            print(f"[Camera] opened index: {idx}")
            return True

        return False

    def _safe_call(self, fn, *args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception:
            return None

    def _log_model_info(self):
        print(f"[Init] Model path: {self.model_path}")
        print(f"[Init] Input trial mode: {self.input_layout} {self.input_dtype.__name__}")

        try:
            model_id = getattr(self.model, "_model_id", None)
            model_desc = getattr(self.model, "_model_desc", None)

            if model_desc is not None:
                num_inputs = self._safe_call(acl.mdl.get_num_inputs, model_desc)
                num_outputs = self._safe_call(acl.mdl.get_num_outputs, model_desc)
                if num_inputs is not None or num_outputs is not None:
                    print(f"[Init] Model IO count: inputs={num_inputs} outputs={num_outputs}")

                if isinstance(num_inputs, int):
                    for i in range(num_inputs):
                        dims = self._safe_call(acl.mdl.get_input_dims, model_desc, i)
                        size = self._safe_call(acl.mdl.get_input_size_by_index, model_desc, i)
                        print(f"[Init] Input[{i}] dims={dims} size={size}")

                if isinstance(num_outputs, int):
                    for i in range(num_outputs):
                        dims = self._safe_call(acl.mdl.get_output_dims, model_desc, i)
                        size = self._safe_call(acl.mdl.get_output_size_by_index, model_desc, i)
                        print(f"[Init] Output[{i}] dims={dims} size={size}")

            if model_id is not None:
                print(f"[Init] Model id: {model_id}")
        except Exception as e:
            print(f"[Init] Model info probe failed: {e}")

    def _load_face_library_async(self):
        try:
            self.face_library.load()
            self.face_library_loaded = True
        except Exception as e:
            print(f"[Face] library load failed: {e}")
        finally:
            self.face_library_loading = False

    def _ensure_face_library_loaded(self, has_people):
        if not has_people or self.face_library_loaded or self.face_library_loading:
            return
        self.face_library_loading = True
        print("[Face] detected person in frame, start loading face library...")
        threading.Thread(target=self._load_face_library_async, daemon=True).start()

    def init(self):
        try:
            self._acl_resource = AclLiteResource()
            self._acl_resource.init()

            self.face_recognizer.init()
            print("[Face] loading face library before camera inference...")
            self.face_library_loading = True
            try:
                self.face_library.load()
                self.face_library_loaded = True
            finally:
                self.face_library_loading = False

            self.model = AclLiteModel(self.model_path)
            self.dvpp = AclLiteImageProc(self._acl_resource)
            self.face_detector.init()
            self._log_model_info()

            self.running = True
            self.camera_stop.clear()
            self.camera_thread = threading.Thread(target=self._camera_reader_thread, daemon=True)
            self.camera_thread.start()

            return True
        except Exception as e:
            print(f'Init Error: {e}')
            return False

    def camera_is_live(self):
        return (self.running and self.camera_connected
                and time.monotonic() - self.last_camera_frame_at < 3.0)

    def _clear_camera_frames(self):
        self.camera_connected = False
        self.last_camera_frame_at = 0.0
        with self.frame_lock:
            self.latest_frame = None
            self.frame_ready.clear()
        with self.result_lock:
            self.latest_result = None
            self.result_ready.clear()

    def _camera_reader_thread(self):
        try:
            while self.running and not self.camera_stop.is_set():
                if self.cap is None:
                    try:
                        opened = self._open_camera_with_fallback()
                    except Exception as exc:
                        print(f'[Camera] open failed: {exc}')
                        opened = False
                    if not opened:
                        self.camera_stop.wait(3.0)
                        continue
                    self.camera_connected_since = time.monotonic()
                if not self.running or self.camera_stop.is_set():
                    break
                try:
                    ret, frame = self.cap.read()
                except Exception:
                    ret, frame = False, None
                if not ret or frame is None:
                    self._clear_camera_frames()
                    self.cap.release()
                    self.cap = None
                    print('[Camera] disconnected; retrying in 3 seconds')
                    self.camera_stop.wait(3.0)
                    continue

                if not self.running or self.camera_stop.is_set():
                    break
                self.last_camera_frame_at = time.monotonic()
                self.camera_connected = True
                now = time.time()
                if now - self._last_capture_ts < self._capture_interval:
                    continue
                self._last_capture_ts = now

                with self.frame_lock:
                    self.latest_frame = frame.copy()
                self.frame_ready.set()

                if not self.inference_enabled:
                    with self.result_lock:
                        self.latest_result = (frame.copy(), [])
                    self.result_ready.set()
        finally:
            self._clear_camera_frames()
            if self.cap is not None:
                self.cap.release()
                self.cap = None

    def _record_perf(self, t1, t2, t3, t4):
        self._perf_window.append({
            'pre': (t2 - t1) * 1000.0,
            'infer': (t3 - t2) * 1000.0,
            'post': (t4 - t3) * 1000.0,
            'total': (t4 - t1) * 1000.0,
            'face_det': self._face_det_ms,
            'face_rec': self._face_rec_ms,
        })

        now = time.time()
        if now - self._last_perf_log < 2.0 or not self._perf_window:
            return

        avg_pre = sum(item['pre'] for item in self._perf_window) / len(self._perf_window)
        avg_infer = sum(item['infer'] for item in self._perf_window) / len(self._perf_window)
        avg_post = sum(item['post'] for item in self._perf_window) / len(self._perf_window)
        avg_total = sum(item['total'] for item in self._perf_window) / len(self._perf_window)
        max_face_det = max(item['face_det'] for item in self._perf_window)
        max_face_rec = max(item['face_rec'] for item in self._perf_window)
        fps = 1000.0 / avg_total if avg_total > 0 else 0.0
        print(
            f'[Perf] avg pre:{avg_pre:.1f}ms | infer:{avg_infer:.1f}ms | '
            f'post:{avg_post:.1f}ms | face-det max:{max_face_det:.1f}ms | '
            f'face-rec max:{max_face_rec:.1f}ms | total:{avg_total:.1f}ms | fps:{fps:.1f}'
        )
        self._last_perf_log = now

    def _apply_face_result(self, person_id, label, score):
        with self.person_state_lock:
            state = self.person_states.get(person_id)
            if state is None:
                return

            vote_history = state.setdefault("face_vote_history", deque(maxlen=FACE_VOTE_WINDOW))
            numeric_score = float(score) if score is not None else None
            previous_label = state.get("face_label")
            invalid_result = (not str(label).startswith("known:")) and (numeric_score is None or numeric_score < 0)

            if invalid_result:
                state["face_pending"] = False
                final_label = state.get("face_label", "pending")
                final_score = state.get("face_score")
                if str(final_label).startswith("known:"):
                    print(f"[Face] person_id={person_id} recognized as {final_label.split(':', 1)[1]} score={final_score:.3f}")
                else:
                    print(f"[Face] person_id={person_id} labeled as {final_label} score={final_score}")
                return

            competing_owner = None
            if str(label).startswith("known:"):
                now_ts = time.time()
                for other_person_id, other_state in self.person_states.items():
                    if other_person_id == person_id:
                        continue
                    if now_ts - float(other_state.get("last_seen", 0.0) or 0.0) > FACE_KNOWN_OWNER_TTL:
                        continue
                    if str(other_state.get("face_label", "") or "") == label:
                        competing_owner = other_state
                        break
                if competing_owner is not None:
                    state["face_candidate"] = None
                    state["face_candidate_hits"] = 0
                    if str(previous_label).startswith("known:"):
                        state["face_label"] = previous_label
                    else:
                        state["face_label"] = "pending"
                    state["face_pending"] = False
                    final_label = state["face_label"]
                    final_score = state.get("face_score")
                    print(f"[Face] person_id={person_id} labeled as {final_label} score={final_score}")
                    return

            vote_history.append((label, numeric_score))

            if label.startswith("known:"):
                known_count = sum(1 for vote_label, _ in vote_history if vote_label == label)
                strong_known = numeric_score is not None and numeric_score >= FACE_MATCH_SIMILARITY_ARCFACE_STRONG
                if strong_known or known_count >= FACE_VOTE_MIN_KNOWN:
                    state["face_label"] = label
                    state["face_candidate"] = label
                    state["face_candidate_hits"] = max(known_count, 1)
                    state["best_face_crop"] = None
                    state["best_face_score"] = 0.0
                else:
                    state["face_candidate"] = label
                    state["face_candidate_hits"] = known_count
                    state["face_label"] = "pending"
            else:
                state["face_candidate"] = None
                state["face_candidate_hits"] = 0
                if str(previous_label).startswith("known:"):
                    state["face_label"] = previous_label
                else:
                    can_promote_stranger = (
                        (time.time() - float(state.get("first_seen", 0.0) or 0.0)) >= FACE_STRANGER_MIN_AGE
                    )
                    confident_unknown = False
                    if numeric_score is not None:
                        if self.face_recognizer is not None and self.face_recognizer.enabled:
                            known_count = len(getattr(self.face_library, "centroids", {}) or {})
                            stranger_similarity = (
                                FACE_STRANGER_SIMILARITY_ARCFACE_SINGLE_ID
                                if known_count <= 1
                                else FACE_STRANGER_SIMILARITY_ARCFACE
                            )
                            confident_unknown = numeric_score <= stranger_similarity
                        else:
                            confident_unknown = numeric_score >= FACE_STRANGER_DISTANCE_FALLBACK
                    unknown_count = sum(
                        1
                        for vote_label, vote_score in vote_history
                        if vote_label == "unknown"
                        and vote_score is not None
                        and (
                            (
                                self.face_recognizer is not None
                                and self.face_recognizer.enabled
                                and vote_score <= (
                                    FACE_STRANGER_SIMILARITY_ARCFACE_SINGLE_ID
                                    if len(getattr(self.face_library, "centroids", {}) or {}) <= 1
                                    else FACE_STRANGER_SIMILARITY_ARCFACE
                                )
                            )
                            or (
                                (self.face_recognizer is None or not self.face_recognizer.enabled)
                                and vote_score >= FACE_STRANGER_DISTANCE_FALLBACK
                            )
                        )
                    )
                    state["face_label"] = (
                        "stranger"
                        if can_promote_stranger
                        and confident_unknown
                        and unknown_count >= FACE_VOTE_MIN_UNKNOWN
                        else "pending"
                    )
                state["best_face_crop"] = None
                state["best_face_score"] = 0.0

            state["face_score"] = numeric_score
            state["face_pending"] = False

        final_label = state["face_label"]
        final_score = state["face_score"]

        if str(final_label).startswith("known:"):
            print(f"[Face] person_id={person_id} recognized as {final_label.split(':', 1)[1]} score={final_score:.3f}")
        else:
            print(f"[Face] person_id={person_id} labeled as {final_label} score={final_score}")

    def _prune_person_states(self, now_ts):
        with self.person_state_lock:
            expired_ids = [
                person_id
                for person_id, state in self.person_states.items()
                if now_ts - state.get("last_seen", 0.0) > FACE_TRACK_MAX_AGE
            ]
            for person_id in expired_ids:
                state = self.person_states.get(person_id)
                self._remember_known_track(person_id, state, now_ts)
                self.person_states.pop(person_id, None)

    def _remember_known_track(self, person_id, state, now_ts):
        if not state:
            return
        face_label = str(state.get("face_label", "") or "")
        if not face_label.startswith("known:"):
            return
        box = state.get("box")
        if not box:
            return
        self.recent_known_tracks.append({
            "person_id": person_id,
            "face_label": face_label,
            "face_score": state.get("face_score"),
            "box": [float(v) for v in box],
            "ts": now_ts,
        })

    def _recover_recent_known_track(self, box, now_ts):
        if not self.recent_known_tracks:
            return None

        det_center = box_center(box)
        best = None
        best_norm_dist = 999.0
        fresh_tracks = []

        for item in self.recent_known_tracks:
            age = now_ts - float(item.get("ts", 0.0) or 0.0)
            if age > FACE_TRACK_KNOWN_REID_TTL:
                continue
            fresh_tracks.append(item)
            prev_box = item.get("box")
            if not prev_box:
                continue
            prev_center = box_center(prev_box)
            center_dist = ((det_center[0] - prev_center[0]) ** 2 + (det_center[1] - prev_center[1]) ** 2) ** 0.5
            norm_dist = center_dist / max(1.0, box_diag(prev_box))
            if norm_dist <= FACE_TRACK_KNOWN_REID_MAX_NORM_DIST and norm_dist < best_norm_dist:
                best = item
                best_norm_dist = norm_dist

        self.recent_known_tracks = deque(fresh_tracks, maxlen=12)
        return best

    def _get_demo_known_label(self):
        if not self.face_library_loaded:
            return None
        centroids = getattr(self.face_library, "centroids", None) or {}
        if len(centroids) != 1:
            return None
        only_name = next(iter(centroids.keys()), None)
        return f"known:{only_name}" if only_name else None

    def _has_active_known_owner(self, label, owner_person_id=None):
        now_ts = time.time()
        for other_person_id, other_state in self.person_states.items():
            if owner_person_id is not None and other_person_id == owner_person_id:
                continue
            if now_ts - float(other_state.get("last_seen", 0.0) or 0.0) > FACE_KNOWN_OWNER_TTL:
                continue
            if str(other_state.get("face_label", "") or "") == label:
                return True
        return False

    def _recover_active_known_track(self, box, now_ts, used_ids):
        best = None
        best_score = -999.0

        for person_id, state in self.person_states.items():
            if person_id in used_ids:
                continue
            if now_ts - float(state.get("last_seen", 0.0) or 0.0) > FACE_KNOWN_OWNER_TTL:
                continue
            face_label = str(state.get("face_label", "") or "")
            if not face_label.startswith("known:"):
                continue
            prev_box = state.get("box")
            if not prev_box:
                continue

            iou = compute_iou(box, prev_box)
            prev_center = box_center(prev_box)
            det_center = box_center(box)
            center_dist = ((det_center[0] - prev_center[0]) ** 2 + (det_center[1] - prev_center[1]) ** 2) ** 0.5
            norm_dist = center_dist / max(1.0, box_diag(prev_box))
            score = iou - norm_dist * 0.2

            if (
                iou >= FACE_ACTIVE_KNOWN_TRANSFER_IOU
                or norm_dist <= FACE_ACTIVE_KNOWN_TRANSFER_NORM_DIST
            ) and score > best_score:
                best = {
                    "person_id": person_id,
                    "face_label": face_label,
                    "face_score": state.get("face_score"),
                }
                best_score = score

        return best

    def _refresh_face_det_cache(self, frame, now_ts, has_people=True):
        if self.face_detector is None or not self.face_detector.enabled:
            self.face_det_cache = []
            return
        if not has_people:
            self.face_det_cache = []
            return
        if now_ts - self.face_det_last_run < FACE_DET_INTERVAL:
            return

        face_det_started = time.perf_counter()
        detections = self.face_detector.detect(frame, conf_threshold=0.35)
        self._face_det_ms += (time.perf_counter() - face_det_started) * 1000.0
        cache = []
        for det in detections:
            expanded_box = expand_face_box(det["box"], frame.shape)
            cache.append({
                "box": expanded_box,
                "score": float(det.get("score", 0.0)),
                "ts": now_ts,
            })
        self.face_det_cache = cache
        self.face_det_last_run = now_ts

    def _get_face_detection_for_person(self, body_box):
        best = None
        best_score = -1.0
        for det in self.face_det_cache:
            if body_contains_face(body_box, det["box"]):
                score = float(det.get("score", 0.0))
                if score > best_score:
                    best = det
                    best_score = score
        return best

    def _assign_person_ids(self, detections, now_ts):
        self._prune_person_states(now_ts)
        assignments = []
        used_ids = set()

        for det in detections:
            best_id = None
            best_score = -999.0
            best_match_iou = 0.0
            best_match_norm_dist = 999.0
            det_center = box_center(det["box"])
            with self.person_state_lock:
                for person_id, state in self.person_states.items():
                    if person_id in used_ids:
                        continue
                    iou = compute_iou(det["box"], state["box"])
                    state_center = box_center(state["box"])
                    center_dist = ((det_center[0] - state_center[0]) ** 2 + (det_center[1] - state_center[1]) ** 2) ** 0.5
                    norm_dist = center_dist / box_diag(state["box"])
                    score = iou - norm_dist * 0.25
                    if str(state.get("face_label", "")).startswith("known:"):
                        score += FACE_TRACK_KNOWN_SCORE_BONUS
                    if (iou > FACE_TRACK_MATCH_MIN_IOU or norm_dist < FACE_TRACK_MATCH_MAX_NORM_DIST) and score > best_score:
                        best_score = score
                        best_id = person_id
                        best_match_iou = iou
                        best_match_norm_dist = norm_dist

                if best_id is None:
                    recovered_known = self._recover_active_known_track(det["box"], now_ts, used_ids)
                    if recovered_known is not None and recovered_known.get("person_id") in self.person_states:
                        best_id = recovered_known["person_id"]
                    else:
                        if recovered_known is None:
                            recovered_known = self._recover_recent_known_track(det["box"], now_ts)
                        best_id = self.next_person_id
                        self.next_person_id += 1
                        self.person_states[best_id] = {
                            "box": det["box"],
                            "first_seen": now_ts,
                            "last_seen": now_ts,
                            "box_history": deque(maxlen=12),
                            "fall_candidate_since": 0.0,
                            "fall_recover_since": 0.0,
                            "fall_confirmed": False,
                            "face_label": recovered_known["face_label"] if recovered_known else "pending",
                            "face_score": recovered_known.get("face_score") if recovered_known else None,
                            "face_det_box": None,
                            "face_det_box_ts": 0.0,
                            "last_face_check": now_ts if recovered_known else 0.0,
                            "face_pending": False,
                            "face_candidate": recovered_known["face_label"] if recovered_known else None,
                            "face_candidate_hits": FACE_VOTE_MIN_KNOWN if recovered_known else 0,
                            "face_vote_history": deque(maxlen=FACE_VOTE_WINDOW),
                            "best_face_crop": None,
                            "best_face_score": 0.0,
                            "vlm_sent_events": set(),
                            "vlm_inflight_events": set(),
                            "vlm_last_summary": None,
                            "vlm_last_event": None,
                            "vlm_last_risk_level": None,
                            "vlm_last_ts": 0.0,
                            "vlm_retry_after": {},
                        }
                    best_match_iou = 1.0
                    best_match_norm_dist = 0.0

                state = self.person_states[best_id]
                weak_reuse = (
                    best_match_iou < FACE_TRACK_REUSE_IOU_STRICT
                    or best_match_norm_dist > FACE_TRACK_REUSE_DIST_STRICT
                )
                if weak_reuse:
                    if not str(state.get("face_label", "")).startswith("known:"):
                        state["face_label"] = "pending"
                        state["face_score"] = None
                        state["face_det_box"] = None
                        state["face_det_box_ts"] = 0.0
                        state["last_face_check"] = 0.0
                        state["face_pending"] = False
                        state["face_candidate"] = None
                        state["face_candidate_hits"] = 0
                        state["face_vote_history"] = deque(maxlen=FACE_VOTE_WINDOW)
                        state["best_face_crop"] = None
                        state["best_face_score"] = 0.0
                state["box"] = det["box"]
                state["last_seen"] = now_ts
                state.setdefault("first_seen", now_ts)
                box_w = max(1.0, det["box"][2] - det["box"][0])
                box_h = max(1.0, det["box"][3] - det["box"][1])
                box_cy = (det["box"][1] + det["box"][3]) * 0.5
                state.setdefault("box_history", deque(maxlen=12)).append(
                    (now_ts, box_cy, box_h, box_h / box_w)
                )
                state_snapshot = dict(state)

            used_ids.add(best_id)
            assignments.append((best_id, state_snapshot, det))

        return assignments

    def _is_long_sit_state(self, state, now_ts):
        history = list(state.get("box_history", []))
        if len(history) < 2 or state.get("fall_confirmed"):
            return False

        oldest_ts = history[0][0]
        if now_ts - oldest_ts < VLM_LONG_SIT_THRESHOLD_SECONDS:
            return False

        centers_y = [item[1] for item in history]
        heights = [max(1.0, item[2]) for item in history]
        move_threshold = max(STATIONARY_PIXEL_THRESHOLD, float(np.median(heights)) * 0.12)
        if max(centers_y) - min(centers_y) > move_threshold:
            return False

        latest_aspect = history[-1][3]
        return latest_aspect > 0.45

    def _trigger_vlm_event_async(self, frame, person_id, event_type, state, det, now_ts, repeatable=False):
        if not self.vlm_enabled:
            if not self._vlm_warned and VLM_EVENTS_ENABLED and VLMClient is None:
                print("[VLM] disabled: vlm_client import failed")
                self._vlm_warned = True
            return

        with self.person_state_lock:
            tracked_state = self.person_states.get(person_id)
            if tracked_state is None:
                return
            inflight = tracked_state.setdefault("vlm_inflight_events", set())
            sent = tracked_state.setdefault("vlm_sent_events", set())
            retry_after = tracked_state.setdefault("vlm_retry_after", {})
            if event_type in inflight or (not repeatable and event_type in sent):
                return
            if now_ts < float(retry_after.get(event_type, 0.0) or 0.0):
                return
            inflight.add(event_type)
        frame_copy = frame.copy()
        box = [float(v) for v in det.get("box", [])]
        context = {
            "person_id": int(person_id),
            "event_type": event_type,
            "box": box,
            "face_label": state.get("face_label", "pending"),
            "face_score": state.get("face_score"),
            "fall_confirmed": bool(state.get("fall_confirmed")),
            "track_age_seconds": round(now_ts - state.get("first_seen", now_ts), 2),
        }

        def _worker():
            try:
                result = self.vlm_client.analyze_frame(
                    frame_copy,
                    event_type=event_type,
                    extra_context=context,
                )
            except Exception as exc:
                result = {
                    "ok": False,
                    "summary": f"VLM request failed: {exc}",
                    "risk_level": "unknown",
                    "need_check": True,
                    "source": "client",
                }

            summary = str(result.get("summary", "") or "").strip()
            if len(summary) > VLM_MAX_SUMMARY_LENGTH:
                summary = summary[: VLM_MAX_SUMMARY_LENGTH - 3] + "..."

            with self.person_state_lock:
                tracked_state = self.person_states.get(person_id)
                if tracked_state is not None:
                    tracked_state.setdefault("vlm_inflight_events", set()).discard(event_type)
                    tracked_state["vlm_last_summary"] = summary
                    tracked_state["vlm_last_event"] = event_type
                    tracked_state["vlm_last_risk_level"] = result.get("risk_level")
                    tracked_state["vlm_last_ts"] = time.time()
                    retry_after = tracked_state.setdefault("vlm_retry_after", {})
                    if result.get("ok"):
                        if not repeatable:
                            tracked_state.setdefault("vlm_sent_events", set()).add(event_type)
                        retry_after.pop(event_type, None)
                    else:
                        retry_after[event_type] = time.time() + VLM_RETRY_INTERVAL_SECONDS

            print(f"[VLM] person_id={person_id} event={event_type} summary={summary}")

        threading.Thread(target=_worker, daemon=True).start()

    def _maybe_trigger_vlm_events(self, frame, person_id, state, det, now_ts):
        sent_events = state.get("vlm_sent_events", set())

        if VLM_PERIODIC_ENABLED and now_ts - self.vlm_last_periodic_scene_ts >= VLM_PERIODIC_INTERVAL_SECONDS:
            self.vlm_last_periodic_scene_ts = now_ts
            self._trigger_vlm_event_async(frame, person_id, "periodic_scene", state, det, now_ts, repeatable=True)

        if "new_person" not in sent_events and now_ts - state.get("first_seen", now_ts) >= VLM_NEW_PERSON_DELAY_SECONDS:
            self._trigger_vlm_event_async(frame, person_id, "new_person", state, det, now_ts)

        if state.get("fall_confirmed") and "fall_detected" not in sent_events:
            self._trigger_vlm_event_async(frame, person_id, "fall_detected", state, det, now_ts)

        if self._is_long_sit_state(state, now_ts) and "long_sit" not in sent_events:
            self._trigger_vlm_event_async(frame, person_id, "long_sit", state, det, now_ts)

    def _maybe_recognize_face(self, frame, person_id, state, det, now_ts):
        if not self.face_library_loaded:
            return
        face_label = state.get("face_label")
        if face_label not in (None, "pending", "unknown", "stranger"):
            return
        if now_ts - state.get("first_seen", now_ts) < FACE_STABLE_TIME:
            return
        front_face_ok = is_front_face_candidate(det["kpts"])
        has_face_detector = self.face_detector is not None and self.face_detector.enabled
        if not front_face_ok and not has_face_detector:
            with self.person_state_lock:
                current_state = self.person_states.get(person_id)
                if current_state is not None:
                    current_state["face_label"] = "pending"
                    current_state["face_score"] = None
            return
        retry_interval = FACE_RETRY_UNKNOWN_INTERVAL if face_label in ("unknown", "stranger") else FACE_RECOGNITION_COOLDOWN
        if now_ts - state.get("last_face_check", 0.0) < retry_interval:
            return
        if now_ts - self.face_global_last_check < FACE_GLOBAL_RECOGNITION_COOLDOWN:
            return
        if state.get("face_pending"):
            return

        face_crop = None
        face_score = 0.0
        face_det_box = None
        quality_score = 0.0
        if self.face_detector is not None and self.face_detector.enabled:
            matched_face = self._get_face_detection_for_person(det["box"])
            if matched_face is not None:
                face_det_box = matched_face["box"]
                face_score = float(matched_face.get("score", 0.0))
                fx1, fy1, fx2, fy2 = [int(v) for v in face_det_box]
                candidate = frame[fy1:fy2, fx1:fx2].copy()
                if candidate.size != 0:
                    face_crop = candidate
            if face_crop is not None and face_score < FACE_RECOG_MIN_FACEDET_SCORE:
                face_crop = None
            quality_score = max(quality_score, face_score)

        if face_crop is None:
            face_crop = extract_face_crop(frame, det["box"], det["kpts"])
            face_score = score_face_crop(face_crop, det["kpts"])
            if face_crop is not None and face_score < FACE_RECOG_MIN_CROP_SCORE:
                face_crop = None
            quality_score = max(quality_score, face_score)

        quality_ok = (
            face_crop is not None
            and quality_score >= FACE_RECOG_MIN_QUALITY_SCORE
            and (front_face_ok or face_det_box is not None)
        )

        with self.person_state_lock:
            current_state = self.person_states.get(person_id)
            if current_state is not None:
                current_state["face_det_box"] = face_det_box
                current_state["face_det_box_ts"] = now_ts if face_det_box is not None else 0.0
                if quality_ok and face_crop is not None and face_score > current_state.get("best_face_score", 0.0):
                    current_state["best_face_crop"] = face_crop
                    current_state["best_face_score"] = face_score

        if not quality_ok:
            return

        with self.person_state_lock:
            current_state = self.person_states.get(person_id)
            if current_state is None:
                return
            current_state["last_face_check"] = now_ts
            current_state["face_pending"] = True
            self.face_global_last_check = now_ts
            cached_best_face = current_state.get("best_face_crop")
            cached_best_score = float(current_state.get("best_face_score", 0.0) or 0.0)
        chosen_face = cached_best_face if cached_best_face is not None and cached_best_score >= face_score else face_crop
        if SAVE_FACE_RECOG_INPUTS:
            save_face_debug_image(chosen_face, person_id, face_score, now_ts, force=True)

        try:
            face_rec_started = time.perf_counter()
            try:
                label, score = self.face_library.recognize(chosen_face)
            finally:
                self._face_rec_ms += (time.perf_counter() - face_rec_started) * 1000.0
            self._apply_face_result(person_id, label, score)
        except Exception as e:
            print(f"[Face] synchronous recognize failed: {e}")
            with self.person_state_lock:
                current_state = self.person_states.get(person_id)
                if current_state is not None:
                    current_state["face_pending"] = False
                    current_state["last_face_check"] = now_ts

    def _update_face_det_debug(self, frame, person_id, det, now_ts):
        if self.face_detector is None or not self.face_detector.enabled:
            return

        matched_face = self._get_face_detection_for_person(det["box"])
        face_det_box = matched_face["box"] if matched_face is not None else None

        with self.person_state_lock:
            current_state = self.person_states.get(person_id)
            if current_state is not None:
                current_state["face_det_box"] = face_det_box
                current_state["face_det_box_ts"] = now_ts if face_det_box is not None else 0.0

    def _build_alerts(self, frame, detections, now_ts):
        self._ensure_face_library_loaded(bool(detections))
        self._refresh_face_det_cache(frame, now_ts, has_people=bool(detections))
        alerts = []
        for person_id, state, det in self._assign_person_ids(detections, now_ts):
            self._update_face_det_debug(frame, person_id, det, now_ts)
            self._maybe_recognize_face(frame, person_id, state, det, now_ts)
            with self.person_state_lock:
                latest_state = dict(self.person_states.get(person_id, state))

            box = det["box"]
            kpts = det["kpts"]
            structure_fallen = is_person_fallen(box, kpts, FALL_ASPECT_RATIO_THRESHOLD, frame.shape)
            with self.person_state_lock:
                tracked_state = self.person_states.get(person_id)
                if tracked_state is not None:
                    motion_fallen = analyze_fall_motion(tracked_state, frame.shape)
                    raw_fallen = structure_fallen or motion_fallen
                    if raw_fallen:
                        if not tracked_state.get("fall_candidate_since", 0.0):
                            tracked_state["fall_candidate_since"] = now_ts
                        tracked_state["fall_recover_since"] = 0.0
                        if tracked_state.get("fall_confirmed") or now_ts - tracked_state["fall_candidate_since"] >= FALL_CONFIRM_SECONDS:
                            tracked_state["fall_confirmed"] = True
                    else:
                        tracked_state["fall_candidate_since"] = 0.0
                        if tracked_state.get("fall_confirmed"):
                            if not tracked_state.get("fall_recover_since", 0.0):
                                tracked_state["fall_recover_since"] = now_ts
                            elif now_ts - tracked_state["fall_recover_since"] >= FALL_RELEASE_SECONDS:
                                tracked_state["fall_confirmed"] = False
                                tracked_state["fall_recover_since"] = 0.0
                        else:
                            tracked_state["fall_recover_since"] = 0.0
                    tracked_state["fall_raw"] = raw_fallen
                    tracked_state["fall_structure"] = structure_fallen
                    tracked_state["fall_motion"] = motion_fallen
                    latest_state = dict(tracked_state)
                else:
                    raw_fallen = structure_fallen
                    motion_fallen = False

            is_fallen = latest_state.get("fall_confirmed", False)
            status = "FALL DETECTED" if is_fallen else "Normal"
            color = (0, 0, 255) if is_fallen else (0, 255, 0)
            is_sitting = self._is_long_sit_state(latest_state, now_ts)
            _bh = list(latest_state.get("box_history", []))
            sit_duration_sec = (now_ts - _bh[0][0]) if (is_sitting and _bh) else 0.0
            alerts.append({
                "box": box,
                "kpts": kpts,
                "status": status,
                "color": color,
                "id": person_id,
                "fall_raw": latest_state.get("fall_raw", raw_fallen),
                "fall_structure": latest_state.get("fall_structure", structure_fallen),
                "fall_motion": latest_state.get("fall_motion", motion_fallen),
                "face_label": latest_state.get("face_label", "pending"),
                "face_score": latest_state.get("face_score"),
                "face_det_box": latest_state.get("face_det_box"),
                "face_det_box_ts": latest_state.get("face_det_box_ts", 0.0),
                "vlm_summary": latest_state.get("vlm_last_summary"),
                "vlm_event": latest_state.get("vlm_last_event"),
                "vlm_risk_level": latest_state.get("vlm_last_risk_level"),
                "now_ts": now_ts,
                "is_sitting": is_sitting,
                "sit_duration_sec": sit_duration_sec,
            })
            self._maybe_trigger_vlm_events(frame, person_id, latest_state, det, now_ts)
        return alerts

    def get_detected_frame(self):
        if not self.running:
            return None

        if not self.inference_enabled:
            raw_frame = self.get_latest_raw_frame()
            if raw_frame is not None:
                return raw_frame, []
            return None

        frame = None
        wait_deadline = time.time() + 1.0
        while self.running and frame is None and time.time() < wait_deadline:
            with self.frame_lock:
                if self.latest_frame is not None:
                    frame = self.latest_frame.copy()
                    self.latest_frame = None
                    self.frame_ready.clear()
            if frame is None:
                time.sleep(0.005)

        if frame is None:
            raw_frame = self.get_latest_raw_frame()
            if raw_frame is not None:
                return raw_frame, []
            return None

        now = time.time()
        if now - self._last_infer_ts < self._infer_interval:
            return frame, []
        self._last_infer_ts = now

        try:
            t1 = time.time()
            resized, pp = pre_process_stream(frame, self.dvpp, self.input_dtype, self.input_layout)
            if resized is None or pp is None:
                return frame, []

            resized = np.ascontiguousarray(resized, dtype=self.input_dtype)
            expected_shape = (1, MODEL_HEIGHT, MODEL_WIDTH, 3) if self.input_layout == "NHWC" else (1, 3, MODEL_HEIGHT, MODEL_WIDTH)
            if resized.shape != expected_shape:
                raise ValueError(f'Invalid input shape: {resized.shape}')

            t2 = time.time()
            with ACL_MODEL_EXEC_LOCK:
                result = self.model.execute([resized])
            if result is None:
                raise RuntimeError("AclLiteModel.execute returned None")
            self._infer_fail_count = 0

            t3 = time.time()
            output = result[0]
            if output is None:
                raise RuntimeError("Model output is None")
            if isinstance(output, np.ndarray):
                if output.ndim == 3 and output.shape[1] == 56:
                    output = np.transpose(output, (0, 2, 1))
                detections = parse_predictions(output[0] if output.ndim == 3 else output)
            else:
                detections = []

            final_dets = []
            for det in detections:
                box = [(val - pp[p]) / pp['scale'] for val, p in zip(det['box'], ['pad_x', 'pad_y', 'pad_x', 'pad_y'])]
                kpts = [((k[0] - pp['pad_x']) / pp['scale'], (k[1] - pp['pad_y']) / pp['scale'], k[2]) for k in det['keypoints']]
                final_dets.append({'box': box, 'kpts': kpts})

            self._face_det_ms = 0.0
            self._face_rec_ms = 0.0
            alerts = self._build_alerts(frame, final_dets, time.time())
            res_frame = draw_results(frame, alerts)
            t4 = time.time()
            self._record_perf(t1, t2, t3, t4)
            return res_frame, alerts
        except Exception as e:
            self._infer_fail_count += 1
            now = time.time()
            if now - self._last_infer_error_log > 1.0:
                print(
                    f'[InferError] {type(e).__name__}: {e} | '
                    f'mode={self.input_layout} {self.input_dtype.__name__}'
                )
                self._last_infer_error_log = now

            if self._infer_fail_count == 3 and self.input_dtype is np.float32:
                self.input_dtype = np.float16
                print('[InferError] Switching input mode to NCHW float16')
            elif self._infer_fail_count == 6 and self.input_layout == "NCHW":
                self.input_layout = "NHWC"
                self.input_dtype = np.float32
                print('[InferError] Switching input mode to NHWC float32')
            elif self._infer_fail_count == 9 and self.input_layout == "NHWC" and self.input_dtype is np.float32:
                self.input_dtype = np.float16
                print('[InferError] Switching input mode to NHWC float16')
            elif self._infer_fail_count >= 12:
                print('[InferError] Consecutive inference failures reached limit, disabling inference and keeping raw video stream alive.')
                self.inference_enabled = False

            time.sleep(0.2)
            return frame, []

    def get_latest_raw_frame(self):
        with self.frame_lock:
            if self.latest_frame is None:
                return None
            return self.latest_frame.copy()

    def stop(self):
        self.running = False
        self.frame_ready.set()
        self.result_ready.set()
        self.camera_stop.set()
        self._clear_camera_frames()
        if self.camera_thread is not None:
            self.camera_thread.join(timeout=4.0)
        print('Detector Stopped')
# ---------------------- ????????----------------------

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
