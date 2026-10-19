"""Face-path regressions with real NumPy; ACL/OpenCV are isolated substitutes."""

import ast
from collections import deque
import os
from pathlib import Path
import tempfile
import threading
import time
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import numpy as np

from test_runtime import ROOT, load_definition


def face_namespace():
    namespace = {"np": np, "os": os, "threading": threading, "time": time,
                 "deque": deque, "KNOWN_FACE_DIR": ".", "cv2": SimpleNamespace(),
                 "ensure_dir": lambda path: Path(path).mkdir(parents=True, exist_ok=True),
                 "print": lambda *args: None, "SAVE_FACE_RECOG_INPUTS": False,
                 "ACL_MODEL_EXEC_LOCK": threading.Lock()}
    tree = ast.parse((ROOT / "src/ascend_main_other.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, TypeError):
            if isinstance(node.value, ast.Name) and node.value.id in namespace:
                value = namespace[node.value.id]
            else:
                continue
        for target in node.targets:
            if isinstance(target, ast.Name):
                namespace[target.id] = value
    return namespace


class CropGateTests(unittest.TestCase):
    def run_candidate(self, score=0.9, box=None, front=False, pose_crop=None,
                      pose_quality=None, detector_enabled=True, reload_during_match=False):
        namespace = face_namespace()
        namespace["is_front_face_candidate"] = lambda kpts: front
        namespace["extract_face_crop"] = lambda *args: pose_crop
        quality = load_definition("ascend_main_other.py", "score_face_crop", namespace)
        namespace["score_face_crop"] = (lambda *args: pose_quality) if pose_quality is not None else quality
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                                 "_maybe_recognize_face")
        library = SimpleNamespace(revision=1, _state_lock=threading.RLock(), _log_diag=Mock())
        def recognize(image):
            if reload_during_match:
                library.revision += 1
            return "known:Yang", 0.8
        library.recognize = Mock(side_effect=recognize)
        detector = SimpleNamespace(
            face_library_loaded=True, face_detector=SimpleNamespace(enabled=detector_enabled),
            face_library=library, person_state_lock=threading.Lock(), face_global_last_check=0,
            person_states={1: {"first_seen": 100, "face_label": "pending"}}, _face_rec_ms=0,
            _get_face_detection_for_person=lambda body: {"box": box or [20, 20, 100, 100], "score": score},
            _apply_face_result=Mock(), _sync_face_library_revision=Mock())
        method(detector, np.zeros((200, 200, 3), np.uint8), 1,
               dict(detector.person_states[1]), {"box": [0, 0, 180, 180], "kpts": [(0, 0, 0)] * 17}, 110)
        return detector

    def test_valid_detector_probability_reaches_recognizer(self):
        detector = self.run_candidate()
        detector.face_library.recognize.assert_called_once()
        detector._apply_face_result.assert_called_once_with(1, "known:Yang", 0.8)

    def test_low_detector_probability_and_tiny_crop_are_rejected(self):
        for kwargs in ({"score": 0.4}, {"score": float("nan")}, {"score": float("inf")},
                       {"box": [20, 20, 30, 30]}):
            with self.subTest(kwargs=kwargs):
                detector = self.run_candidate(**kwargs)
                detector.face_library.recognize.assert_not_called()

    def test_pose_only_keeps_its_separate_quality_and_frontal_gate(self):
        image = np.zeros((80, 80, 3), np.uint8)
        for front, quality, accepted in ((True, 1.2, True), (True, 0.9, False), (False, 1.2, False)):
            with self.subTest(front=front, quality=quality):
                detector = self.run_candidate(front=front, pose_crop=image, pose_quality=quality,
                                              detector_enabled=False)
                self.assertEqual(detector.face_library.recognize.call_count, int(accepted))

    def test_result_from_replaced_library_is_not_applied(self):
        detector = self.run_candidate(reload_during_match=True)
        detector._apply_face_result.assert_not_called()
        detector._sync_face_library_revision.assert_called_once()


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.namespace = face_namespace()
        self.Library = load_definition("ascend_main_other.py", "FaceLibrary", self.namespace)

    def arc_library(self, embedding=None):
        value = np.array([1, 0], np.float32) if embedding is None else embedding
        arcface = SimpleNamespace(enabled=True, infer=Mock(return_value=value))
        library = self.Library(recognizer=arcface)
        library.embedding_backend = "arcface"
        library.enabled = True
        library._extract_face_gray = Mock(side_effect=AssertionError("CPU gray must not run on ACL path"))
        library._extract_face_bgr = Mock(side_effect=AssertionError("CPU detection must not run on ACL path"))
        library.entries = [{"name": "Yang", "embedding": np.array([0.8, 0.6], np.float32)}]
        library.centroids = {"Yang": np.array([0.8, 0.6], np.float32)}
        return library

    def test_arcface_fast_path_skips_cpu_processing(self):
        library = self.arc_library()
        label, score = library.recognize(np.zeros((80, 80, 3), np.uint8))
        self.assertEqual(label, "known:Yang")
        self.assertAlmostEqual(score, 0.8)
        library._extract_face_gray.assert_not_called()
        library._extract_face_bgr.assert_not_called()

    def test_name_comes_from_winning_sample_not_a_different_centroid(self):
        library = self.arc_library()
        library.entries.append({"name": "Other", "embedding": np.array([0.6, 0.8], np.float32)})
        library.centroids = {"Yang": np.array([0.1, 0.995], np.float32),
                             "Other": np.array([0.95, 0.312], np.float32)}
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8))[0], "known:Yang")

    def test_low_margin_and_invalid_vectors_do_not_become_known(self):
        library = self.arc_library()
        library.entries.append({"name": "Other", "embedding": np.array([0.76, 0.65], np.float32)})
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8))[0], "unknown")
        for vector in (np.zeros(2), np.array([np.nan, 1]), np.array([np.inf, 1])):
            with self.subTest(vector=vector):
                invalid = self.arc_library(vector)
                self.assertEqual(invalid.recognize(np.zeros((80, 80, 3), np.uint8)), ("unknown", None))

    def test_dimension_mismatch_is_unavailable_not_stranger_evidence(self):
        library = self.arc_library(np.array([1, 0, 0], np.float32))
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8)), ("unknown", None))

    def test_cpu_only_library_keeps_old_return_contract(self):
        library = self.Library()
        library.enabled = True
        library.embedding_backend = "cpu"
        library.centroids = {"Yang": np.array([1, 0, 0], np.float32)}
        library._extract_face_gray = Mock(return_value=np.zeros((128, 128), np.uint8))
        library._extract_face_bgr = Mock(return_value=np.zeros((80, 80, 3), np.uint8))
        self.namespace["build_face_embedding_from_gray"] = lambda image: np.array([1, 0, 0], np.float32)
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8)), ("known:Yang", 0.0))

    def test_missing_gray_does_not_switch_to_different_cpu_feature_dimension(self):
        library = self.Library()
        library.enabled, library.embedding_backend = True, "cpu"
        library.centroids = {"Yang": np.array([1, 0, 0], np.float32)}
        library._extract_face_gray = lambda image: None
        library._extract_face_bgr = lambda image: image
        self.namespace["build_face_embedding"] = Mock(side_effect=AssertionError("incompatible CPU format"))
        self.assertEqual(library.recognize(np.zeros((12, 12, 3), np.uint8)), ("unknown", None))
        self.namespace["build_face_embedding"].assert_not_called()

    def test_cpu_gallery_skips_sample_without_gray_instead_of_mixing_formats(self):
        with tempfile.TemporaryDirectory() as directory:
            person = Path(directory) / "Yang"
            person.mkdir()
            for name in ("one.jpg", "two.jpg"):
                (person / name).write_bytes(b"fake image")
            self.namespace["cv2"] = SimpleNamespace(imread=lambda path: np.zeros((80, 80, 3), np.uint8))
            self.namespace["build_face_embedding_from_gray"] = lambda image: np.array([1, 0, 0], np.float32)
            self.namespace["build_face_embedding"] = Mock(side_effect=AssertionError("incompatible CPU format"))
            library = self.Library(directory)
            with patch.object(self.Library, "_extract_face_gray", side_effect=[None, np.zeros((128, 128), np.uint8)]), \
                 patch.object(self.Library, "_extract_face_bgr", side_effect=lambda image: image):
                library.load()
            self.assertEqual(len(library.entries), 1)
            self.namespace["build_face_embedding"].assert_not_called()

    def test_failed_reload_preserves_complete_old_library(self):
        library = self.arc_library()
        old_entries, old_centroids = library.entries, library.centroids
        with patch.object(self.Library, "_load", side_effect=OSError("unreadable directory")):
            with self.assertRaises(OSError):
                library.load()
        self.assertIs(library.entries, old_entries)
        self.assertIs(library.centroids, old_centroids)
        self.assertEqual(library.revision, 0)

    def test_recognition_uses_old_snapshot_while_replacement_is_building(self):
        library = self.arc_library()
        started, release = threading.Event(), threading.Event()
        failures = []
        def build(staged):
            started.set()
            if not release.wait(3):
                raise TimeoutError("test build did not resume")
            staged.entries = [{"name": "New", "embedding": np.array([1, 0], np.float32)}]
            staged.centroids = {"New": np.array([1, 0], np.float32)}
            staged.enabled, staged.embedding_backend = True, "arcface"
        def reload():
            try:
                library.load()
            except Exception as exc:
                failures.append(exc)
        with patch.object(self.Library, "_load", build):
            worker = threading.Thread(target=reload)
            worker.start()
            try:
                self.assertTrue(started.wait(1))
                self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8))[0], "known:Yang")
            finally:
                release.set()
                worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(library.revision, 1)
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8))[0], "known:New")

    def test_arcface_load_failure_rebuilds_all_samples_in_one_cpu_space(self):
        with tempfile.TemporaryDirectory() as directory:
            person = Path(directory) / "Yang"
            person.mkdir()
            for name in ("one.jpg", "two.jpg"):
                (person / name).write_bytes(b"fake image")
            arcface = SimpleNamespace(enabled=True)
            calls = []
            def infer(image):
                calls.append(image)
                if len(calls) == 2:
                    arcface.enabled = False
                    return None
                return np.array([1, 0], np.float32)
            arcface.infer = infer
            self.namespace["cv2"] = SimpleNamespace(imread=lambda path: np.zeros((80, 80, 3), np.uint8))
            self.namespace["build_face_embedding_from_gray"] = lambda image: np.array([1, 0, 0], np.float32)
            library = self.Library(directory, arcface)
            with patch.object(self.Library, "_extract_face_gray", return_value=np.zeros((128, 128), np.uint8)), \
                 patch.object(self.Library, "_extract_face_bgr", side_effect=lambda image: image):
                library.load()
            self.assertEqual(library.embedding_backend, "cpu")
            self.assertEqual([entry["embedding"].size for entry in library.entries], [3, 3])
            self.assertEqual(library.centroids["Yang"].size, 3)

    def test_live_model_failure_rebuilds_before_using_cpu_features(self):
        library = self.arc_library()
        def fail(image):
            library.arcface.enabled = False
            return None
        library.arcface.infer.side_effect = fail
        def load_cpu():
            library.embedding_backend = "cpu"
            library.centroids = {"Yang": np.array([1, 0, 0], np.float32)}
            library._extract_face_gray = lambda image: np.zeros((128, 128), np.uint8)
            library._extract_face_bgr = lambda image: image
            library.revision += 1
        library.load = Mock(side_effect=load_cpu)
        self.namespace["build_face_embedding_from_gray"] = lambda image: np.array([1, 0, 0], np.float32)
        self.assertEqual(library.recognize(np.zeros((80, 80, 3), np.uint8)), ("known:Yang", 0.0))
        library.load.assert_called_once()


