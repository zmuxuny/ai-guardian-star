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
import guardian_face_quality as quality_policy


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
        with patch.dict(os.environ, {"FACE_TEST_SETTING": "nan"}):
            self.assertEqual(setting("FACE_TEST_SETTING", 20, 80, 600), 80)


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

    def test_known_person_losing_pose_landmarks_gets_new_wait_window(self):
        detector, run = self.detector()
        state = detector.person_states[1]
        state.update(first_seen=1, face_label="known:Yang", face_wait_started=None)
        detector.face_detector.enabled = False
        run(textured_face(), 110)
        self.assertEqual(state["face_label"], "pending")
        self.assertEqual(state["face_wait_started"], 110)
        self.assertFalse(quality_policy.expire_face_wait(state, 139))
        self.assertTrue(quality_policy.expire_face_wait(state, 140))


class RecognitionTimeoutTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("WAIT_TIMEOUT_BASE", 20), ("WAIT_TIMEOUT_MAX", 60)):
            handle = patch.object(quality_policy, name, value)
            handle.start()
            self.addCleanup(handle.stop)

    def test_default_deadline_marks_stranger_with_explicit_timeout_reason(self):
        state = {"first_seen": 100, "face_label": "pending"}
        self.assertFalse(quality_policy.expire_face_wait(state, 119))
        self.assertTrue(quality_policy.expire_face_wait(state, 120))
        self.assertEqual(state["face_label"], "stranger")
        self.assertEqual(state["face_reason"], "timeout")
        self.assertIsNone(state["face_score"])
        self.assertTrue(state["face_timed_out"])

    def test_congestion_and_poor_quality_extend_wait_but_have_a_cap(self):
        state = {"first_seen": 100, "face_label": "pending", "face_quality_reason": "too_dark"}
        self.assertFalse(quality_policy.expire_face_wait(state, 130, 3))
        self.assertEqual(state["face_timeout_seconds"], 38)
        self.assertTrue(quality_policy.expire_face_wait(state, 138, 3))
        state = {"first_seen": 100, "face_label": "pending"}
        quality_policy.expire_face_wait(state, 159, 100)
        self.assertEqual(state["face_timeout_seconds"], 60)
        self.assertTrue(quality_policy.expire_face_wait(state, 160, 100))

    def test_expired_state_stays_timeout_when_people_or_quality_change(self):
        state = {"first_seen": 100, "face_label": "pending"}
        quality_policy.expire_face_wait(state, 120)
        state.update(face_reason="ready", face_quality_reason="blurred", face_score=0.2)
        self.assertTrue(quality_policy.expire_face_wait(state, 121, 2))
        self.assertEqual(state["face_reason"], "timeout")
        self.assertEqual(state["face_timeout_seconds"], 20)
        self.assertIsNone(state["face_score"])
        state["face_label"] = "pending"  # e.g. first of two CPU known-candidate votes
        quality_policy.expire_face_wait(state, 122, 20)
        self.assertEqual(state["face_label"], "stranger")

    def test_improving_conditions_do_not_shorten_existing_deadline(self):
        state = {"first_seen": 100, "face_label": "pending", "face_quality_reason": "blurred"}
        quality_policy.expire_face_wait(state, 110, 3)
        state["face_quality_reason"] = "ready"
        self.assertFalse(quality_policy.expire_face_wait(state, 130, 1))
        self.assertEqual(state["face_timeout_seconds"], 38)

    def test_known_identity_never_expires_and_can_replace_previous_timeout(self):
        from test_face_policy import policy_detector
        detector = policy_detector()
        state = detector.person_states[1]
        quality_policy.expire_face_wait(state, 120)
        self.assertTrue(state["face_timed_out"])
        detector._apply_face_result(1, "known:Yang", 0.8)
        self.assertFalse(quality_policy.expire_face_wait(state, 10000))
        self.assertEqual(state["face_label"], "known:Yang")
        self.assertFalse(state["face_timed_out"])
        self.assertIsNone(state["face_wait_started"])

    def test_known_identity_gets_new_wait_window_after_valid_nonmatch(self):
        from test_face_policy import policy_detector
        detector = policy_detector()
        state = detector.person_states[1]
        state.update(face_label="known:Yang", first_seen=1)
        with patch("time.time", return_value=100):
            detector._apply_face_result(1, "unknown", 0.2)
        self.assertFalse(quality_policy.expire_face_wait(state, 119))
        self.assertTrue(quality_policy.expire_face_wait(state, 120))

    def test_evidence_based_stranger_keeps_its_reason(self):
        state = {"first_seen": 100, "face_label": "stranger", "face_reason": "unmatched"}
        self.assertFalse(quality_policy.expire_face_wait(state, 999))
        self.assertEqual(state["face_reason"], "unmatched")


if __name__ == "__main__":
    unittest.main()
