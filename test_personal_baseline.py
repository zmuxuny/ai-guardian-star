"""Offline acceptance for event posture, personal feedback and shadow isolation."""
import copy
import math
import json
import sqlite3
import socket
import tempfile
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
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


class StoreTests(unittest.TestCase):
    def setUp(self):
        from src.personal_baseline_store import PersonalBaselineStore
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)/'care.db'
        self.now = 1767225600.
        self.store = PersonalBaselineStore(self.path,'p','m',clock=lambda:self.now)

    def event(self,identity='e',mode='shadow',kind='fall',**updates):
        ref = dict(person_id='p',model_version='m',event_id=identity,mode=mode,kind=kind,
                   region_id='room',started_at=self.now,ended_at=None)
        ref.update(updates)
        self.store.create_event(ref)
        return ref

    def capture(self,identity='e',mode='shadow',camera='cam1',feature=None):
        return self.store.capture_event(mode,identity,posture() if feature is None else feature,camera)

    def feedback(self,identity='e',mode='shadow',**kwargs):
        return self.store.event_feedback(identity,mode,kwargs.pop('payload',{'feedback':'untrusted','reason':'not_fall'}),**kwargs)

    def test_samples_follow_feedback_and_revocation_never_revives_on_resubmit(self):
        self.event(); self.capture(); self.feedback()
        self.feedback()
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)
        self.feedback(payload={'feedback':'trusted'})
        self.assertEqual(len(self.store.samples('shadow','cam1')['risk']),1)
        self.feedback(operation='revoke')
        self.feedback()
        self.assertEqual(self.store.samples('shadow','cam1'),{'normal':[],'risk':[]})
        self.feedback(operation='restore')
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)
        self.feedback(payload={'feedback':'untrusted','reason':'occluded'})
        self.assertEqual(self.store.samples('shadow','cam1'),{'normal':[],'risk':[]})
        self.assertEqual(len(self.store.feedback_audit('e',self.now,status='all')),7)

    def test_feedback_first_capture_reads_latest_state_and_invalid_is_not_sample(self):
        self.event(); self.feedback(); self.feedback(operation='revoke'); self.capture()
        self.assertFalse(self.store.samples('shadow','cam1')['normal'])
        self.feedback(operation='restore')
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)
        self.event('invalid'); self.feedback('invalid')
        self.capture('invalid',feature=dict(version='posture_v1',valid=False,reason='invalid_pose'))
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)
        self.event('sit',kind='sit'); self.capture('sit'); self.feedback('sit')
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)

    def test_scope_camera_mode_and_feature_snapshot_immutable(self):
        from src.personal_baseline_store import PersonalBaselineStore
        self.event(); self.capture(); self.feedback()
        for person,model in [('q','m'),('p','n')]:
            other = PersonalBaselineStore(self.path,person,model,clock=lambda:self.now)
            with self.assertRaises(LookupError):
                other.capture_event('shadow','e',posture(),'cam1')
            self.assertFalse(other.samples('shadow','cam1')['normal'])
        self.assertFalse(self.store.samples('live','cam1')['normal'])
        self.assertFalse(self.store.samples('shadow','cam2')['normal'])
        with self.assertRaises(LookupError): self.capture(mode='live')
        self.capture()  # idempotent exact replay
        with self.assertRaises(ValueError): self.capture(feature=posture(30))
        with self.assertRaises(ValueError): self.capture(camera='cam2')
        self.event('no_camera'); self.capture('no_camera',camera=None); self.feedback('no_camera')
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)

    def test_feedback_and_audit_roll_back_if_sample_refresh_fails(self):
        self.event(); self.capture(); self.feedback()
        with patch.object(self.store,'_refresh_sample',side_effect=RuntimeError('disk')):
            with self.assertRaises(RuntimeError): self.feedback(operation='revoke')
        self.assertFalse(self.store.get_feedback('e',self.now,status='all')['is_revoked'])
        self.assertEqual(len(self.store.feedback_audit('e',self.now,status='all')),1)
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)

    def test_histograms_report_retention_and_erasure(self):
        for i in range(4):
            self.event(str(i)); self.capture(str(i))
            if i<3: self.feedback(str(i))
        for _ in range(2): self.store.observe_histogram('shadow',posture(),'cam1',self.now)
        report = self.store.personal_report('shadow','cam1')
        self.assertEqual(report['histogram_observations'],2)
        self.assertEqual(report['evaluated_events'],4)
        self.assertEqual(report['protected_events'],4)
        self.assertEqual(report['would_extend_confirmation_events'],0)
        encoded = json.dumps(report)
        for forbidden in ('torso_angle','hip_height','aspect_ratio','event_id','feature_json'):
            self.assertNotIn(forbidden,encoded)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT sum(count) FROM posture_histograms').fetchone()[0],6)
        self.now += 366*86400
        self.store.maintain('shadow')
        self.assertFalse(self.store.samples('shadow','cam1')['normal'])
        with closing(sqlite3.connect(self.path)) as db:
            for table in ('posture_features','posture_samples','posture_histograms'):
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        self.store.erase()
        self.event('after')
        with self.assertRaises(ValueError): self.capture('after')

    def test_offline_restart_and_v4_migration_backup(self):
        from src.local_care_migrations import migrate_database
        from src.personal_baseline_store import PersonalBaselineStore
        old_path = self.path.with_name('old.db')
        migrate_database(old_path,target_version=4)
        with closing(sqlite3.connect(old_path)) as db:
            db.execute("INSERT INTO baseline_samples VALUES ('p','m','old','posture','{}',1,1,1,'legacy')")
            db.commit()
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            migrated = PersonalBaselineStore(old_path,'p','m',clock=lambda:self.now)
            self.assertEqual(migrated.get_sample('old')['source'],'legacy')
            backups = list(old_path.parent.glob('old.db.v4-*.backup.db'))
            self.assertEqual(len(backups),1)
            with closing(sqlite3.connect(backups[0])) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
            self.event(); self.capture(); self.feedback()
            reopened = PersonalBaselineStore(self.path,'p','m',clock=lambda:self.now)
            self.assertEqual(len(reopened.samples('shadow','cam1')['normal']),1)

    def test_migration5_failure_rolls_back_schema_and_version(self):
        from src.local_care_migrations import migrate_database, MIGRATIONS
        old = self.path.with_name('failed.db')
        migrate_database(old,target_version=4)
        broken = self.path.with_name('broken.sql')
        broken.write_text('CREATE TABLE partial (x); SELECT missing FROM no_table;',encoding='utf8')
        with patch.dict(MIGRATIONS,{5:broken}):
            with self.assertRaises(sqlite3.OperationalError): migrate_database(old)
        with closing(sqlite3.connect(old)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)
            self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='partial'").fetchone())


if __name__ == '__main__':
    unittest.main()
