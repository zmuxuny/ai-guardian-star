"""Small face-image checks and bounded enhancement; no ACL or camera imports."""

import math
import os

import numpy as np


def setting(name, default, minimum, maximum):
    try:
        value = float(os.getenv(name, str(default)))
        if math.isfinite(value):
            return max(minimum, min(maximum, value))
    except (TypeError, ValueError):
        pass
    return max(minimum, min(maximum, float(default)))


MIN_BRIGHTNESS = setting("AI_GUARDIAN_FACE_MIN_BRIGHTNESS", 18, 1, 100)
MIN_CONTRAST = setting("AI_GUARDIAN_FACE_MIN_CONTRAST", 8, 0, 80)
MIN_SHARPNESS = setting("AI_GUARDIAN_FACE_MIN_SHARPNESS", 8, 0, 500)
LOW_LIGHT_LEVEL = 65.0
SAMPLE_INTERVAL = 0.5
BEST_CROP_TTL = 2.0
WAIT_TIMEOUT_BASE = setting("AI_GUARDIAN_FACE_WAIT_SECONDS", 20, 8, 300)
WAIT_TIMEOUT_MAX = setting("AI_GUARDIAN_FACE_WAIT_MAX_SECONDS", 60, WAIT_TIMEOUT_BASE, 600)


def expire_face_wait(state, now, active_people=1):
    """Apply the requested display timeout, independently of match evidence.

    A timeout means identity was not established in time, not proof of non-enrollment.
    Matched people do not expire; later successful recognition can replace a timeout.
    """
    label = str(state.get("face_label", "pending"))
    if label.startswith("known:"):
        state.update(face_wait_started=None, face_wait_seconds=0.0,
                     face_timeout_seconds=0.0, face_timed_out=False)
        return False
    if state.get("face_timed_out"):
        # Once expired, new people/quality samples cannot reopen the deadline or
        # turn the timeout explanation into evidence-based non-enrollment.
        started = state.get("face_wait_started", now)
        elapsed = max(0.0, now - float(started if started is not None else now))
        state.update(face_label="stranger", face_reason="timeout", face_score=None,
                     face_wait_seconds=elapsed, face_pending=False)
        return True
    if label == "stranger" and not state.get("face_timed_out"):
        return False
    started = state.get("face_wait_started")
    if started is None:
        started = state.get("first_seen", now)
        state["face_wait_started"] = started
    quality_reason = state.get("face_quality_reason", state.get("face_reason"))
    poor_quality = quality_reason in ("too_dark", "overexposed", "low_contrast", "blurred",
                                     "landmarks_unavailable", "no_face", "low_light")
    allowance = WAIT_TIMEOUT_BASE + 4 * max(0, active_people - 1) + (10 if poor_quality else 0)
    # Extend for congestion/quality, never shorten a running deadline; always bounded.
    allowance = min(WAIT_TIMEOUT_MAX, max(allowance, state.get("face_timeout_seconds", 0.0)))
    elapsed = max(0.0, now - float(started))
    state.update(face_wait_seconds=elapsed, face_timeout_seconds=allowance)
    if elapsed >= allowance:
        state.update(face_label="stranger", face_score=None, face_reason="timeout",
                     face_timed_out=True, face_pending=False)
        return True
    return False


def assess_face_image(image):
    result = dict(usable=False, reason="no_face", brightness=0.0,
                  contrast=0.0, sharpness=0.0, rank=0.0)
    if image is None or image.ndim != 3 or image.shape[2] != 3 or min(image.shape[:2]) < 24:
        return result
    # Bound CPU work and avoid depending on a particular OpenCV build.
    step = max(1, int(math.ceil(max(image.shape[:2]) / 160.0)))
    pixels = np.asarray(image[::step, ::step], dtype=np.float32)
    if not np.all(np.isfinite(pixels)):
        return result
    gray = pixels[:, :, 0] * 0.114 + pixels[:, :, 1] * 0.587 + pixels[:, :, 2] * 0.299
    brightness = float(gray.mean())
    contrast = float(gray.std())
    laplacian = (gray[1:-1, :-2] + gray[1:-1, 2:] + gray[:-2, 1:-1]
                 + gray[2:, 1:-1] - 4 * gray[1:-1, 1:-1])
    sharpness = float(laplacian.var())
    reason = "ready"
    if brightness < MIN_BRIGHTNESS or float(np.mean(gray < 8)) > 0.85:
        reason = "too_dark"
    elif brightness > 245 or float(np.mean(gray > 250)) > 0.85:
        reason = "overexposed"
    elif contrast < MIN_CONTRAST:
        reason = "low_contrast"
    elif sharpness < MIN_SHARPNESS:
        reason = "blurred"
    elif brightness < LOW_LIGHT_LEVEL:
        reason = "low_light"
    # Rank is only a frame-selection heuristic, never a match probability.
    rank = (min(sharpness, 500) / 500 + min(contrast, 60) / 60
            + min(brightness, 100) / 100)
    result.update(usable=reason in ("ready", "low_light"), reason=reason,
                  brightness=brightness, contrast=contrast, sharpness=sharpness, rank=rank)
    return result


def enhance_face_image(image, cv_module=None):
    """Preserve ordinary images; mildly brighten usable dark crops without mutation.

    CLAHE is opt-in pending board measurements; unavailable APIs fall back to gamma.
    The same transform is used for enrollment and live feature extraction.
    """
    quality = assess_face_image(image)
    if not quality["usable"] or quality["reason"] != "low_light":
        return image
    brightness = quality["brightness"]
    gamma = max(0.70, min(1.0, math.log(80.0 / 255.0) / math.log(max(brightness, 1) / 255.0)))
    table = np.clip(np.power(np.arange(256, dtype=np.float32) / 255.0, gamma) * 255, 0, 255).astype(np.uint8)
    adjusted = table[np.clip(image, 0, 255).astype(np.uint8)]
    if os.getenv("AI_GUARDIAN_FACE_CLAHE", "0").lower() in ("1", "true", "on", "yes"):
        try:
            lab = cv_module.cvtColor(adjusted, cv_module.COLOR_BGR2LAB)
            lab[:, :, 0] = cv_module.createCLAHE(clipLimit=1.5, tileGridSize=(4, 4)).apply(lab[:, :, 0])
            adjusted = cv_module.cvtColor(lab, cv_module.COLOR_LAB2BGR)
        except Exception:
            pass
    return np.ascontiguousarray(adjusted)
