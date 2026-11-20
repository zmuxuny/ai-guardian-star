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
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import ast
import threading
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
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

    def test_trusted_event_is_never_recommended_for_extension(self):
        guards=dict(long_still=False,no_response=False,radar_fall=False)
        for identity in ('n1','n2','n3','candidate'):
            self.event(identity)
            self.store.capture_event('shadow',identity,posture(),'cam1',guards=guards)
            self.feedback(identity,payload={'feedback':'trusted'} if identity=='candidate' else
                          {'feedback':'untrusted','reason':'not_fall'})
        report=self.store.personal_report('shadow','cam1')
        self.assertEqual(report['would_extend_confirmation_events'],0)
        self.assertGreater(report['positive_match_events'],0)

    def test_static_suggestion_is_recomputed_after_withdrawal_and_quality_reasons_are_aggregate(self):
        guards=dict(long_still=False,no_response=False,radar_fall=False)
        for identity in ('n1','n2','n3','candidate'):
            self.event(identity)
            self.store.capture_event('shadow',identity,posture(),'cam1',guards=guards)
            if identity!='candidate': self.feedback(identity)
        first=self.store.personal_report('shadow','cam1')
        self.assertEqual(first['would_extend_confirmation_events'],1)
        self.feedback('n1',operation='revoke')
        self.assertEqual(self.store.personal_report('shadow','cam1')['would_extend_confirmation_events'],0)
        self.event('bad'); self.capture('bad',feature=dict(version='posture_v1',valid=False,reason='invalid_pose'))
        self.event('unknown'); self.capture('unknown')
        report=self.store.personal_report('shadow','cam1')
        self.assertEqual(report['quality_reasons'],{'invalid_pose':1})
        self.assertEqual(report['protection_reasons']['radar_fall_unknown'],1)

    def test_new_foreign_keys_are_checked_before_adopting_existing_schema(self):
        from src.local_care_migrations import migrate_database, MIGRATIONS
        old=self.path.with_name('bad_fk.db')
        script=MIGRATIONS[5].read_text(encoding='utf8')
        script=script.replace(',\n    FOREIGN KEY(person_id,model_version,event_id) REFERENCES care_events(person_id,model_version,event_id)','')
        broken=self.path.with_name('no_fk.sql'); broken.write_text(script,encoding='utf8')
        migrate_database(old,target_version=4)
        with patch.dict(MIGRATIONS,{5:broken}):
            with self.assertRaises(ValueError): migrate_database(old)

    def test_feedback_while_collection_disabled_still_refreshes_saved_samples(self):
        from src.weekly_store import WeeklyStore
        self.event(); self.capture(); self.feedback()
        disabled=WeeklyStore(self.path,'p','m',clock=lambda:self.now)
        disabled.event_feedback('e','shadow',operation='revoke')
        self.assertFalse(self.store.samples('shadow','cam1')['normal'])
        disabled.event_feedback('e','shadow',operation='restore')
        self.assertEqual(len(self.store.samples('shadow','cam1')['normal']),1)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        from src.care_runtime import CareRuntime, RuntimeConfig
        from src.sedentary_care import VirtualClock
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.clock = VirtualClock(datetime(2026,11,20,12,tzinfo=timezone(timedelta(hours=8))))
        self.config = RuntimeConfig(db_path=Path(self.directory.name)/'care.db',person_ids=('p',),
                                    model_version='m',mode='shadow',personal_baseline_enabled=True,camera_revision='cam1',region_id='room')
        self.runtime = CareRuntime(self.config,clock=self.clock)
        self.addCleanup(self.runtime.close)

    def alert(self,fall=True,**extra):
        box,kpts,shape = pose_input()
        return dict(id=7,face_label='known:p',status='FALL DETECTED' if fall else 'Normal',
                    fall_raw=fall,is_sitting=False,box=box,kpts=kpts,frame_shape=shape,**extra)

    def record(self,identity='real',alert=None):
        alert=alert or self.alert()
        self.runtime.process_frame([alert],{'fall':[alert]})
        self.runtime.observe_recorded_event('fall',alert,
            dict(event_id=identity,kind='fall',started_at=self.runtime.utc()))
        self.assertTrue(self.runtime.personal.flush())

    def test_shadow_real_recorded_id_feedback_and_no_new_recording(self):
        alert = self.alert()
        result = self.runtime.process_frame([alert],{'fall':[alert]})
        self.assertFalse(self.runtime.events('p'))
        self.record()
        events = self.runtime.events('p')
        self.assertEqual([r['event_id'] for r in events],['real'])
        self.assertFalse(result['event_refs'])
        self.runtime.feedback('p','real',{'feedback':'untrusted','reason':'not_fall'})
        self.assertEqual(len(self.runtime.store('p').samples('shadow','cam1')['normal']),1)
        self.assertFalse(self.runtime.pending('p'))

    def test_histogram_throttled_and_ambiguous_or_alerted_frames_excluded(self):
        normal = self.alert(False)
        for _ in range(20): self.runtime.process_frame([normal],{})
        self.assertTrue(self.runtime.personal.flush())
        self.assertEqual(self.runtime.personal_report('p')['histogram_observations'],1)
        for rows in ([normal,normal],[self.alert()], [dict(normal,face_label='stranger')],
                     [dict(normal,fall_raw=True)], [dict(normal,pose_reliable=False)]):
            self.clock.advance(2); self.runtime.process_frame(rows,{})
        self.assertTrue(self.runtime.personal.flush())
        self.assertEqual(self.runtime.personal_report('p')['histogram_observations'],1)
        self.clock.advance(2); self.runtime.process_frame([normal],{})
        self.assertTrue(self.runtime.personal.flush())
        self.assertEqual(self.runtime.personal_report('p')['histogram_observations'],2)

    def test_erased_person_drops_queued_work_and_requires_explicit_resume(self):
        self.record()
        self.runtime.erase_person('p')
        self.record('after_erase')
        self.assertFalse(self.runtime.events('p'))
        self.assertEqual(self.runtime.personal_report('p')['evaluated_events'],0)
        self.runtime.resume_person('p'); self.record('after_resume')
        self.assertEqual([r['event_id'] for r in self.runtime.events('p')],['after_resume'])

    def test_disabled_feature_does_not_change_existing_events_or_start_worker(self):
        from src.care_runtime import CareRuntime
        other = CareRuntime(replace(self.config,db_path=Path(self.directory.name)/'disabled.db',personal_baseline_enabled=False),clock=self.clock)
        self.addCleanup(other.close)
        self.assertIsNone(other.personal)
        alert = self.alert()
        before = copy.deepcopy(alert)
        other.process_frame([alert],{'fall':[alert]})
        self.assertEqual(len(other.events('p')),1)
        self.assertEqual(alert,before)

    def test_entry_supplies_frame_shape_without_mutating_legacy_alerts(self):
        from test_care_delivery import production_entry
        alert=self.alert(); shape=alert.pop('frame_shape'); before=copy.deepcopy(alert)
        result=production_entry('dispatch_care_detection')(self.runtime,[alert],{'fall':[alert]},shape)
        self.assertEqual(result['mode'],'shadow')
        self.runtime.observe_recorded_event('fall',alert,dict(event_id='shape',kind='fall',started_at=self.runtime.utc()))
        self.assertTrue(self.runtime.personal.flush())
        self.runtime.feedback('p','shape',{'feedback':'trusted'})
        self.assertEqual(len(self.runtime.store('p').samples('shadow','cam1')['risk']),1)
        self.assertEqual(alert,before)

    def test_unknown_identity_missing_record_id_and_invalid_feature_do_not_throw(self):
        self.runtime.observe_recorded_event('fall',self.alert(),{})
        self.runtime.observe_recorded_event('fall',self.alert(face_score=.1),None)
        self.runtime.observe_recorded_event('fall',dict(self.alert(),face_label='unknown'),{'event_id':'u'})
        self.assertTrue(self.runtime.personal.flush())
        self.assertFalse(self.runtime.events('p'))

    def test_api_uses_existing_auth_and_exposes_only_aggregate(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.care_api import create_care_router
        app = FastAPI(); app.include_router(create_care_router(self.runtime,lambda:'private-test'))
        self.record()
        with TestClient(app) as client:
            route='/api/care/m/p/personal-baseline'
            self.assertEqual(client.get(route).status_code,401)
            headers={'Authorization':'Bearer private-test'}
            response=client.get(route,headers=headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()['evaluated_events'],1)
            for key in ('torso_angle','hip_height','aspect_ratio','kpts','box','event_id'):
                self.assertNotIn(key,response.text)
            self.assertEqual(client.get('/api/care/m/q/personal-baseline',headers=headers).status_code,404)

    def test_real_history_entry_preserves_id_through_feature_and_feedback(self):
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parent/'src'))
        from src.guardian_recording_config import RecordingConfig
        from src.guardian_storage import initialize_storage
        from src.guardian_history import HistoryStore
        from src.guardian_event_cache import EventClipCache
        from test_care_delivery import production_entry
        config=RecordingConfig(enabled=True,data_root=Path(self.directory.name)/'recordings',
                               storage_quota_bytes=10**7,min_free_bytes=1,encoder='test-only-fake')
        initialize_storage(config)
        history=HistoryStore(config); self.addCleanup(history.close)
        cache=EventClipCache(config,history,None,clock=self.runtime.utc,monotonic=lambda:self.clock.now)
        alert=self.alert(); before=copy.deepcopy(alert)
        result=self.runtime.process_frame([alert],{'fall':[alert]})
        actual=production_entry('trigger_history_event')(cache,'fall',alert,result,self.runtime.utc(),self.runtime)
        self.assertTrue(self.runtime.personal.flush())
        identity=actual['event_id']
        self.assertEqual(history.get_event(identity)['id'],identity)
        self.assertEqual([e['event_id'] for e in self.runtime.events('p')],[identity])
        self.runtime.feedback('p',identity,{'feedback':'trusted'})
        self.assertEqual(self.runtime.store('p').samples('shadow','cam1')['risk'][0]['event_id'],identity)
        self.assertEqual(alert,before)
        self.assertEqual(cache._clip.event_ids,[identity])

    def test_legacy_recording_result_survives_private_observation_failure(self):
        from test_care_delivery import production_entry
        from types import SimpleNamespace
        trigger=production_entry('trigger_history_event')
        expected={'event_id':'real','state':'recording'}
        cache=SimpleNamespace(trigger=lambda *args,**kwargs:expected)
        broken=SimpleNamespace(observe_history_result=lambda *args:(_ for _ in ()).throw(OSError('private')))
        self.assertIs(trigger(cache,'fall',self.alert(),{'event_refs':{}},self.runtime.utc(),broken),expected)

    def test_close_drains_private_writer(self):
        self.record()
        self.runtime.close()
        self.assertFalse(self.runtime.personal._thread.is_alive())

    def test_live_existing_ref_reused_and_feedback_outbox_has_no_features(self):
        from src.care_runtime import CareRuntime
        from src.guardian_recording_config import RecordingConfig
        from src.guardian_storage import initialize_storage
        from src.guardian_history import HistoryStore
        from src.guardian_event_cache import EventClipCache
        from test_care_delivery import production_entry
        live=CareRuntime(replace(self.config,mode='live',db_path=Path(self.directory.name)/'live.db'),clock=self.clock)
        self.addCleanup(live.close)
        config=RecordingConfig(enabled=True,data_root=Path(self.directory.name)/'live-recordings',
                               storage_quota_bytes=10**7,min_free_bytes=1,encoder='test-only-fake')
        initialize_storage(config)
        history=HistoryStore(config); self.addCleanup(history.close)
        cache=EventClipCache(config,history,None,clock=live.utc,monotonic=lambda:self.clock.now)
        alert=self.alert()
        result=live.process_frame([alert],{'fall':[alert]})
        identity=result['event_refs'][('fall',7)]['event_id']
        actual=production_entry('trigger_history_event')(cache,'fall',alert,result,live.utc(),live)
        self.assertEqual(actual['event_id'],identity)
        self.assertTrue(live.personal.flush())
        live.feedback('p',identity,{'feedback':'trusted'})
        self.assertEqual(len(live.events('p')),1)
        encoded=json.dumps(live.pending('p'))
        for field in ('torso_angle','hip_height','aspect_ratio','feature_json','frame_shape','kpts'):
            self.assertNotIn(field,encoded)

    def test_worker_failure_and_queue_overflow_leave_original_input_untouched(self):
        alert=self.alert(); before=copy.deepcopy(alert)
        self.runtime.process_frame([alert],{'fall':[alert]})
        entered,release=threading.Event(),threading.Event()
        original=self.runtime.store('p').capture_event
        def slow(*args,**kwargs):
            entered.set(); release.wait(5); return original(*args,**kwargs)
        with patch.object(self.runtime.store('p'),'capture_event',side_effect=slow):
            self.runtime.observe_recorded_event('fall',alert,dict(event_id='first',kind='fall',started_at=self.runtime.utc()))
            self.assertTrue(entered.wait(2))
            for i in range(50):
                self.runtime.observe_recorded_event('fall',alert,dict(event_id='overflow'+str(i),kind='fall',started_at=self.runtime.utc()))
            self.assertGreater(self.runtime.personal.diagnostics()['dropped'],0)
            release.set()
            self.assertTrue(self.runtime.personal.flush())
        with patch.object(self.runtime.store('p'),'capture_event',side_effect=OSError('secret-data')):
            self.record('failure')
        self.assertGreater(self.runtime.personal.diagnostics()['errors'],0)
        self.assertEqual(alert,before)


class PackagingTests(unittest.TestCase):
    def test_all_existing_packages_include_personal_modules_and_schema5(self):
        import zipfile
        from tools.care_release import FILES
        from tools.care_flat_release import MODULES,MIGRATIONS
        from tools.board_validation import build_kit
        modules=('posture_features','personal_baseline_store','personal_baseline')
        for module in modules:
            self.assertIn('src/'+module+'.py',FILES)
            self.assertIn(module,MODULES)
        self.assertIn('005_personal_baseline.sql',MIGRATIONS)
        with tempfile.TemporaryDirectory() as directory:
            destination=Path(directory)/'kit.zip'
            build_kit(Path(__file__).resolve().parent,destination)
            with zipfile.ZipFile(destination) as archive:
                names=archive.namelist()
                for module in modules:
                    self.assertIn('src/'+module+'.py',names)
                self.assertIn('src/migrations/local_care/005_personal_baseline.sql',names)


if __name__ == '__main__':
    unittest.main()
