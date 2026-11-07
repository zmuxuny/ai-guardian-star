"""Side-view regressions use synthetic pixels/vectors, never real identities."""
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import numpy as np

from test_face_policy import policy_detector
import test_face_recognition as face_tests
import test_face_quality as quality_tests
from guardian_face_quality import expire_face_wait


class SideViewDecisionTests(unittest.TestCase):
    def test_repeated_profile_nonmatches_never_vote_a_person_into_stranger(self):
        detector = policy_detector()
        for _ in range(6):
            detector._apply_face_result(1, 'unknown', 0.1, allow_stranger=False)
        state = detector.person_states[1]
        self.assertEqual(state['face_label'], 'pending')
        self.assertEqual(state['face_reason'], 'pose_unverified')
        self.assertEqual(len(state['face_vote_history']), 0)

    def test_profile_interrupts_old_frontal_nonmatch_votes(self):
        detector = policy_detector()
        for _ in range(2):
            detector._apply_face_result(1, 'unknown', 0.1)
        detector._apply_face_result(1, 'unknown', 0.1, allow_stranger=False)
        detector._apply_face_result(1, 'unknown', 0.1)
        self.assertEqual(detector.person_states[1]['face_label'], 'pending')

    def test_profile_still_accepts_a_genuine_match(self):
        detector = policy_detector()
        detector._apply_face_result(1, 'known:Yang', 0.8, allow_stranger=False)
        self.assertEqual(detector.person_states[1]['face_label'], 'known:Yang')

    def test_profile_does_not_carry_an_old_identity_without_match(self):
        detector = policy_detector()
        detector.person_states[1].update(face_label='known:Yang', face_score=0.8)
        detector._apply_face_result(1, 'unknown', 0.1, allow_stranger=False)
        self.assertEqual(detector.person_states[1]['face_label'], 'pending')

    def test_a_good_frontal_nonmatch_still_confirms_stranger(self):
        detector = policy_detector()
        for _ in range(3):
            detector._apply_face_result(1, 'unknown', 0.1)
        self.assertEqual(detector.person_states[1]['face_label'], 'stranger')

    def test_new_frontal_evidence_replaces_timeout_with_its_actual_reason(self):
        detector = policy_detector()
        state = detector.person_states[1]
        expire_face_wait(state, 1000)
        for _ in range(3):
            detector._apply_face_result(1, 'unknown', 0.1)
        self.assertEqual(state['face_label'], 'stranger')
        self.assertEqual(state['face_reason'], 'unmatched')
        self.assertFalse(state['face_timed_out'])

    def test_expiry_never_turns_missing_side_face_into_stranger(self):
        state = {'first_seen':100,'face_label':'pending','face_quality_reason':'no_face'}
        self.assertTrue(expire_face_wait(state,1000))
        self.assertEqual(state['face_label'],'pending')
        self.assertEqual(state['face_reason'],'timeout')
        self.assertTrue(expire_face_wait(state,1001))
        self.assertEqual(state['face_label'],'pending')

    def test_confirmed_stranger_is_not_erased_by_old_timeout_flag(self):
        state = {'face_label':'stranger','face_reason':'unmatched','face_timed_out':True}
        self.assertFalse(expire_face_wait(state,1000))
        self.assertEqual(state['face_reason'],'unmatched')

    def test_detector_profile_crop_reaches_matching_but_not_stranger_voting(self):
        detector = face_tests.CropGateTests().run_candidate(front=False)
        detector._apply_face_result.assert_called_once_with(1,'known:Yang',0.8,allow_stranger=False)


class SideViewGalleryTests(unittest.TestCase):
    def fixture(self, cascade=None):
        fixture = face_tests.LibraryTests()
        fixture.setUp()
        library = fixture.Library()
        library.face_cascade = cascade
        library._ensure_detector = lambda: None
        fixture.namespace['cv2'] = SimpleNamespace(COLOR_BGR2GRAY=0,
            cvtColor=lambda image, code: image[:, :, 0], equalizeHist=lambda image: image)
        return library

    def test_tight_detector_scale_and_mirrored_real_photo_are_both_retained(self):
        image = np.arange(100 * 100 * 3, dtype=np.uint8).reshape(100,100,3)
        before = image.copy()
        cascade = SimpleNamespace(detectMultiScale=lambda *args, **kwargs: [[20,10,40,50]])
        views = self.fixture(cascade)._arcface_gallery_variants(image)
        tight = image[10:60,20:60]
        self.assertTrue(any(np.array_equal(view,tight) for view in views))
        self.assertTrue(any(np.array_equal(view,tight[:,::-1]) for view in views))
        self.assertTrue(all(view.flags.c_contiguous for view in views))
        np.testing.assert_array_equal(image,before)

    def test_missing_frontal_haar_detector_still_preserves_uploaded_side_photo(self):
        image = np.arange(40 * 40 * 3,dtype=np.uint8).reshape(40,40,3)
        views = self.fixture()._arcface_gallery_variants(image)
        self.assertEqual(len(views),2)
        np.testing.assert_array_equal(views[0],image)
        np.testing.assert_array_equal(views[1],image[:,::-1])

    def test_identical_mirror_is_not_an_extra_enrollment_sample(self):
        image = np.zeros((40,40,3),np.uint8)
        self.assertEqual(len(self.fixture()._arcface_gallery_variants(image)),1)

    def test_cached_crop_uses_its_own_pose_not_the_next_frames_pose(self):
        for first_front in (False,True):
            with self.subTest(first_front=first_front):
                namespace = face_tests.face_namespace()
                with patch.object(quality_tests,'face_namespace',return_value=namespace):
                    detector, run = quality_tests.QualityGateIntegrationTests().detector()
                namespace['is_front_face_candidate'] = lambda *args: first_front
                good = quality_tests.textured_face()
                run(good,111)  # still in global cooldown: caches the current crop
                namespace['is_front_face_candidate'] = lambda *args: not first_front
                run(np.zeros_like(good),112)  # consumes the cached crop
                if first_front:
                    detector._apply_face_result.assert_called_once_with(1,'unknown',0.2)
                else:
                    detector._apply_face_result.assert_called_once_with(1,'unknown',0.2,allow_stranger=False)


if __name__ == '__main__':
    unittest.main()
