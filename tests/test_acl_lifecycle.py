"""Offline ordering checks supplement, but do not replace, board ACL execution."""

import threading
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import Mock

import numpy as np

from test_face_recognition import face_namespace
from test_runtime import load_definition


class AclLifecycleTests(unittest.TestCase):
    def detector(self, events):
        namespace = face_namespace()
        method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace, "release_acl")
        class Resource:
            def __del__(self):
                events.append("context_finalize")
        def model(name):
            return SimpleNamespace(destroy=lambda: events.append(name))
        detector = SimpleNamespace(_acl_resource=Resource(), _acl_owner_thread=threading.get_ident(),
            face_library=SimpleNamespace(_load_lock=threading.Lock(), _state_lock=threading.RLock()),
            face_recognizer=SimpleNamespace(model=model("recognizer"), enabled=True, _acl_context=1),
            face_detector=SimpleNamespace(model=model("face_detector"), enabled=True),
            model=model("pose"), dvpp=model("dvpp"))
        detector.release_acl = MethodType(method, detector)
        return detector

    def test_models_and_dvpp_destroy_before_context_and_cleanup_is_idempotent(self):
        events = []
        detector = self.detector(events)
        detector.release_acl()
        self.assertEqual(events, ["recognizer", "face_detector", "pose", "dvpp", "context_finalize"])
        detector.release_acl()
        self.assertEqual(len(events), 5)
        self.assertFalse(detector.face_recognizer.enabled)
        self.assertFalse(detector.face_detector.enabled)

    def test_wrong_thread_does_not_destroy_live_resources(self):
        events = []
        detector = self.detector(events)
        detector._acl_owner_thread = -1
        with self.assertRaises(RuntimeError):
            detector.release_acl()
        self.assertEqual(events, [])
        detector._acl_owner_thread = threading.get_ident()
        detector.release_acl()

    def test_face_inference_binds_context_on_api_thread(self):
        namespace = face_namespace()
        namespace["cv2"] = SimpleNamespace(resize=lambda image, size, interpolation: image,
            cvtColor=lambda image, code: image[..., ::-1], INTER_LINEAR=1, COLOR_BGR2RGB=1)
        bind = Mock(return_value=0)
        namespace["acl"] = SimpleNamespace(rt=SimpleNamespace(set_context=bind))
        recognizer_type = load_definition("ascend_main_other.py", "ArcFaceRecognizerACL", namespace)
        recognizer = recognizer_type("face_rec_mbf.om")
        recognizer.enabled = True
        recognizer._acl_context = 123
        recognizer._acl_owner_thread = -1
        recognizer.model = SimpleNamespace(execute=Mock(return_value=[np.ones(512, np.float32)]))
        self.assertIsNotNone(recognizer.infer(np.ones((112, 112, 3), np.uint8)))
        bind.assert_called_once_with(123)


if __name__ == "__main__":
    unittest.main()
