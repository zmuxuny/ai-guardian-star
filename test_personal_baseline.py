"""Offline acceptance for event posture, personal feedback and shadow isolation."""
import copy
import math
import unittest

from src.posture_features import extract_posture, eligible_label, evaluate, histogram_bins


def posture(angle=0, hip=0.6, ratio=0.5, region='room', slot=2):
    return dict(version='posture_v1', valid=True, reason='ok', torso_angle=angle,
                hip_height=hip, aspect_ratio=ratio, region_id=region, time_slot=slot)


def pose_input():
    points = [(150., 100., 0.9)] * 17
    points[5], points[6] = (130., 150., .9), (170., 150., .9)
    points[11], points[12] = (135., 220., .9), (165., 220., .9)
    return [100., 100., 200., 300.], points, (480, 640)


class FeatureTests(unittest.TestCase):
    def test_normalized_scale_and_local_time(self):
        box, points, shape = pose_input()
        first = extract_posture(box, points, shape, 'room', 0)
        scaled = extract_posture([x*2 for x in box], [(x*2,y*2,c) for x,y,c in points],
                                 (960,1280), 'room', 0)
        self.assertEqual(first, scaled)
        self.assertEqual(first, posture())
        self.assertNotIn('kpts', first)

    def test_unreliable_points_edges_invalid_numbers_and_degenerate_torso(self):
        box, points, shape = pose_input()
        for value in (.4, float('nan'), True):
            bad = list(points); bad[5] = (130,150,value)
            self.assertFalse(extract_posture(box,bad,shape,'room',0)['valid'])
        for bad_box in ([0,100,200,300], [100,100,100,300], [100,100,math.inf,300]):
            result = extract_posture(bad_box,points,shape,'room',0)
            self.assertFalse(result['valid'])
            self.assertNotIn('torso_angle',result)
        self.assertFalse(extract_posture(box,[],shape,'room',0)['valid'])
        bad = list(points); bad[11],bad[12] = points[5],points[6]
        self.assertFalse(extract_posture(box,bad,shape,'room',0)['valid'])

    def test_feedback_labels_are_strict_and_revocation_wins(self):
        self.assertEqual(eligible_label({'feedback':'trusted'},False),'risk')
        for reason in ('not_fall','sitting_or_lying'):
            self.assertEqual(eligible_label({'feedback':'untrusted','reason':reason},False),'normal')
        for payload in ({'feedback':'untrusted'}, {'feedback':'uncertain'}, {'label':'confirmed'},
                        *({'feedback':'untrusted','reason':r} for r in
                          ('occluded','poor_image_quality','wrong_person','other'))):
            self.assertIsNone(eligible_label(payload,False))
        self.assertIsNone(eligible_label({'feedback':'trusted'},True))

    def test_shadow_three_distinct_events_protection_and_no_mutation(self):
        f = posture()
        samples = [dict(event_id=str(i), feature=copy.deepcopy(f)) for i in range(3)]
        guards = dict(long_still=False,no_response=False,radar_fall=False)
        before = copy.deepcopy((f,samples,guards))
        self.assertEqual(evaluate(f,samples,[],guards),'suggest_extend')
        self.assertEqual((f,samples,guards),before)
        self.assertEqual(evaluate(f,samples[:2],[],guards),'insufficient')
        self.assertEqual(evaluate(f,[samples[0]]*3,[],guards),'insufficient')
        self.assertEqual(evaluate(f,samples,[samples[0]],guards),'positive_match')
        for field in guards:
            for value in (True,None,0,'not_available','unknown'):
                bad = dict(guards,**{field:value})
                self.assertEqual(evaluate(f,samples,[],bad),'protected')
        self.assertEqual(evaluate(f,samples,[],{}),'protected')

    def test_similarity_boundaries_and_context(self):
        f = posture()
        guards = dict(long_still=False,no_response=False,radar_fall=False)
        near = posture(10,0.7,0.575)
        rows = [dict(event_id=str(i),feature=near) for i in range(3)]
        self.assertEqual(evaluate(f,rows,[],guards),'suggest_extend')
        for changed in (posture(10.01),posture(0,.701),posture(0,.6,.576),
                        posture(region='other'),posture(slot=3)):
            self.assertEqual(evaluate(f,[dict(event_id=str(i),feature=changed) for i in range(3)],[],guards),'no_match')
        self.assertEqual(histogram_bins(posture()),{'torso_angle':0,'hip_height':6,'aspect_ratio':1})
        self.assertEqual(histogram_bins(posture(90,1,4)),{'torso_angle':5,'hip_height':9,'aspect_ratio':5})


if __name__ == '__main__':
    unittest.main()
