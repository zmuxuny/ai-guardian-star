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
    return float(default)


MIN_BRIGHTNESS = setting("AI_GUARDIAN_FACE_MIN_BRIGHTNESS", 18, 1, 100)
MIN_CONTRAST = setting("AI_GUARDIAN_FACE_MIN_CONTRAST", 8, 0, 80)
MIN_SHARPNESS = setting("AI_GUARDIAN_FACE_MIN_SHARPNESS", 8, 0, 500)
LOW_LIGHT_LEVEL = 65.0
SAMPLE_INTERVAL = 0.5
BEST_CROP_TTL = 2.0


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
