"""Registration policy and API flow checks with synthetic images/features only."""

from collections import deque
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
import time
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

import numpy as np

from test_face_recognition import face_namespace
from test_runtime import load_definition
from guardian_runtime import StationaryTimer


def policy_detector(backend="arcface", sample_count=1, identities=1):
    namespace = face_namespace()
    method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                             "_apply_face_result")
    library = SimpleNamespace(embedding_backend=backend, revision=1,
                              registered_sample_count=sample_count, enabled=sample_count > 0,
                              centroids={str(i): None for i in range(identities)})
    detector = SimpleNamespace(person_states={1: {"face_label": "pending", "first_seen": 100}},
        person_state_lock=threading.Lock(), face_library=library,
        face_recognizer=SimpleNamespace(enabled=backend == "arcface"))
    detector._apply_face_result = MethodType(method, detector)
    return detector


class RegistrationDecisionTests(unittest.TestCase):
    def test_single_and_multiple_identity_libraries_confirm_stable_nonmatch(self):
        for identities in (1, 2):
            for score in (0.20, -0.20):
                with self.subTest(identities=identities, score=score):
                    detector = policy_detector(identities=identities)
                    for count in range(3):
                        detector._apply_face_result(1, "unknown", score)
                        self.assertEqual(detector.person_states[1]["face_label"],
                                         "stranger" if count == 2 else "pending")

    def test_cpu_uses_distance_and_actual_library_backend(self):
        detector = policy_detector(backend="cpu")
        detector.face_recognizer.enabled = True
        for _ in range(3):
            detector._apply_face_result(1, "unknown", 0.65)
        self.assertEqual(detector.person_states[1]["face_label"], "stranger")

    def test_ambiguous_or_unavailable_scores_are_not_stranger_evidence(self):
        for backend, score in (("arcface", 0.45), ("arcface", None), ("arcface", float("nan")),
                               ("arcface", float("inf")), ("arcface", -999),
                               ("cpu", 0.62), ("cpu", None), ("cpu", 999), ("cpu", -0.2)):
            with self.subTest(backend=backend, score=score):
                detector = policy_detector(backend=backend)
                for _ in range(4):
                    detector._apply_face_result(1, "unknown", score)
                self.assertEqual(detector.person_states[1]["face_label"], "pending")

    def test_successfully_loaded_empty_gallery_marks_valid_faces_unregistered(self):
        detector = policy_detector(sample_count=0, identities=0)
        for _ in range(3):
            detector._apply_face_result(1, "unregistered", None)
        self.assertEqual(detector.person_states[1]["face_label"], "stranger")
        self.assertIsNone(detector.person_states[1]["face_score"])

    def test_never_loaded_or_unusable_gallery_does_not_mean_nobody_registered(self):
        for sample_count, revision in ((0, 0), (2, 1)):
            with self.subTest(sample_count=sample_count, revision=revision):
                detector = policy_detector(sample_count=sample_count, identities=0)
                detector.face_library.revision = revision
                detector.face_library.enabled = False
                for _ in range(3):
                    detector._apply_face_result(1, "unregistered", None)
                self.assertEqual(detector.person_states[1]["face_label"], "pending")

    def test_clear_repeated_nonmatch_can_replace_old_known_identity(self):
        detector = policy_detector()
        state = detector.person_states[1]
        state.update(face_label="known:Yang", face_score=0.8)
        for index in range(3):
            detector._apply_face_result(1, "unknown", 0.2)
            if index < 2:
                self.assertEqual(state["face_label"], "pending")
                self.assertEqual(state["face_score"], 0.2)
        self.assertEqual(state["face_label"], "stranger")
        detector._apply_face_result(1, "known:Yang", 0.8)
        self.assertEqual(state["face_label"], "known:Yang")

    def test_unknown_does_not_create_enrollment_or_trigger_name_assignment(self):
        detector = policy_detector()
        for _ in range(5):
            detector._apply_face_result(1, "unknown", 0.1)
        self.assertEqual(detector.person_states[1]["face_label"], "stranger")
        self.assertEqual(detector.face_library.registered_sample_count, 1)


