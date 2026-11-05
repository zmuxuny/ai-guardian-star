"""Fail-closed board-side head-pose probe primitives.

The model runner is injected so this module can be tested on a workstation and
bound to an ACL/OM runner on the Orange Pi without importing ACL at module load.
"""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
from typing import Callable, Optional

import numpy as np


class PoseProbeError(ValueError):
    """The pose sample cannot be trusted for enrollment."""


@dataclass(frozen=True)
class PoseAngles:
    yaw: float
    pitch: float
    roll: float
    model_id: str
    calibration_id: str = ""


@dataclass(frozen=True)
class PoseCalibration:
    calibration_id: str
    model_id: str
    yaw_sign: int
    pitch_sign: int
    roll_sign: int
    yaw_offset: float
    pitch_offset: float
    roll_offset: float


@dataclass(frozen=True)
class PoseGateResult:
    accepted: bool
    reason: str


def model_fingerprint(model_path, output_contract="rotation6d-v1",
                      preprocess_contract="rgb224-imagenet-nchw-f32-v1"):
    path = Path(model_path)
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    digest.update(b"\0")
    digest.update(str(output_contract).encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(preprocess_contract).encode("utf-8"))
    return "sha256:" + digest.hexdigest()


def apply_pose_calibration(angles, calibration):
    if not calibration.calibration_id:
        raise PoseProbeError("CALIBRATION_ID_REQUIRED")
    if angles.model_id != calibration.model_id:
        raise PoseProbeError("MODEL_ID_MISMATCH")
    signs = (calibration.yaw_sign, calibration.pitch_sign, calibration.roll_sign)
    if any(sign not in (-1, 1) for sign in signs):
        raise PoseProbeError("INVALID_CALIBRATION_SIGN")
    raw_values = (angles.yaw, angles.pitch, angles.roll)
    offsets = (calibration.yaw_offset, calibration.pitch_offset, calibration.roll_offset)
    if not all(math.isfinite(float(value)) for value in raw_values + offsets):
        raise PoseProbeError("INVALID_CALIBRATION_VALUE")
    values = tuple(float(raw) * sign + float(offset)
                   for raw, sign, offset in zip(raw_values, signs, offsets))
    return PoseAngles(*values, angles.model_id, calibration.calibration_id)


def classify_enrollment_pose(angles, target_pose, expected_model_id,
                             expected_calibration_id):
    if target_pose not in ("front", "left", "right"):
        raise PoseProbeError("UNKNOWN_TARGET_POSE")
    if not expected_model_id or angles.model_id != expected_model_id:
        return PoseGateResult(False, "MODEL_ID_MISMATCH")
    if not angles.calibration_id:
        return PoseGateResult(False, "CALIBRATION_MISSING")
    if (not expected_calibration_id
            or angles.calibration_id != expected_calibration_id):
        return PoseGateResult(False, "CALIBRATION_ID_MISMATCH")
    values = (angles.yaw, angles.pitch, angles.roll)
    if not all(math.isfinite(float(value)) for value in values):
        return PoseGateResult(False, "INVALID_POSE")
    if not -20.0 <= float(angles.pitch) <= 20.0:
        return PoseGateResult(False, "PITCH_OUT_OF_RANGE")
    if not -15.0 <= float(angles.roll) <= 15.0:
        return PoseGateResult(False, "ROLL_OUT_OF_RANGE")
    yaw = float(angles.yaw)
    accepted = (
        (-15.0 <= yaw <= 15.0) if target_pose == "front"
        else (yaw <= -25.0) if target_pose == "left"
        else (yaw >= 25.0)
    )
    return PoseGateResult(accepted, "READY" if accepted else "YAW_OUT_OF_RANGE")


def _resize_bilinear(image, size):
    height, width = image.shape[:2]
    y = np.linspace(0.0, height - 1.0, size, dtype=np.float32)
    x = np.linspace(0.0, width - 1.0, size, dtype=np.float32)
    y0 = np.floor(y).astype(np.intp)
    x0 = np.floor(x).astype(np.intp)
    y1 = np.minimum(y0 + 1, height - 1)
    x1 = np.minimum(x0 + 1, width - 1)
    wy = (y - y0).reshape(size, 1, 1)
    wx = (x - x0).reshape(1, size, 1)
    source = image.astype(np.float32)
    top = source[y0[:, None], x0[None, :]] * (1.0 - wx) + source[y0[:, None], x1[None, :]] * wx
    bottom = source[y1[:, None], x0[None, :]] * (1.0 - wx) + source[y1[:, None], x1[None, :]] * wx
    return top * (1.0 - wy) + bottom * wy


def _preprocess_bgr(image, size):
    if (image is None or not isinstance(image, np.ndarray) or image.ndim != 3
            or image.shape[2] != 3 or image.size == 0
            or image.shape[0] < 2 or image.shape[1] < 2):
        raise PoseProbeError("INVALID_IMAGE")
    if image.dtype != np.uint8:
        raise PoseProbeError("INVALID_IMAGE_DTYPE")
    rgb = _resize_bilinear(image[:, :, ::-1], size) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    normalized = (rgb - mean) / std
    return np.transpose(normalized, (2, 0, 1))[np.newaxis, ...].astype(np.float32)


def _rotation6d_to_matrix(values):
    raw = np.asarray(values, dtype=np.float32).reshape(-1)
    if raw.size != 6 or not np.all(np.isfinite(raw)):
        raise PoseProbeError("INVALID_MODEL_OUTPUT")
    first = raw[:3]
    second = raw[3:]
    first_norm = float(np.linalg.norm(first))
    if first_norm <= 1e-6:
        raise PoseProbeError("INVALID_MODEL_OUTPUT")
    first = first / first_norm
    second = second - float(np.dot(first, second)) * first
    second_norm = float(np.linalg.norm(second))
    if second_norm <= 1e-6:
        raise PoseProbeError("INVALID_MODEL_OUTPUT")
    second = second / second_norm
    third = np.cross(first, second)
    return np.stack((first, second, third), axis=1)


def _matrix_to_angles(matrix):
    matrix = np.asarray(matrix, dtype=np.float32)
    if matrix.shape != (3, 3) or not np.all(np.isfinite(matrix)):
        raise PoseProbeError("INVALID_ROTATION_MATRIX")
    singular_guard = math.sqrt(float(matrix[0, 0] ** 2 + matrix[1, 0] ** 2))
    pitch = math.atan2(float(matrix[2, 1]), float(matrix[2, 2]))
    yaw = math.atan2(float(-matrix[2, 0]), singular_guard)
    roll = math.atan2(float(matrix[1, 0]), float(matrix[0, 0]))
    return tuple(math.degrees(value) for value in (yaw, pitch, roll))


class FacePoseEstimator:
    def __init__(self, model_id, infer, input_size=224):
        if not model_id or not callable(infer) or int(input_size) < 2:
            raise PoseProbeError("INVALID_ESTIMATOR_CONFIGURATION")
        self.model_id = str(model_id)
        self.infer = infer
        self.input_size = int(input_size)

    def estimate(self, bgr_face):
        tensor = _preprocess_bgr(bgr_face, self.input_size)
        output = self.infer(tensor)
        matrix = _rotation6d_to_matrix(output)
        yaw, pitch, roll = _matrix_to_angles(matrix)
        if not all(math.isfinite(value) for value in (yaw, pitch, roll)):
            raise PoseProbeError("INVALID_POSE")
        return PoseAngles(yaw=yaw, pitch=pitch, roll=roll, model_id=self.model_id)