class IdentityRevisionTests(unittest.TestCase):
    def test_cpu_distances_do_not_use_arcface_strong_similarity_shortcut(self):
        namespace = face_namespace()
        apply = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                                "_apply_face_result")
        for backend, enabled, score, immediate in (("cpu", False, 60.0, False),
                                                   ("cpu", True, 0.6, False),
                                                   ("arcface", True, 0.8, True)):
            with self.subTest(backend=backend, enabled=enabled):
                state = {"face_label": "pending"}
                detector = SimpleNamespace(person_state_lock=threading.Lock(), person_states={1: state},
                    face_library=SimpleNamespace(embedding_backend=backend),
                    face_recognizer=SimpleNamespace(enabled=enabled))
                apply(detector, 1, "known:Yang", score)
                self.assertEqual(state["face_label"], "known:Yang" if immediate else "pending")
                apply(detector, 1, "known:Yang", score)
                self.assertEqual(state["face_label"], "known:Yang")

    def test_reload_invalidates_face_identity_but_keeps_body_and_fall_state(self):
        namespace = face_namespace()
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                                 "_sync_face_library_revision")
        state = {"face_label": "known:Old", "face_score": 0.8, "fall_confirmed": True,
                 "box": [1, 2, 3, 4], "best_face_crop": object()}
        detector = SimpleNamespace(face_library=SimpleNamespace(revision=2), _face_library_revision=1,
                                   person_state_lock=threading.Lock(), person_states={1: state},
                                   recent_known_tracks=deque([{"face_label": "known:Old"}]),
                                   face_global_last_check=100)
        method(detector)
        self.assertEqual(state["face_label"], "pending")
        self.assertIsNone(state["face_score"])
        self.assertTrue(state["fall_confirmed"])
        self.assertEqual(state["box"], [1, 2, 3, 4])
        self.assertFalse(detector.recent_known_tracks)
        state["face_label"] = "known:New"
        method(detector)
        self.assertEqual(state["face_label"], "known:New")


class ArcFaceOutputTests(unittest.TestCase):
    def test_invalid_model_outputs_try_compatible_layout_then_disable(self):
        namespace = face_namespace()
        namespace["cv2"] = SimpleNamespace(resize=lambda image, size, interpolation: image,
            cvtColor=lambda image, code: image[..., ::-1], INTER_LINEAR=1, COLOR_BGR2RGB=1)
        recognizer_class = load_definition("ascend_main_other.py", "ArcFaceRecognizerACL", namespace)
        for output in (np.zeros(4), np.array([np.nan]), np.array([np.inf])):
            with self.subTest(output=output):
                recognizer = recognizer_class("face_rec_mbf.om")
                recognizer.enabled = True
                recognizer.model = SimpleNamespace(execute=Mock(return_value=[output]))
                self.assertIsNone(recognizer.infer(np.ones((112, 112, 3), np.uint8)))
                self.assertFalse(recognizer.enabled)
                self.assertEqual(recognizer.model.execute.call_count, 2)


if __name__ == "__main__":
    unittest.main()
