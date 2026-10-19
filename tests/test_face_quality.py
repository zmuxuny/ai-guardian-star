"""Pixel-quality checks use real NumPy; live scheduling uses isolated source bodies."""

import os
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from test_face_recognition import face_namespace
from test_runtime import load_definition
from guardian_face_quality import assess_face_image, enhance_face_image, setting


def textured_face(low=60, high=150, size=80):
    values = np.where(np.indices((size, size)).sum(axis=0) % 2, low, high).astype(np.uint8)
    return np.repeat(values[:, :, None], 3, axis=2)


class ImageQualityTests(unittest.TestCase):
    def test_normal_image_is_usable_and_unchanged(self):
        image = textured_face()
        self.assertTrue(assess_face_image(image)["usable"])
        self.assertIs(enhance_face_image(image), image)

    def test_dark_flat_overexposed_and_small_images_are_rejected(self):
        for image, reason in ((np.zeros((80, 80, 3)), "too_dark"),
                              (np.full((80, 80, 3), 255), "overexposed"),
                              (np.full((80, 80, 3), 100), "low_contrast"),
                              (np.zeros((10, 10, 3)), "no_face")):
            with self.subTest(reason=reason):
                result = assess_face_image(image)
                self.assertFalse(result["usable"])
                self.assertEqual(result["reason"], reason)

    def test_smooth_gradient_is_rejected_as_blurred(self):
        gradient = np.tile(np.linspace(40, 180, 80).astype(np.uint8), (80, 1))
        result = assess_face_image(np.repeat(gradient[:, :, None], 3, axis=2))
        self.assertEqual(result["reason"], "blurred")

    def test_nonfinite_pixels_and_non_color_images_are_rejected(self):
        for image in (None, np.full((80, 80, 3), np.nan), np.zeros((80, 80))):
            self.assertFalse(assess_face_image(image)["usable"])

    def test_moderately_dark_image_is_brightened_without_mutating_input(self):
        image = textured_face(20, 60)
        before = image.copy()
        self.assertEqual(assess_face_image(image)["reason"], "low_light")
        result = enhance_face_image(image)
        self.assertGreater(float(result.mean()), float(image.mean()))
        self.assertLess(float(result.mean()), 100)
        self.assertEqual(result.dtype, np.uint8)
        self.assertEqual(result.shape, image.shape)
        np.testing.assert_array_equal(image, before)

    def test_optional_clahe_failure_keeps_gamma_result(self):
        image = textured_face(20, 60)
        expected = enhance_face_image(image)
        with patch.dict(os.environ, {"AI_GUARDIAN_FACE_CLAHE": "1"}):
            result = enhance_face_image(image, SimpleNamespace())
        np.testing.assert_array_equal(result, expected)

    def test_invalid_configuration_uses_default_and_numeric_values_are_bounded(self):
        for value, expected in (("nan", 20), ("bad", 20), ("999", 100), ("-1", 1)):
            with patch.dict(os.environ, {"FACE_TEST_SETTING": value}):
                self.assertEqual(setting("FACE_TEST_SETTING", 20, 1, 100), expected)


class QualityGateIntegrationTests(unittest.TestCase):
    def detector(self):
        namespace = face_namespace()
        namespace.update(assess_face_image=assess_face_image,
            is_front_face_candidate=lambda *args: False,
            extract_face_crop=lambda *args: None, score_face_crop=lambda *args: 1.2)
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                                 "_maybe_recognize_face")
        library = SimpleNamespace(revision=1, _state_lock=threading.RLock(),
            _log_diag=Mock(), recognize=Mock(return_value=("unknown", 0.2)))
        detector = SimpleNamespace(face_library_loaded=True, face_detector=SimpleNamespace(enabled=True),
            face_library=library, person_state_lock=threading.Lock(), face_global_last_check=108,
            person_states={1: {"first_seen": 100, "face_label": "pending"}}, _face_rec_ms=0,
            _get_face_detection_for_person=lambda body: {"box": [0, 0, 80, 80], "score": 0.9},
            _apply_face_result=Mock(), _sync_face_library_revision=Mock())
        def run(image, now):
            method(detector, image, 1, dict(detector.person_states[1]),
                   {"box": [0, 0, 80, 80], "kpts": []}, now)
        return detector, run

    def test_dark_frame_does_not_reach_recognition_or_vote(self):
        detector, run = self.detector()
        run(np.zeros((80, 80, 3), np.uint8), 110)
        detector.face_library.recognize.assert_not_called()
        detector._apply_face_result.assert_not_called()
        self.assertEqual(detector.person_states[1]["face_reason"], "too_dark")

    def test_best_recent_frame_survives_bad_frame_but_is_consumed_once(self):
        detector, run = self.detector()
        good = textured_face()
        run(good, 111)  # Global cooldown: save the good frame.
        run(np.zeros_like(good), 112)
        detector.face_library.recognize.assert_called_once()
        np.testing.assert_array_equal(detector.face_library.recognize.call_args[0][0], good)
        self.assertIsNone(detector.person_states[1]["best_face_crop"])
        run(np.zeros_like(good), 116)
        self.assertEqual(detector.face_library.recognize.call_count, 1)

    def test_expired_best_frame_cannot_bypass_current_quality_failure(self):
        detector, run = self.detector()
        run(textured_face(), 111)
        run(np.zeros((80, 80, 3), np.uint8), 114)
        detector.face_library.recognize.assert_not_called()


if __name__ == "__main__":
    unittest.main()
