"""Offline readiness regressions; no SSH, GPIO, sensors, or real services."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from tools import board_validation as validation


class ValidationTests(unittest.TestCase):
    def test_resource_measurement_cannot_bypass_step_gate_or_hide_failed_service(self):
        from unittest.mock import patch
        device=validation.DeviceRun(self.root/'session',self.root/'app',runner=lambda args:'0')
        with self.assertRaises(ValueError): device.resource_observe(1,formal=True)
        device.set_step(1,'PASS')
        with patch.object(validation.time,'monotonic',side_effect=[0,0,2]), patch.object(validation.time,'sleep'):
            result=device.resource_observe(1)
        self.assertEqual(result['status'],'INCOMPLETE')
        self.assertEqual(result['samples'][0]['error'],'ValueError')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_python39_audit_catches_import_time_union_and_new_path_api(self):
        self.assertTrue(validation.portability_issues('from datetime import time\nquiet: time | None = None'))
        self.assertTrue(validation.portability_issues("p.write_text('x', newline='\\n')"))
        self.assertEqual(validation.portability_issues("with p.open('w', newline='\\n') as f: f.write('x')"), [])

    def test_backup_uses_consistent_sqlite_copy_and_never_overwrites(self):
        import sqlite3
        source, target = self.root/'source.db', self.root/'backup.db'
        with sqlite3.connect(source) as db:
            db.execute('CREATE TABLE samples(value TEXT)')
            db.execute("INSERT INTO samples VALUES ('preserve')")
        db.close()
        validation.backup_sqlite(source, target)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT value FROM samples').fetchone()[0], 'preserve')
        db.close()
        before = target.read_bytes()
        with self.assertRaises(FileExistsError): validation.backup_sqlite(source, target)
        self.assertEqual(target.read_bytes(), before)

    def test_gate_never_promotes_missing_or_failed_previous_step(self):
        for ledger in ({}, {'1':'PASS'}, {'1':'PASS','2':'FAIL'}):
            with self.assertRaises(ValueError): validation.require_steps(ledger, 3)
        validation.require_steps({'1':'PASS','2':'PASS'}, 3)

    def test_live_is_rejected_before_any_test_mutation(self):
        with self.assertRaises(ValueError): validation.validate_test_config({'mode':'live','sync_enabled':True})
        with self.assertRaises(ValueError): validation.validate_test_config({'mode':'shadow','sync_enabled':True})
        validation.validate_test_config({'mode':'shadow','sync_enabled':False})

    def test_empty_or_idle_observations_do_not_pass_shadow(self):
        for rows in ([], [{'states':{'P1':{'state':'IDLE','seated_seconds':0}},'live_outbox_rows':0}]):
            result = validation.assess_shadow(rows)
            self.assertNotEqual(result['status'], 'PASS')
            self.assertNotEqual(result['checks']['reminders'], 'PASS')

    def test_broadcast_isolation_requires_exercised_output(self):
        rows = [{'states':{},'shadow_mode':'shadow','live_outbox_rows':0,
                 'broadcasts':[{'level':'L0','event_id':'same','role':'P1'},{'level':'L1','event_id':'same','role':'P1'}]}]
        result = validation.assess_shadow(rows)
        self.assertEqual(result['checks']['reminders'], 'PASS')
        self.assertEqual(result['checks']['isolation'], 'PASS')
        self.assertNotEqual(result['status'], 'PASS')  # other real cases missing
        rows[0]['live_outbox_rows']=1
        self.assertEqual(validation.assess_shadow(rows)['checks']['isolation'], 'FAIL')

    def test_role_sanitization_does_not_export_private_identity_or_token(self):
        state = validation.sanitize_state({'person_id':'private-id','state':'SITTING','counts':{'L0':1}}, 'P1')
        self.assertEqual(state['role'], 'P1')
        self.assertNotIn('private-id', json.dumps(state))

    def test_idle_other_person_does_not_prove_actor_left_or_stood_up(self):
        rows=[dict(phase='leave',confirmed_action=True,actor_role='P2',sample_monotonic=t,
                   states={'P1':dict(role='P1',state='IDLE',seated_seconds=0),
                           'P2':dict(role='P2',state='PAUSED',seated_seconds=20)}) for t in (0,130)]
        self.assertNotEqual(validation.assess_shadow(rows)['checks']['leave'],'PASS')

    def test_different_actors_or_sessions_cannot_be_joined_into_leave_pass(self):
        for second_actor,second_session in (('P2','one'),('P1','two')):
            rows=[dict(phase='leave',confirmed_action=True,actor_role='P1',session_id='one',sample_monotonic=0,
                       states={'P1':dict(role='P1',state='PAUSED',seated_seconds=20)}),
                  dict(phase='leave',confirmed_action=True,actor_role=second_actor,session_id=second_session,sample_monotonic=130,
                       states={second_actor:dict(role=second_actor,state='IDLE',seated_seconds=0)})]
            self.assertNotEqual(validation.assess_shadow(rows)['checks']['leave'],'PASS')

    def test_l0_l1_from_different_episodes_are_not_an_upgrade_pass(self):
        row=dict(shadow_mode='shadow',live_outbox_rows=0,broadcasts=[{'level':'L0','event_id':'one','role':'P1'},
                                                                  {'level':'L1','event_id':'two','role':'P2'}])
        self.assertNotEqual(validation.assess_shadow([row])['checks']['reminders'],'PASS')

    def test_repeated_cover_cases_compare_frozen_time_within_each_episode(self):
        rows=[]
        for events,seconds in ((['a'],0.88),(['a','b'],1.86)):
            for _ in range(2):
                rows.append(dict(phase='cover',confirmed_action=True,actor_role='P2',session_id='same',
                                 states={'P2':dict(state='PAUSED',seated_seconds=seconds,event_ids=events)}))
        self.assertEqual(validation.assess_shadow(rows)['checks']['cover'],'PASS')
        rows[-1]['states']['P2']['seated_seconds']=2.86
        self.assertEqual(validation.assess_shadow(rows)['checks']['cover'],'FAIL')

    def test_expired_idle_samples_do_not_turn_valid_freeze_into_drift(self):
        rows=[dict(phase='cover',confirmed_action=True,actor_role='P2',states={'P2':dict(
            state='PAUSED',phase=phase,seated_seconds=seconds,event_ids=['real-event'],at=at,uncertainty_seconds=uncertainty)})
            for phase,seconds,at,uncertainty in (('SITTING',1.86,100,10),('SITTING',1.86,101,11),('IDLE',0,210.1,0),('IDLE',0,211,1))]
        self.assertEqual(validation.assess_shadow(rows)['checks']['cover'],'PASS')
        self.assertNotEqual(validation.assess_shadow(rows[2:])['checks']['cover'],'PASS')

    def test_cover_cannot_hide_early_reset_or_reset_with_missing_deadline_proof(self):
        rows=[dict(phase='cover',confirmed_action=True,actor_role='P2',states={'P2':dict(
            state='PAUSED',phase=phase,seated_seconds=seconds,event_ids=['real-event'],at=at,uncertainty_seconds=uncertainty)})
            for phase,seconds,at,uncertainty in (('SITTING',1.86,100,10),('SITTING',1.86,101,11),('IDLE',0,102,0))]
        self.assertEqual(validation.assess_shadow(rows)['checks']['cover'],'FAIL')
        del rows[-1]['states']['P2']['at']
        self.assertNotEqual(validation.assess_shadow(rows)['checks']['cover'],'PASS')

    def test_cover_without_event_identity_cannot_prove_freeze(self):
        rows=[dict(phase='cover',confirmed_action=True,actor_role='P2',states={'P2':dict(
            state='PAUSED',phase='SITTING',seated_seconds=1.86,event_ids=[])}) for _ in range(2)]
        self.assertNotEqual(validation.assess_shadow(rows)['checks']['cover'],'PASS')

    def test_owned_dropin_is_required_for_cleanup(self):
        session=self.root/'session';session.mkdir()
        (session/'token').write_text('private-token')
        expected='[Service]\nEnvironment=AI_GUARDIAN_CARE_CONFIG='+str(session/'config.json')+'\nEnvironment=AI_GUARDIAN_CARE_API_TOKEN=private-token\n'
        self.assertTrue(validation.owns_dropin(expected, session))
        self.assertFalse(validation.owns_dropin(expected+'ExecStart=/other\n', session))
        self.assertFalse(validation.owns_dropin(expected.replace('private-token','different'), session))

    def test_cleanup_refuses_foreign_dropin_without_service_commands(self):
        from unittest.mock import patch
        session=self.root/'session';session.mkdir();(session/'token').write_text('secret')
        dropin=self.root/'runtime.conf';dropin.write_text('[Service]\nExecStart=/foreign\n')
        commands=[]
        device=validation.DeviceRun(session,self.root/'app',runner=lambda args:commands.append(args),mode_reader=lambda:'shadow_owned')
        with patch.object(validation,'DROPIN',dropin):
            with self.assertRaises(ValueError):device.recover_off()
        self.assertEqual(commands,[]);self.assertTrue(dropin.exists())

    def test_cleanup_removes_only_owned_runtime_file(self):
        from unittest.mock import patch
        session=self.root/'session';session.mkdir();(session/'token').write_text('secret')
        dropin=self.root/'runtime.conf'
        dropin.write_text('[Service]\nEnvironment=AI_GUARDIAN_CARE_CONFIG='+str(session/'config.json')+'\nEnvironment=AI_GUARDIAN_CARE_API_TOKEN=secret\n')
        original=self.root/'original.service';original.write_bytes(b'preserve')
        commands=[];mode=['shadow_owned']
        def run(args):
            commands.append(args)
            if args[1]=='restart':mode[0]='off'
        device=validation.DeviceRun(session,self.root/'app',runner=run,mode_reader=lambda:mode[0])
        with patch.object(validation,'DROPIN',dropin):self.assertEqual(device.recover_off()['status'],'PASS')
        self.assertFalse(dropin.exists());self.assertEqual(original.read_bytes(),b'preserve')
        self.assertEqual(commands,[['systemctl','daemon-reload'],['systemctl','restart',validation.SERVICE]])

    def test_failed_cleanup_remains_pending_and_retries_without_dropin(self):
        from unittest.mock import patch
        session=self.root/'session';session.mkdir();(session/'token').write_text('secret')
        dropin=self.root/'runtime.conf';dropin.write_text('[Service]\nEnvironment=AI_GUARDIAN_CARE_CONFIG='+str(session/'config.json')+'\nEnvironment=AI_GUARDIAN_CARE_API_TOKEN=secret\n')
        mode=['shadow_owned'];fail=[True];commands=[]
        def run(args):
            commands.append(args)
            if args[1]=='restart':
                if fail[0]:raise OSError('simulated restart failure')
                mode[0]='off'
        device=validation.DeviceRun(session,self.root/'app',runner=run,mode_reader=lambda:mode[0])
        with patch.object(validation,'DROPIN',dropin):
            with self.assertRaises(OSError):device.recover_off()
            self.assertFalse(dropin.exists());self.assertFalse((session/'finish.request').exists())
            self.assertTrue((session/'recovery-pending.json').exists())
            fail[0]=False
            self.assertEqual(device.recover_off()['status'],'PASS')
        self.assertTrue((session/'finish.request').exists())
        self.assertFalse((session/'recovery-pending.json').exists())

    def test_mutating_api_checks_require_generated_isolated_scope(self):
        base={'mode':'shadow','sync_enabled':False,'model_version':'acceptance-'+'a'*16,'db_path':'isolated/care.db'}
        self.assertEqual(validation.isolated_database(base,self.root),self.root/'isolated/care.db')
        for change in ({'db_path':'../original.db'},{'model_version':'production-model'}):
            with self.assertRaises(ValueError):validation.isolated_database(dict(base,**change),self.root)

    def test_feedback_does_not_write_before_previous_gate(self):
        self.root.joinpath('session').mkdir();calls=[]
        device=validation.DeviceRun(self.root/'session',self.root/'app',http=lambda *a,**k:calls.append((a,k)))
        with self.assertRaises(ValueError):device.feedback_case()
        self.assertEqual(calls,[])

    def test_watchdog_is_armed_before_runtime_override_or_restart(self):
        import sqlite3
        from unittest.mock import patch
        session=self.root/'session';session.mkdir();app=self.root/'app';(app/'db').mkdir(parents=True)
        db=sqlite3.connect(app/'db/guardian.db')
        db.execute('CREATE TABLE t_face_feature(user_id TEXT,name TEXT)')
        db.execute("INSERT INTO t_face_feature VALUES ('uid-a','label-a')");db.commit();db.close()
        (app/'original.py').write_bytes(b'preserve')
        baseline=self.root/'baseline.json';validation.write_json(baseline,dict(expected_files={'original.py':hashlib.sha256(b'preserve').hexdigest()}))
        dropin=self.root/'run/override.conf';calls=[];armed=[]
        def run(args):
            calls.append(args)
            if args[1]=='cat':return 'original unit'
            if args[1]=='show':return '99'
            if args[1]=='restart':self.assertTrue(armed);self.assertTrue(dropin.exists())
            return ''
        device=validation.DeviceRun(session,app,runner=run)
        def probe():
            device.set_step(1,'PASS');validation.write_json(session/'probe.json',dict(care_mode='off',care_config_present=False))
        def arm():self.assertFalse(dropin.exists());armed.append(True)
        original_read=Path.read_bytes
        def read_bytes(path):
            return b'UNCHANGED=value\0' if path.as_posix()=='/proc/99/environ' else original_read(path)
        with patch.object(validation,'DROPIN',dropin),patch.object(validation,'BASELINE',baseline),patch.object(device,'probe',probe),patch.object(device,'_arm_watchdog',arm),patch.object(device,'wait_ready',lambda:None),patch.object(Path,'read_bytes',read_bytes):
            self.assertEqual(device.start_shadow()['status'],'PASS')
        self.assertTrue(armed);self.assertEqual((app/'original.py').read_bytes(),b'preserve')

    def test_two_layer_rollback_plan_keeps_new_patch_from_failing_old_overlay(self):
        from tools.care_flat_release import PATHS
        app=self.root/'app';app.mkdir();flat=self.root/'flat';(flat/'code').mkdir(parents=True)
        patch=self.root/'patch';patch.mkdir();rows=[];patch_rows=[]
        for name in PATHS:
            target=app/name;target.parent.mkdir(parents=True,exist_ok=True)
            original=b'old-entry' if name=='ascend_board_server.py' else None
            installed=('installed-'+name).encode();target.write_bytes(installed)
            rows.append(dict(path=name,sha256=hashlib.sha256(installed).hexdigest(),before_sha256=hashlib.sha256(original).hexdigest() if original else None))
            if original:(flat/'code'/name).write_bytes(original)
            if name in ('care_runtime.py','care_api.py'):
                (patch/name).write_bytes(installed);new=installed+b'-identity-fix';target.write_bytes(new)
                patch_rows.append(dict(path=name,before_sha256=hashlib.sha256(installed).hexdigest(),sha256=hashlib.sha256(new).hexdigest()))
        validation.write_json(flat/'backup.json',dict(kind='care-flat-backup',files=rows))
        validation.write_json(patch/'manifest.json',dict(files=patch_rows))
        self.assertEqual(validation.rollback_plan(app,flat,patch)['status'],'PASS')
        (app/'care_runtime.py').write_bytes(b'newer independent changes')
        with self.assertRaises(ValueError):validation.rollback_plan(app,flat,patch)

    def test_package_is_reproducible_and_contains_no_private_data(self):
        import zipfile
        repo=Path(__file__).resolve().parent
        one,two=self.root/'one.zip',self.root/'two.zip'
        validation.build_kit(repo,one);validation.build_kit(repo,two)
        self.assertEqual(one.read_bytes(),two.read_bytes())
        with zipfile.ZipFile(one) as archive:
            names=archive.namelist()
            self.assertIn('tools/board_validation.py',names)
            self.assertIn('deploy/board/care-validation-baseline.json',names)
            self.assertFalse(any(n.endswith(('.db','.om','.p7b','.cer')) or 'token' in n for n in names))
            manifest=json.loads(archive.read('kit-manifest.json'))
            self.assertEqual(manifest['files']['tools/board_validation.py'],hashlib.sha256(archive.read('tools/board_validation.py')).hexdigest())


if __name__=='__main__': unittest.main(verbosity=2)
