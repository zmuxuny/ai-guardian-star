import threading
import time
import cv2

_stats_lock = threading.Lock()
_stats = {
    "fps": 0.0, "detections": 0, "fall_count": 0,
    "status": "正常", "mqtt_connected": True,
    "start_time": time.time(),
    "keypoint_scores": None, "last_fall_time": None,
    "frame_count": 0,
    "face_label": None, "face_score": None,
    "sit_duration": 0.0, "sit_count": 0, "stranger_count": 0,
    "faces": [],
}

def update_stats(fps=None, detections=None, fall_count_inc=False,
                 last_fall_time=None, status=None,
                 keypoint_scores=None, mqtt_connected=None, frame_count_inc=False,
                 face_label=None, face_score=None,
                 sit_duration=None, sit_count_inc=False, stranger_count_inc=False,
                 faces=None):
    with _stats_lock:
        if fps is not None: _stats["fps"] = round(fps, 1)
        if detections is not None: _stats["detections"] = detections
        if fall_count_inc: _stats["fall_count"] += 1
        if status is not None: _stats["status"] = status
        if mqtt_connected is not None: _stats["mqtt_connected"] = mqtt_connected
        if keypoint_scores is not None: _stats["keypoint_scores"] = keypoint_scores
        if last_fall_time is not None: _stats["last_fall_time"] = last_fall_time
        if frame_count_inc: _stats["frame_count"] += 1
        if face_label is not None: _stats["face_label"] = face_label
        if face_score is not None: _stats["face_score"] = face_score
        if sit_duration is not None: _stats["sit_duration"] = sit_duration
        if sit_count_inc: _stats["sit_count"] += 1
        if stranger_count_inc: _stats["stranger_count"] += 1
        if faces is not None: _stats["faces"] = faces

def get_stats():
    with _stats_lock:
        return dict(_stats)

encoded_frame_bytes = None
lock = threading.Lock()
last_encode_time = 0.0
# 分辨率降低以减少 FRP 隧道缓冲积压，有效降低视频延迟
JPEG_SIZE = (320, 240)
JPEG_QUALITY = 35
MAX_ENCODE_FPS = 20.0


def update_frame(frame):
    """
    Limit JPEG encoding frequency so the CPU is not dominated by streaming work.
    """
    global encoded_frame_bytes, last_encode_time

    now = time.time()
    if now - last_encode_time < 1.0 / MAX_ENCODE_FPS:
        return
    last_encode_time = now

    small_frame = cv2.resize(frame, JPEG_SIZE)
    ok, encoded = cv2.imencode('.jpg', small_frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        return

    with lock:
        encoded_frame_bytes = encoded.tobytes()


def get_current_frame():
    with lock:
        return encoded_frame_bytes


def start_stream():
    """Compatibility placeholder."""
    pass
