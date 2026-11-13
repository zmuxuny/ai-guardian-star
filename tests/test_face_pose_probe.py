"""Board-side head-pose probe contracts without model weights or ACL hardware."""

import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from guardian_face_pose import (
    FacePoseEstimator,
    PoseAngles,
    PoseCalibration,
    PoseProbeError,
    apply_pose_calibration,
    classify_enrollment_pose,
    model_fingerprint,
)


class PoseGateTests(unittest.TestCase):
    def calibrated(self, yaw=0.0, pitch=0.0, roll=0.0, model_id="pose-model"):
        return apply_pose_calibration(
            PoseAngles(yaw=yaw, pitch=pitch, roll=roll, model_id=model_id),
            PoseCalibration("board-camera-v1", model_id, 1, 1, 1, 0.0, 0.0, 0.0),
        )

    def test_strict_pose_boundaries_match_app_contract(self):
        model_id = "pose-model"
        accepted = {
            "front": (-15.0, 15.0),
            "left": (-25.0, -80.0),
            "right": (25.0, 80.0),
        }
        for pose, yaws in accepted.items():
            for yaw in yaws:
                with self.subTest(pose=pose, yaw=yaw):
                    result = classify_enrollment_pose(
                        self.calibrated(yaw=yaw, pitch=20.0, roll=-15.0),
                        pose,
                        expected_model_id=model_id,
                        expected_calibration_id="board-camera-v1",
                    )
                    self.assertTrue(result.accepted)

        for pose, yaw in (("front", -15.01), ("front", 15.01),
                          ("left", -24.99), ("right", 24.99)):
            with self.subTest(pose=pose, yaw=yaw):
                self.assertFalse(classify_enrollment_pose(
                    self.calibrated(yaw=yaw),
                    pose,
                    expected_model_id=model_id,
                    expected_calibration_id="board-camera-v1",
                ).accepted)

    def test_pitch_roll_nonfinite_and_model_mismatch_fail_closed(self):
        valid = self.calibrated(model_id="expected")
        cases = (
            (self.calibrated(pitch=20.01, model_id="expected"), "PITCH_OUT_OF_RANGE"),
            (self.calibrated(roll=-15.01, model_id="expected"), "ROLL_OUT_OF_RANGE"),
            (PoseAngles(math.nan, 0.0, 0.0, "expected", "board-camera-v1"), "INVALID_POSE"),
            (valid, "MODEL_ID_MISMATCH"),
        )
        for index, (angles, reason) in enumerate(cases):
            expected = "other" if index == 3 else "expected"
            with self.subTest(reason=reason):
                result = classify_enrollment_pose(
                    angles, "front", expected, "board-camera-v1")
                self.assertFalse(result.accepted)
                self.assertEqual(result.reason, reason)

    def test_unknown_target_pose_is_rejected(self):
        with self.assertRaises(PoseProbeError):
            classify_enrollment_pose(self.calibrated(model_id="model"), "profile", "model", "board-camera-v1")

    def test_raw_or_wrong_calibration_never_reaches_gate(self):
        raw = PoseAngles(0.0, 0.0, 0.0, "pose-model")
        self.assertEqual(
            classify_enrollment_pose(raw, "front", "pose-model", "board-camera-v1").reason,
            "CALIBRATION_MISSING",
        )
        wrong = PoseAngles(0.0, 0.0, 0.0, "pose-model", "other-camera")
        self.assertEqual(
            classify_enrollment_pose(wrong, "front", "pose-model", "board-camera-v1").reason,
            "CALIBRATION_ID_MISMATCH",
        )

    def test_calibration_applies_signs_then_offsets_and_rejects_bad_contract(self):
        raw = PoseAngles(10.0, -5.0, 2.0, "pose-model")
        calibrated = apply_pose_calibration(
            raw,
            PoseCalibration("board-camera-v1", "pose-model", -1, -1, 1, 1.0, -2.0, 3.0),
        )
        self.assertEqual((calibrated.yaw, calibrated.pitch, calibrated.roll), (-9.0, 3.0, 5.0))
        for calibration in (
            PoseCalibration("", "pose-model", 1, 1, 1, 0.0, 0.0, 0.0),
            PoseCalibration("board", "other-model", 1, 1, 1, 0.0, 0.0, 0.0),
            PoseCalibration("board", "pose-model", 0, 1, 1, 0.0, 0.0, 0.0),
        ):
            with self.subTest(calibration=calibration):
                with self.assertRaises(PoseProbeError):
                    apply_pose_calibration(raw, calibration)