class TrackAuthenticationTests(unittest.TestCase):
    def test_new_person_gets_recognition_turn_without_changing_alert_order(self):
        namespace = face_namespace()
        namespace["is_person_fallen"] = lambda *args: False
        namespace["analyze_fall_motion"] = lambda *args: False
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace, "_build_alerts")
        states = {1: {"face_label": "known:Yang", "face_score": 0.8, "last_face_check": 100},
                  2: {"face_label": "pending", "last_face_check": 0, "first_seen": 80}}
        for state in states.values():
            state["fall_confirmed"] = False
        detection = {"box": [0, 0, 100, 200], "kpts": [(0, 0, 0)] * 17}
        calls = []
        detector = SimpleNamespace(person_states=states, person_state_lock=threading.Lock(),
            _sync_face_library_revision=lambda: None, _ensure_face_library_loaded=lambda *args: None,
            _refresh_face_det_cache=lambda *args, **kwargs: None,
            _assign_person_ids=lambda *args: [(i, dict(state), detection) for i, state in states.items()],
            _update_face_det_debug=lambda *args: None,
            _maybe_recognize_face=lambda frame, person_id, *args: calls.append(person_id),
            _is_long_sit_state=lambda *args: False, _maybe_trigger_vlm_events=lambda *args: None)
        alerts = method(detector, SimpleNamespace(shape=(480, 640, 3)), [], 110)
        self.assertEqual(calls, [2, 1])
        self.assertEqual([alert["id"] for alert in alerts], [1, 2])
        self.assertEqual(alerts[1]["face_label"], "stranger")
        self.assertEqual(alerts[1]["face_reason"], "timeout")

    def detector(self):
        namespace = face_namespace()
        namespace["StationaryTimer"] = StationaryTimer
        for name in ("compute_iou", "box_center", "box_diag"):
            load_definition("ascend_main_other.py", name, namespace)
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace,
                                 "_assign_person_ids")
        detector = SimpleNamespace(person_states={}, next_person_id=1,
            person_state_lock=threading.Lock(), _prune_person_states=lambda now: None,
            _recover_active_known_track=Mock(return_value={"person_id": 99, "face_label": "known:Old"}),
            _recover_recent_known_track=Mock(return_value={"face_label": "known:Old", "face_score": 0.9}))
        detector.assign = MethodType(method, detector)
        return detector

    def test_new_body_near_previous_known_person_does_not_inherit_name(self):
        detector = self.detector()
        result = detector.assign([{"box": [0, 0, 100, 200]}], 110)
        self.assertEqual(result[0][1]["face_label"], "pending")
        detector._recover_active_known_track.assert_not_called()
        detector._recover_recent_known_track.assert_not_called()

    def test_weak_track_reuse_clears_known_identity_and_votes(self):
        detector = self.detector()
        detector.person_states[1] = {"box": [0, 0, 100, 200], "face_label": "known:Yang",
            "face_score": 0.8, "face_vote_history": deque([("known:Yang", 0.8)])}
        result = detector.assign([{"box": [60, 0, 160, 200]}], 110)
        self.assertEqual(result[0][0], 1)
        self.assertEqual(result[0][1]["face_label"], "pending")
        self.assertFalse(result[0][1]["face_vote_history"])

    def test_strong_track_continuity_keeps_last_verified_name(self):
        detector = self.detector()
        detector.person_states[1] = {"box": [0, 0, 100, 200], "face_label": "known:Yang", "face_score": 0.8}
        result = detector.assign([{"box": [2, 0, 102, 200]}], 110)
        self.assertEqual(result[0][1]["face_label"], "known:Yang")


class GalleryAvailabilityTests(unittest.TestCase):
    def test_loaded_empty_and_unusable_samples_have_different_results(self):
        namespace = face_namespace()
        namespace["cv2"] = SimpleNamespace(imread=lambda path: None)
        library_class = load_definition("ascend_main_other.py", "FaceLibrary", namespace)
        with tempfile.TemporaryDirectory() as directory:
            library = library_class(directory)
            self.assertEqual(library.recognize(np.zeros((80, 80, 3))), ("unknown", None))
            library.load()
            self.assertEqual(library.recognize(np.zeros((80, 80, 3))), ("unregistered", None))
            self.assertEqual(library.recognize(None), ("unknown", None))
            self.assertEqual(library.recognize(np.zeros((12, 12, 3))), ("unknown", None))
            person = Path(directory) / "Yang"
            person.mkdir()
            (person / "invalid.jpg").write_bytes(b"invalid")
            library.load()
            self.assertEqual(library.registered_sample_count, 1)
            self.assertEqual(library.recognize(np.zeros((80, 80, 3))), ("unknown", None))


class ApiRegistrationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_upload_match_nonmatch_and_delete_flow(self):
        namespace = face_namespace()
        def image(value):
            return np.full((80, 80, 3), value, np.uint8)
        cv = SimpleNamespace(IMREAD_COLOR=1,
            imread=lambda path: image(Path(path).read_bytes()[0]),
            imdecode=lambda data, flag: image(int(data[0])),
            imencode=lambda ext, frame: (True, np.array([frame[0, 0, 0]], np.uint8)))
        namespace["cv2"] = cv
        library_class = load_definition("ascend_main_other.py", "FaceLibrary", namespace)
        arcface = SimpleNamespace(enabled=True,
            infer=lambda frame: np.eye(3, dtype=np.float32)[min(int(frame[0, 0, 0]), 3) - 1])
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(library_class, "_extract_face_gray", return_value=np.zeros((128, 128), np.uint8)):
            library = library_class(str(Path(directory) / "known_faces"), arcface)
            library.load()
            detector = policy_detector()
            detector.face_library = library
            detector.person_states[2] = {"face_label": "pending", "first_seen": 100}
            api = {"os": os, "np": np, "cv2": cv, "time": time, "uuid": uuid, "shutil": shutil,
                "_sqlite3": sqlite3, "system_detector": detector,
                "_FACE_DIR": library.library_dir, "_DB_PATH": str(Path(directory) / "faces.db"),
                "_FACE_UPLOAD_MAX_BYTES": 8 * 1024 * 1024,
                "_FACE_ENROLL_HINT": "上传不同方向的照片，有助于加快识别并提高精度；照片数量不作要求，一张也可登记。",
                "UploadFile": object, "Form": lambda *args: None, "File": lambda *args: None,
                "JSONResponse": lambda result: result, "print": lambda *args: None}
            class HTTPException(Exception):
                def __init__(self, status_code, detail):
                    self.status_code, self.detail = status_code, detail
            api["HTTPException"] = HTTPException
            for name in ("_validate_face_fields", "_face_sample_paths", "_connect_face_db", "_db_get_face_name", "_db_log_face",
                         "_db_delete_face", "_db_list_faces", "_reload_face_library_for_api",
                         "face_enroll", "face_delete"):
                load_definition("ascend_board_server.py", name, api)
            async def read(limit):
                return b"\x01"
            result = await api["face_enroll"]("Yang", "user_yang", SimpleNamespace(read=read))
            self.assertEqual(result["recognition_status"], "ready")
            self.assertEqual(result["photo_count"], 1)
            self.assertIn("一张也可登记", result["hint"])
            self.assertEqual(api["_db_list_faces"]()[0]["name"], "Yang")
            async def read_second(limit):
                return b"\x02"
            result = await api["face_enroll"]("Yang", "user_yang", SimpleNamespace(read=read_second))
            self.assertEqual(result["photo_count"], 2)
            self.assertEqual(api["_db_list_faces"]()[0]["photo_count"], 2)
            self.assertEqual(len(library.entries), 2)
            label, score = library.recognize(image(1))
            detector._apply_face_result(1, label, score)
            self.assertEqual(detector.person_states[1]["face_label"], "known:Yang")
            for _ in range(3):
                label, score = library.recognize(image(3))
                detector._apply_face_result(2, label, score)
            self.assertEqual(detector.person_states[2]["face_label"], "stranger")
            deleted = await api["face_delete"]("user_yang")
            self.assertEqual(deleted["recognition_status"], "ready")
            self.assertEqual(api["_db_list_faces"](), [])
            self.assertEqual(library.registered_sample_count, 0)
            for _ in range(3):
                label, score = library.recognize(image(1))
                detector._apply_face_result(1, label, score)
            self.assertEqual(detector.person_states[1]["face_label"], "stranger")

    async def test_reload_status_distinguishes_failure_unusable_and_offline(self):
        library = SimpleNamespace(load=Mock(), _state_lock=threading.RLock(), entries=[])
        namespace = {"system_detector": SimpleNamespace(face_library=library), "print": lambda *args: None}
        reload_library = load_definition("ascend_board_server.py", "_reload_face_library_for_api", namespace)
        self.assertEqual(reload_library("sample.jpg"), "photo_unusable")
        library.load.side_effect = OSError("failed")
        self.assertEqual(reload_library("sample.jpg"), "reload_failed")
        namespace["system_detector"] = None
        self.assertEqual(reload_library("sample.jpg"), "service_offline")


if __name__ == "__main__":
    unittest.main()