class EstimatorTests(unittest.TestCase):
    def test_model_fingerprint_uses_file_bytes_and_contract_version(self):
        with tempfile.TemporaryDirectory() as directory:
            model = Path(directory) / "pose.om"
            model.write_bytes(b"model-a")
            first = model_fingerprint(model, output_contract="rotation6d-v1")
            second = model_fingerprint(model, output_contract="rotation-matrix-v1")
            preprocess_changed = model_fingerprint(
                model,
                output_contract="rotation6d-v1",
                preprocess_contract="rgb256-v2",
            )
            model.write_bytes(b"model-b")
            third = model_fingerprint(model, output_contract="rotation6d-v1")
        self.assertTrue(first.startswith("sha256:"))
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, preprocess_changed)
        self.assertNotEqual(first, third)

    def test_identity_rotation6d_decodes_to_zero_angles(self):
        seen = []

        def infer(tensor):
            seen.append(tensor)
            return np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0], np.float32)

        estimator = FacePoseEstimator(
            model_id="pose-model",
            infer=infer,
            input_size=4,
        )
        image = np.full((8, 6, 3), 127, np.uint8)
        angles = estimator.estimate(image)
        self.assertEqual(seen[0].shape, (1, 3, 4, 4))
        self.assertEqual(seen[0].dtype, np.float32)
        self.assertAlmostEqual(angles.yaw, 0.0, places=4)
        self.assertAlmostEqual(angles.pitch, 0.0, places=4)
        self.assertAlmostEqual(angles.roll, 0.0, places=4)
        self.assertEqual(angles.model_id, "pose-model")
        self.assertEqual(angles.calibration_id, "")

    def test_invalid_image_or_model_output_is_rejected(self):
        estimator = FacePoseEstimator("pose-model", lambda tensor: np.zeros(5, np.float32))
        for image in (None, np.zeros((0, 0, 3), np.uint8), np.zeros((10, 10), np.uint8)):
            with self.subTest(shape=getattr(image, "shape", None)):
                with self.assertRaises(PoseProbeError):
                    estimator.estimate(image)
        with self.assertRaises(PoseProbeError):
            estimator.estimate(np.zeros((20, 20, 3), np.uint8))

    def test_preprocess_uses_deterministic_bilinear_rgb_resize(self):
        captured = []

        def infer(tensor):
            captured.append(tensor)
            return np.array([1.0, 0.0, 0.0, 0.0, 1.0, 0.0], np.float32)

        estimator = FacePoseEstimator("pose-model", infer, input_size=3)
        bgr = np.array([
            [[0, 0, 0], [0, 0, 200]],
            [[0, 200, 0], [200, 0, 0]],
        ], dtype=np.uint8)
        estimator.estimate(bgr)
        center_rgb = np.array([50.0, 50.0, 50.0], np.float32) / 255.0
        expected = (center_rgb - np.array([0.485, 0.456, 0.406], np.float32)) / np.array(
            [0.229, 0.224, 0.225], np.float32)
        np.testing.assert_allclose(captured[0][0, :, 1, 1], expected, atol=1e-5)


class BenchmarkPrivacyTests(unittest.TestCase):
    def test_report_contains_only_hashed_sample_ids_and_numeric_metrics(self):
        from tools.face_pose_probe.benchmark import build_report

        rows = [{
            "sample_id": "front-01",
            "source_path": "C:/private/Yang/front.jpg",
            "name": "Yang",
            "expected": {"yaw": 0.0, "pitch": 1.0, "roll": -1.0},
            "actual": {"yaw": 1.0, "pitch": 0.0, "roll": -2.0},
            "latency_ms": 12.5,
            "expected_pose": "front",
            "actual_pose": "front",
        }]
        report = build_report("pose-model", rows)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("Yang", encoded)
        self.assertNotIn("front.jpg", encoded)
        self.assertNotIn("source_path", encoded)
        self.assertRegex(report["samples"][0]["sample_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(report["latency_ms"]["p95"], 12.5)
        self.assertEqual(report["mae_degrees"], {"yaw": 1.0, "pitch": 1.0, "roll": 1.0})
        self.assertEqual(report["gate_confusion"], {"match": 1, "mismatch": 0})

    def test_blank_ids_and_nonfinite_metrics_are_rejected(self):
        from tools.face_pose_probe.benchmark import BenchmarkInputError, build_report

        base = {
            "sample_id": "sample-1",
            "expected": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "actual": {"yaw": 0.0, "pitch": 0.0, "roll": 0.0},
            "latency_ms": 1.0,
            "expected_pose": "front",
            "actual_pose": "front",
        }
        for override in ({"sample_id": ""}, {"latency_ms": math.nan},
                         {"actual": {"yaw": math.inf, "pitch": 0.0, "roll": 0.0}}):
            row = dict(base)
            row.update(override)
            with self.subTest(override=override):
                with self.assertRaises(BenchmarkInputError):
                    build_report("pose-model", [row])
        with self.assertRaises(BenchmarkInputError):
            build_report("", [base])


if __name__ == "__main__":
    unittest.main()
