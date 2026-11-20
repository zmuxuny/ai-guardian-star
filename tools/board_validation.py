"""Python 3.9 standard-library readiness kit. Offline actions never contact a board.

Device actions use the existing service/HTTP API. They never flash firmware,
open a second camera/NPU, install dependencies, or publish MQTT messages.
"""
import argparse
import ast
import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import py_compile
import re
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
BASELINE = ROOT/'deploy/board/care-validation-baseline.json'
SERVICE = 'guardian-board.service'
DROPIN = Path('/run/systemd/system/guardian-board.service.d/90-care-shadow-acceptance.conf')
PHASES = ('baseline','seated','standing','stand-still','cover','leave','return','quiet')
STATE_KEYS = ('at','wall_time','state','phase','seated_seconds','remaining_seconds',
              'uncertainty_seconds','uncertainty_reason','level','pending_level','counts','quiet')
DEMO_DETECTOR_ENV = {'AI_GUARDIAN_VLM_LONG_SIT_SECONDS':'2'}
DEMO_AUDIO_ENV = {'AI_GUARDIAN_CARE_AUDIO_DIR':'/root/ai_guardian/care_audio_assets','AI_GUARDIAN_CARE_DEMO_AUDIO':'1'}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name+'.'+secrets.token_hex(6)+'.tmp')
    try:
        with temp.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        temp.chmod(0o600);temp.replace(path)
    finally:
        if temp.exists(): temp.unlink()


def fingerprint(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1048576), b''): result.update(block)
    return result.hexdigest()


def backup_sqlite(source, destination):
    destination = Path(destination)
    with destination.open('xb'): pass
    a = b = None
    try:
        a = sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro', uri=True, timeout=10)
        b = sqlite3.connect(str(destination));a.backup(b)
        if b.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('backup_integrity_failed')
    finally:
        if a: a.close()
        if b: b.close()


def portability_issues(source):
    try: tree = ast.parse(source, feature_version=(3,9))
    except SyntaxError as exc: return ['python39_syntax_line_'+str(exc.lineno)]
    issues = []
    annotations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign): annotations.append(node.annotation)
        if isinstance(node, (ast.FunctionDef,ast.AsyncFunctionDef)) and node.returns:
            annotations.append(node.returns)
        if isinstance(node, ast.arg) and node.annotation: annotations.append(node.annotation)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == 'write_text' and any(k.arg=='newline' for k in node.keywords)):
            issues.append('Path.write_text_newline_requires_python310')
    for node in annotations:
        if any(isinstance(child,ast.BinOp) and isinstance(child.op,ast.BitOr) for child in ast.walk(node)):
            issues.append('PEP604_annotation_not_safe_on_python39')
    return sorted(set(issues))


def offline_audit(repo, output):
    repo, output = Path(repo), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    paths = list((repo/'src').rglob('*.py'))
    paths += [repo/'tools'/name for name in ('board_validation.py','care_flat_release.py',
              'care_release.py','care_runtime_patch.py','run_shadow_scenarios.py','run_care_delivery.py','run_weekly_scenarios.py')]
    rows = []
    for index,path in enumerate(sorted(set(paths))):
        issues = portability_issues(path.read_text(encoding='utf-8-sig'))
        try: py_compile.compile(str(path), cfile=str(output/('compiled-%d.pyc'%index)), doraise=True)
        except py_compile.PyCompileError: issues.append('bytecode_compilation_failed')
        rows.append(dict(path=path.relative_to(repo).as_posix(),status='FAIL' if issues else 'PASS',issues=issues))
    report = dict(schema_version=1,status='PASS' if all(r['status']=='PASS' for r in rows) else 'FAIL',
                  interpreter=platform.python_version(),compilation_scope='Python only; not CANN native or OM rebuild',files=rows)
    write_json(output/'offline-audit.json',report)
    return report


def build_kit(repo, destination):
    repo, destination = Path(repo), Path(destination)
    names = ['tools/board_validation.py','deploy/board/care-validation-baseline.json']
    for name in ('docs/board-offline-preparation-2026-11-17.md','tools/Invoke-BoardValidation.ps1',
                 'test_weekly_report.py','tools/care_flat_release.py','tools/care_release.py',
                 'tools/care_runtime_patch.py','test_care_restart_input.py','test_care_runtime_patch.py',
                 'test_board_validation.py','docs/board-retest-ready-2026-11-18.md','docs/board-fast-demo-2026-11-18.md',
                 'docs/board-short-restart-fix-2026-11-17.md'):
        if (repo/name).is_file(): names.append(name)
    # Isolated weekly fixtures use only these local modules; no sensor imports.
    for name in ('local_care_store','local_care_migrations','care_delivery_store','weekly_store','weekly_report',
                 'sedentary_care','shadow_mode','region_aggregation','guardian_runtime','care_runtime','care_transport','care_api',
                 'posture_features','personal_baseline_store','personal_baseline'):
        names.append('src/'+name+'.py')
    names += [p.relative_to(repo).as_posix() for p in (repo/'src/migrations/local_care').glob('*.sql')]
    blobs = {name:(repo/name).read_bytes() for name in sorted(names)}
    manifest = dict(schema_version=1,files={n:hashlib.sha256(v).hexdigest() for n,v in blobs.items()})
    blobs['kit-manifest.json'] = (json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(blobs.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return dict(status='PASS',sha256=fingerprint(destination),files=len(blobs))


def require_steps(ledger, number):
    if any(ledger.get(str(n))!='PASS' for n in range(1,number)):
        raise ValueError('previous_step_not_passed')


def validate_test_config(config):
    if config.get('mode')!='shadow' or config.get('sync_enabled') is not False:
        raise ValueError('only_isolated_shadow_is_permitted')


def isolated_database(config, session):
    validate_test_config(config)
    path=(Path(session)/config['db_path']).resolve()
    if Path(session).resolve() not in path.parents or not re.fullmatch(r'acceptance-[0-9a-f]{16}',config['model_version']):
        raise ValueError('operation_refused_outside_generated_test_scope')
    return path


def sanitize_state(state, role):
    return dict(role=role,**{key:state[key] for key in STATE_KEYS if key in state})


def visible_actor(sample):
    roles=sorted(set(sample.get('recognized_roles',[])))
    if not roles: raise ValueError('recognized_actor_required; specify a previously observed role for absence phases')
    return max(roles,key=lambda role:sample.get('states',{}).get(role,{}).get('seated_seconds',0))


def owns_dropin(content, session):
    session = Path(session)
    if not (session/'token').is_file(): return False
    expected={'[Service]', 'Environment=AI_GUARDIAN_CARE_CONFIG='+str(session/'config.json'),
              'Environment=AI_GUARDIAN_CARE_API_TOKEN='+(session/'token').read_text().strip()}
    profile_path=session/'test-profile.json'
    if profile_path.exists():
        try: profile=read_json(profile_path)
        except (OSError,ValueError): return False
        overrides=profile.get('detector_environment',{})
        if overrides:
            if profile.get('name')!='fast-demo' or overrides!=DEMO_DETECTOR_ENV: return False
            expected.update('Environment='+key+'='+value for key,value in overrides.items())
        audio=profile.get('audio_environment',{})
        if audio:
            if profile.get('name')!='fast-demo' or audio!=DEMO_AUDIO_ENV:return False
            expected.update('Environment='+key+'='+value for key,value in audio.items())
    lines=[line.strip() for line in content.splitlines() if line.strip()]
    return len(lines)==len(expected) and set(lines)==expected


def assess_shadow(rows, restart_results=()):
    checks = dict(reminders='NOT_EXERCISED',isolation='NOT_EXERCISED',seated='NOT_EXERCISED',
                  standing='NOT_EXERCISED',cover='NOT_EXERCISED',leave='NOT_EXERCISED',
                  short_restart='NOT_EXERCISED',long_restart='NOT_EXERCISED',quiet='NOT_EXERCISED')
    broadcasts=[b for row in rows for b in row.get('broadcasts',[])]
    episodes={}
    for row in rows:
        for b in row.get('broadcasts',[]):
            if b.get('event_id') and b.get('role'):
                key=(row.get('session_id','legacy'),b['role'],b['event_id'])
                episodes.setdefault(key,set()).add(b.get('level'))
    if any({'L0','L1'}<=levels for levels in episodes.values()): checks['reminders']='PASS'
    if broadcasts:
        checks['isolation']='PASS' if rows and all(r.get('live_outbox_rows')==0 and r.get('shadow_mode')=='shadow' for r in rows) else 'FAIL'
    if any(row.get('live_outbox_rows',0)>0 for row in rows): checks['isolation']='FAIL'
    for phase in ('seated','standing','cover','leave','quiet'):
        groups={}
        for row in rows:
            if row.get('phase')==phase and row.get('confirmed_action') and row.get('actor_role'):
                groups.setdefault((row.get('session_id','legacy'),row['actor_role']),[]).append(row)
        results=[]
        for (_,actor),sample in groups.items():
            states=[row['states'][actor] for row in sample if actor in row.get('states',{})]
            value='NOT_EXERCISED'
            if phase=='seated' and any(s.get('seated_seconds',0)>0 for s in states):value='PASS'
            if phase=='standing' and any(actor in row.get('recognized_roles',[])
                    and row['states'].get(actor,{}).get('state')=='IDLE'
                    and row['states'][actor].get('seated_seconds')==0 for row in sample):value='PASS'
            if phase=='cover':
                paused=[s for s in states if s.get('state')=='PAUSED' and s.get('event_ids')]
                # Repeating a physical case can start a new real event. Compare
                # frozen values only while the exported event history is equal.
                # A changed history splits evidence conservatively; never join
                # two different sitting rounds to manufacture a freeze/pass.
                by_episode={}
                for state in paused:
                    by_episode.setdefault(tuple(state['event_ids']),[]).append(state)
                ranges=[];expiry=[]
                for segment in by_episode.values():
                    active=[];latest=None
                    for state in segment:
                        if state.get('phase')!='IDLE':
                            active.append(state['seated_seconds']);latest=state
                        elif latest is not None:
                            # Clearing at the real 120s deadline is expected;
                            # clearing earlier (or without time proof) must not
                            # be hidden by excluding all idle snapshots.
                            times=(state.get('at'),latest.get('at'),latest.get('uncertainty_seconds'))
                            if all(isinstance(t,(int,float)) and not isinstance(t,bool) for t in times):
                                expiry.append('PASS' if times[0]-(times[1]-times[2])>=120 else 'FAIL')
                            else: expiry.append('NOT_EXERCISED')
                    if len(active)>=2: ranges.append(max(active)-min(active))
                if ranges:
                    value=('FAIL' if any(delta>=0.3 for delta in ranges) or 'FAIL' in expiry else
                           'NOT_EXERCISED' if 'NOT_EXERCISED' in expiry else 'PASS')
            if phase=='leave' and len(sample)>=2:
                duration=sample[-1].get('sample_monotonic',0)-sample[0].get('sample_monotonic',0)
                if duration>=120 and any(s.get('seated_seconds',0)>0 for s in states) and sample[-1].get('states',{}).get(actor,{}).get('state')=='IDLE':value='PASS'
            if phase=='quiet' and any(s.get('quiet') and s.get('pending_level') for s in states):
                value='PASS' if all(not r.get('broadcasts') for r in sample) else 'FAIL'
            results.append(value)
        if 'FAIL' in results:checks[phase]='FAIL'
        elif 'PASS' in results:checks[phase]='PASS'
    for result in restart_results:
        key=result.get('kind','')+'_restart'
        if key in checks: checks[key]=result.get('status','FAIL')
    return dict(status='FAIL' if 'FAIL' in checks.values() else 'PASS' if all(v=='PASS' for v in checks.values()) else 'INCOMPLETE',
                scope='shadow/static-proxy/simulated-output only',checks=checks)


def rollback_plan(app_root, flat_backup, identity_backup):
    """Read-only two-layer plan; e463172 must be undone before the 063 overlay."""
    from tools.care_flat_release import PATHS
    app_root,flat_backup,identity_backup=map(Path,(app_root,flat_backup,identity_backup))
    overlay=read_json(flat_backup/'backup.json');patch=read_json(identity_backup/'manifest.json')
    if overlay.get('kind')!='care-flat-backup' or {r['path'] for r in overlay.get('files',[])}!=set(PATHS):
        raise ValueError('unknown_flat_rollback_manifest')
    if {r['path'] for r in patch.get('files',[])}!={'care_runtime.py','care_api.py'}:
        raise ValueError('unknown_identity_patch_manifest')
    effective={};reverse=[]
    for row in patch['files']:
        path=app_root/row['path'];before=identity_backup/row['path']
        if fingerprint(before)!=row['before_sha256']: raise ValueError('identity_backup_changed')
        actual=fingerprint(path) if path.exists() else None
        if actual not in (None,row['sha256'],row['before_sha256']): raise ValueError('post_patch_code_change_requires_review')
        effective[row['path']]=row['before_sha256'] if actual else None
        reverse.append(row)
    for row in overlay['files']:
        path=app_root/row['path']
        actual=effective.get(row['path'],fingerprint(path) if path.exists() else None)
        if actual not in (None,row['sha256'],row['before_sha256']): raise ValueError('post_overlay_code_change_requires_review')
        if row['before_sha256'] is not None and fingerprint(flat_backup/'code'/row['path'])!=row['before_sha256']:
            raise ValueError('original_entry_backup_changed')
    return dict(status='PASS',order=['stop_owned_shadow_and_service','reverse_identity_patch_atomically',
                'rollback_flat_overlay','start_original_service_and_check_camera'],reverse_patch=reverse,
                database_action='never restore or delete a database')


def code_rollback(device, flat_backup, identity_backup):
    from tools.care_flat_release import rollback_flat
    require_steps(device.ledger(),6)
    plan=rollback_plan(device.app_root,flat_backup,identity_backup)
    if DROPIN.exists(): device.recover_off()
    device.runner(['systemctl','stop',SERVICE])
    # On an error remain stopped; never start partially restored code.
    for row in plan['reverse_patch']:
        target=device.app_root/row['path']
        if target.exists() and fingerprint(target)==row['sha256']:
            stage=target.with_name(target.name+'.ready-restore-'+secrets.token_hex(8))
            try:
                shutil.copy2(Path(identity_backup)/row['path'],stage)
                if fingerprint(stage)!=row['before_sha256']: raise ValueError('restored_module_hash_failed')
                stage.replace(target)
            finally:
                if stage.exists(): stage.unlink()
    rollback_flat(device.app_root,flat_backup)
    device.runner(['systemctl','start',SERVICE])
    return dict(status='INCOMPLETE',code_restored=True,original_service_start_requested=True,
                remaining=['camera_inference_and_legacy_functions_manual_recheck'],database_preserved=True)


class DeviceRun:
    def __init__(self, session, app_root='/root/ai_guardian', runner=None, http=None, mode_reader=None, reference_time=None):
        self.session=Path(session).resolve();self.app_root=Path(app_root).resolve()
        if self.app_root==self.session or self.app_root in self.session.parents or self.session in self.app_root.parents:
            raise ValueError('test_session_must_be_outside_application')
        self.runner=runner or self._run
        self.http=http or self._http
        self.mode_reader=mode_reader or self._runtime_mode
        self.reference_time=reference_time

    @staticmethod
    def _run(args):
        return subprocess.check_output(args,stderr=subprocess.DEVNULL,universal_newlines=True,timeout=65).strip()

    def _http(self, path, method='GET', body=None, token=None):
        if token is None and (self.session/'token').exists(): token=(self.session/'token').read_text().strip()
        headers={'Content-Type':'application/json'}
        if token: headers['Authorization']='Bearer '+token
        request=urllib.request.Request('http://127.0.0.1:5000'+path,method=method,headers=headers,
                                      data=None if body is None else json.dumps(body).encode())
        with urllib.request.urlopen(request,timeout=8) as response:
            return json.load(response)

    def ledger(self):
        return read_json(self.session/'ledger.json') if (self.session/'ledger.json').exists() else {}

    def set_step(self, number, status):
        ledger=self.ledger();ledger[str(number)]=status;write_json(self.session/'ledger.json',ledger)

    def _runtime_mode(self):
        pid=self.runner(['systemctl','show',SERVICE,'-p','MainPID','--value'])
        if not pid.isdigit() or pid=='0':return 'stopped'
        env=dict(x.split(b'=',1) for x in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in x)
        value=env.get(b'AI_GUARDIAN_CARE_CONFIG')
        if not value:return 'off'
        # Do not trust a file edited after startup to describe the live process.
        return 'shadow_owned' if Path(os.fsdecode(value)).resolve()==self.session/'config.json' else 'foreign'

    def probe(self):
        baseline=read_json(BASELINE)
        files={name:('PASS' if (self.app_root/name).is_file() and fingerprint(self.app_root/name)==digest else 'FAIL')
               for name,digest in baseline['expected_files'].items()}
        arch=platform.system()=='Linux' and platform.machine().lower() in ('aarch64','arm64')
        active=self.runner(['systemctl','is-active',SERVICE])=='active'
        versions=sys.version_info[:2]>=(3,9) and tuple(map(int,sqlite3.sqlite_version.split('.')[:2]))>=(3,24)
        stats=self.http('/api/stats')
        current_mode='off';pid=self.runner(['systemctl','show',SERVICE,'-p','MainPID','--value'])
        if not pid.isdigit() or pid=='0': raise ValueError('service_has_no_process')
        entries=Path('/proc/'+pid+'/environ').read_bytes().split(b'\0')
        env=dict(x.split(b'=',1) for x in entries if b'=' in x)
        if env.get(b'AI_GUARDIAN_CARE_CONFIG'):
            current_mode=read_json(Path(os.fsdecode(env[b'AI_GUARDIAN_CARE_CONFIG'])))['mode']
        metadata={}
        if shutil.which('npu-smi'):
            text=self.runner(['npu-smi','info'])
            metadata['chip_tokens']=sorted(set(re.findall(r'\b(?:Ascend\s*)?3[19]0[A-Za-z0-9]*\b',text)))
        library=self.app_root/'libguardian_audio.so'
        if library.is_file():
            header=library.read_bytes()[:20]
            metadata['audio_elf_machine']=int.from_bytes(header[18:20],'little' if header[5]==1 else 'big') if len(header)>=20 and header[:4]==b'\x7fELF' else 'not_elf'
        clock_delta=None if self.reference_time is None else time.time()-self.reference_time
        clock_ok=datetime.datetime.now(datetime.timezone.utc).year>=2020 and (clock_delta is None or abs(clock_delta)<=120)
        status='PASS' if arch and versions and active and clock_ok and all(v=='PASS' for v in files.values()) and stats.get('camera_connected') and (stats.get('fps') or 0)>0 else 'FAIL'
        self.session.mkdir(parents=True,exist_ok=True,mode=0o700)
        result=dict(status=status,architecture=platform.machine(),python=platform.python_version(),sqlite=sqlite3.sqlite_version,
                    service_active=active,care_mode=current_mode,care_config_present=bool(env.get(b'AI_GUARDIAN_CARE_CONFIG')),files=files,hardware_metadata=metadata,
                    camera_connected=stats.get('camera_connected'),fps=stats.get('fps'),
                    utc_now=datetime.datetime.now(datetime.timezone.utc).isoformat(),clock_delta_seconds=clock_delta,clock_check=clock_ok,
                    model_scope='reuse frozen known-working OM; ATC provenance still required for replacement')
        write_json(self.session/'probe.json',result);self.set_step(1,status)
        return result

    def recover_off(self):
        pending=self.session/'recovery-pending.json';mode=self.mode_reader()
        if DROPIN.exists() and not owns_dropin(DROPIN.read_text(),self.session): raise ValueError('foreign_runtime_dropin_refused')
        if mode=='foreign':raise ValueError('foreign_running_care_configuration_refused')
        if not DROPIN.exists() and not pending.exists() and mode!='shadow_owned':
            return dict(status='NO_CHANGE',reason='no_owned_override; actual_mode_'+mode)
        if pending.exists() and read_json(pending).get('config')!=str(self.session/'config.json'):
            raise ValueError('foreign_pending_recovery_refused')
        write_json(pending,dict(status='pending',config=str(self.session/'config.json')))
        if DROPIN.exists():DROPIN.unlink()
        self.runner(['systemctl','daemon-reload'])
        if self.mode_reader()!='off':self.runner(['systemctl','restart',SERVICE])
        if self.mode_reader()!='off':raise ValueError('off_not_confirmed; recovery remains pending')
        result=dict(status='PASS',restored_off=True)
        write_json(self.session/'readykit-off-result.json',result)
        (self.session/'finish.request').write_text('actual off confirmed')
        pending.unlink(missing_ok=True)
        return result

    def _arm_watchdog(self):
        marker=self.session/'watchdog-armed.json'
        process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'watchdog','--session',str(self.session),'--app-root',str(self.app_root)],
                                 stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if marker.exists() and read_json(marker).get('pid')==process.pid and process.poll() is None:return
            if process.poll() is not None:break
            time.sleep(0.1)
        raise ValueError('watchdog_not_confirmed; temporary override not enabled')

    def start_shadow(self, quiet=False, fast_demo=False, audio_demo=False):
        if audio_demo and not fast_demo:raise ValueError('audio_demo_requires_fast_demo')
        self.probe()  # Cached yesterday's PASS must not authorize today's write.
        require_steps(self.ledger(),2)
        if (self.session/'config.json').exists() or DROPIN.exists(): raise ValueError('existing_session_must_be_reviewed_and_closed')
        current=read_json(self.session/'probe.json')
        if current['care_mode']!='off' or current.get('care_config_present'): raise ValueError('existing_care_mode_requires_review')
        backup=self.session/'backup';backup.mkdir(mode=0o700)
        registry=self.app_root/'db/guardian.db'
        (backup/'service-unit.txt').write_text(self.runner(['systemctl','cat',SERVICE]))
        pid=self.runner(['systemctl','show',SERVICE,'-p','MainPID','--value'])
        environment=Path('/proc/'+pid+'/environ').read_bytes()
        (backup/'process-environment.bin').write_bytes(environment)
        env=dict(x.split(b'=',1) for x in environment.split(b'\0') if b'=' in x)
        databases={registry};configurations=[]
        for key,value in env.items():
            if key.startswith(b'AI_GUARDIAN_') and key.endswith(b'_CONFIG'):
                path=Path(os.fsdecode(value))
                if path.is_file():
                    configurations.append(path)
                    original=read_json(path)
                    if original.get('data_root'):
                        databases.update((Path(original['data_root'])/'db').glob('*.db'))
        code_hashes={}
        for name in read_json(BASELINE)['expected_files']:
            path=self.app_root/name;dest=backup/'code'/name;dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(path,dest);code_hashes[name]=fingerprint(dest)
            if code_hashes[name]!=fingerprint(path): raise ValueError('original_code_changed_during_backup')
        for index,path in enumerate(configurations): shutil.copy2(path,backup/('private-config-%d'%index))
        for index,path in enumerate(sorted(databases)): backup_sqlite(path,backup/('database-%d.sqlite'%index))
        write_json(backup/'manifest.json',dict(status='verified',code_hashes=code_hashes,databases=len(databases),private_configs=len(configurations)))
        db=sqlite3.connect(registry.resolve().as_uri()+'?mode=ro',uri=True)
        try: people=db.execute('SELECT user_id,name FROM t_face_feature ORDER BY user_id').fetchall()
        finally: db.close()
        if not 1<=len(people)<=32 or len(set(name for _,name in people))!=len(people): raise ValueError('missing_or_ambiguous_local_identity')
        machine=dict(l0_seconds=2 if fast_demo else 15,upgrade_seconds=3 if fast_demo else 10,repeat_seconds=5 if fast_demo else 10)
        if not quiet: machine.update(quiet_start=None,quiet_end=None)
        config=dict(mode='shadow',sync_enabled=False,db_path='isolated/care.db',person_ids=[p[0] for p in people],
                    face_label_ids={p[1]:p[0] for p in people},model_version='acceptance-'+secrets.token_hex(8),
                    region_id='unknown',machine=machine)
        validate_test_config(config)
        write_json(self.session/'config.json',config)
        detector_environment=dict(DEMO_DETECTOR_ENV) if fast_demo else {}
        audio_environment=dict(DEMO_AUDIO_ENV) if audio_demo else {}
        write_json(self.session/'test-profile.json',dict(name='fast-demo' if fast_demo else 'acceptance',machine=machine,detector_environment=detector_environment,audio_environment=audio_environment))
        write_json(self.session/'roles.json',{p[0]:'P%d'%(i+1) for i,p in enumerate(people)})
        token=secrets.token_hex(32);(self.session/'token').write_text(token);(self.session/'token').chmod(0o600)
        content='[Service]\nEnvironment=AI_GUARDIAN_CARE_CONFIG='+str(self.session/'config.json')+'\nEnvironment=AI_GUARDIAN_CARE_API_TOKEN='+token+'\n'
        content+=''.join('Environment='+key+'='+value+'\n' for key,value in detector_environment.items())
        content+=''.join('Environment='+key+'='+value+'\n' for key,value in audio_environment.items())
        DROPIN.parent.mkdir(parents=True,exist_ok=True)
        self._arm_watchdog()  # Confirm detached recovery BEFORE enabling override.
        try:
            with DROPIN.open('x') as stream: stream.write(content)
            DROPIN.chmod(0o600);self.runner(['systemctl','daemon-reload']);self.runner(['systemctl','restart',SERVICE])
            self.wait_ready()
            return dict(status='PASS',mode='shadow',sync_enabled=False,trigger_profile='fast-demo' if fast_demo else 'acceptance',accelerated_profile=machine,detector_environment=detector_environment,audio_environment=audio_environment,restore_off_after_seconds=1800)
        except BaseException:
            if DROPIN.exists() and owns_dropin(DROPIN.read_text(),self.session): self.recover_off()
            raise

    def wait_ready(self):
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            try:
                data=self.http('/api/care/shadow-report')
                if data.get('mode')=='shadow': return data
            except (OSError,ValueError): pass
            time.sleep(1)
        raise ValueError('shadow_not_ready; preserve logs and restore owned off configuration')

    def sample(self):
        config=read_json(self.session/'config.json');validate_test_config(config)
        roles=read_json(self.session/'roles.json');stats=self.http('/api/stats')
        phase=read_json(self.session/'phase.json') if (self.session/'phase.json').exists() else dict(name='baseline',confirmed=False,role=None)
        row=dict(observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),sample_monotonic=time.monotonic(),session_id=config['model_version'],
                 phase=phase['name'],confirmed_action=phase['confirmed'],actor_role=phase.get('role'),sensor={k:stats.get(k) for k in ('camera_connected','fps','frame_count','detections','sit_duration')},states={})
        labels=[stats.get('face_label')]+[x.get('label') or x.get('face_label') for x in stats.get('faces',[])]
        visible={config['face_label_ids'][x[6:]] for x in labels if isinstance(x,str) and x.startswith('known:') and x[6:] in config['face_label_ids']}
        row['recognized_roles']=sorted(roles[p] for p in visible)
        for person in config['person_ids']:
            result=self.http(self.scope(config,person)+'/events')
            state=sanitize_state(result['state'],roles[person]);state['event_ids']=[e['event_id'] for e in result['events']]
            row['states'][roles[person]]=state
        result=self.http('/api/care/shadow-report');row['shadow_mode']=result['mode']
        row['broadcasts']=[]
        for item in result.get('broadcasts',[]):
            value={k:v for k,v in item.items() if k!='person_id'};value['role']=roles.get(item['person_id'],'unmapped');row['broadcasts'].append(value)
        database=isolated_database(config,self.session)
        db=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
        try:
            total=0
            for person in config['person_ids']:
                total+=db.execute('SELECT COUNT(*) FROM care_outbox WHERE person_id=? AND model_version=?',(person,config['model_version'])).fetchone()[0]
            row['live_outbox_rows']=total
        finally: db.close()
        return row

    def resource_observe(self, seconds, formal=False):
        require_steps(self.ledger(),6 if formal else 2)
        if not 1<=seconds<=1800: raise ValueError('observation_duration_must_be_1_to_1800')
        rows=[];end=time.monotonic()+seconds
        while time.monotonic()<end:
            row=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat())
            try:
                pid=self.runner(['systemctl','show',SERVICE,'-p','MainPID','--value'])
                if not pid.isdigit() or pid=='0': raise ValueError('service_not_running')
                status=Path('/proc/'+pid+'/status').read_text()
                for field in ('VmRSS','VmHWM','Threads'):
                    match=re.search(r'^'+field+r':\s+(\d+)',status,re.M)
                    row[field]=int(match.group(1)) if match else None
                stats=self.http('/api/stats');row['sensor']={k:stats.get(k) for k in ('camera_connected','fps','frame_count')}
                row['cpu_stat']=Path('/proc/'+pid+'/stat').read_text().rsplit(') ',1)[1].split()[11:13]
                row['thermal_millidegrees']={p.parent.name:int(p.read_text()) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')}
            except (OSError,ValueError,subprocess.SubprocessError) as exc: row['error']=type(exc).__name__
            rows.append(row);time.sleep(1)
        result=dict(status='INCOMPLETE' if formal or any('error' in r for r in rows) else 'PASS',
                    scope='measurements only; no resource SLA was supplied',samples=rows)
        write_json(self.session/('step6-resources.json' if formal else 'off-resources.json'),result)
        return result

    @staticmethod
    def scope(config, person):
        return '/api/care/'+urllib.parse.quote(config['model_version'],safe='')+'/'+urllib.parse.quote(person,safe='')

    def observe(self, seconds):
        if not 1<=seconds<=1800: raise ValueError('observation_duration_must_be_1_to_1800')
        deadline=time.monotonic()+seconds;rows=[];seen=set()
        while time.monotonic()<deadline:
            try: row=self.sample()
            except Exception as exc: row=dict(error=type(exc).__name__,sample_monotonic=time.monotonic())
            fresh=[]
            for message in row.get('broadcasts',[]):
                key=(message['event_id'],message['revision'])
                if key not in seen: fresh.append(message);seen.add(key)
            row['broadcasts']=fresh
            with (self.session/'observations.jsonl').open('a',encoding='utf-8',newline='\n') as stream:
                stream.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
            rows.append(row);time.sleep(1)
        return dict(status='PASS' if all('error' not in row for row in rows) else 'FAIL',samples=len(rows),last=rows[-1])

    def assess(self, other_sessions=()):
        rows=[];restarts=[]
        for folder in [self.session]+list(map(Path,other_sessions)):
            if (folder/'observations.jsonl').is_file(): rows += [json.loads(line) for line in (folder/'observations.jsonl').read_text(encoding='utf-8').splitlines() if line]
            for p in folder.glob('restart-*.json'): restarts.append(read_json(p))
        result=assess_shadow(rows,restarts);write_json(self.session/'step2-assessment.json',result)
        self.set_step(2,result['status']);return result

    def restart_case(self, kind, role):
        require_steps(self.ledger(),2)
        if kind not in ('short','long'): raise ValueError('invalid_restart_kind')
        path=self.session/('restart-'+kind+'.json')
        pending=dict(status='INCOMPLETE',kind=kind,role=role,stage='preflight',
                     started_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        write_json(path,pending)  # A failed rerun must never leave yesterday's PASS.
        try:
            config=read_json(self.session/'config.json');validate_test_config(config)
            if not DROPIN.exists() or not owns_dropin(DROPIN.read_text(),self.session): raise ValueError('only_owned_shadow_service_may_restart')
            return self._restart_case(kind,role,path,pending)
        except Exception as exc:
            pending['error_type']=type(exc).__name__;write_json(path,pending)
            raise

    def _restart_case(self, kind, role, path, pending):
        sample=self.sample()
        if role=='auto':
            role=visible_actor(sample)
        before=sample['states'].get(role)
        if not before or before['seated_seconds']<=0: raise ValueError('active_real_sitting_sample_required')
        if role not in sample['recognized_roles']: raise ValueError('visible_actor_required')
        if kind=='short' and before.get('counts')!={'L0':1,'L1':2}:
            raise ValueError('exhausted_reminders_required_before_short_restart')
        pending.update(stage='stopping',role=role,before=before);write_json(path,pending)
        self.runner(['systemctl','stop',SERVICE])
        try:
            time.sleep(5 if kind=='short' else 130)
        finally: self.runner(['systemctl','start',SERVICE])
        pending['stage']='recovering';write_json(path,pending)
        self.wait_ready();recovery=self.sample()
        pending['stage']='observing';write_json(path,pending)
        observation=self.observe(35);final=self.sample()
        restored=recovery['states'].get(role,{});after=final['states'].get(role,{})
        stamps=[row.get('sample_monotonic') for row in (sample,recovery,final)]
        measured=all(isinstance(t,(int,float)) and not isinstance(t,bool) and math.isfinite(t) for t in stamps)
        gap=stamps[1]-stamps[0] if measured else None
        timing=measured and stamps[2]>=stamps[1] and (5<=gap<120 if kind=='short' else gap>=120)
        visible=all(role in row.get('recognized_roles',[]) for row in (recovery,final))
        evidence=timing and visible and observation.get('status')=='PASS' and bool(restored) and bool(after)
        same=lambda state:bool(before.get('event_ids')) and before['event_ids'][-1:]==state.get('event_ids',[])[-1:]
        if kind=='short':
            passed=all(same(s) and s.get('counts')==before['counts'] and s.get('seated_seconds',0)>=before['seated_seconds']-0.3 for s in (restored,after))
        else: passed=not same(after) and bool(after.get('event_ids')) and after.get('seated_seconds',0)>0
        result=dict(status=('PASS' if passed else 'FAIL') if evidence else 'INCOMPLETE',kind=kind,role=role,
                    before=before,recovery=restored,after=after,recovery_gap_seconds=gap,
                    sample_monotonic=stamps,checks=dict(timing=bool(timing),visible_actor=visible,
                    observation=observation.get('status'),event_and_counts=passed))
        write_json(path,result);return result

    def feedback_case(self, role='auto'):
        require_steps(self.ledger(),3)
        config=read_json(self.session/'config.json');validate_test_config(config)
        isolated_database(config,self.session)
        if not DROPIN.exists() or not owns_dropin(DROPIN.read_text(),self.session): raise ValueError('owned_shadow_configuration_required')
        roles=read_json(self.session/'roles.json')
        if role=='auto':
            candidates=[p for p in config['person_ids'] if self.http(self.scope(config,p)+'/events')['events']]
            if len(candidates)!=1: raise ValueError('specify_unique_role_with_real_events')
            person=candidates[0]
        else:
            candidates=[p for p,label in roles.items() if label==role]
            if len(candidates)!=1: raise ValueError('unknown_role')
            person=candidates[0]
        base=self.scope(config,person)
        events=self.http(base+'/events')['events']
        if not events: raise ValueError('real_event_required; no synthetic replacement permitted')
        identity=events[-1]['event_id'];path=base+'/events/'+urllib.parse.quote(identity,safe='')+'/feedback'
        a=self.http(path,'POST',dict(payload=dict(confirmed=True,label='confirmed')))
        b=self.http(path,'POST',dict(payload=dict(confirmed=False,label='false_alarm')))
        if a['created_at']!=b['created_at'] or b['revision']<=a['revision']: raise ValueError('feedback_update_contract_failed')
        active=self.http(base+'/feedback')['feedback']
        if sum(r['target_id']==identity for r in active)!=1: raise ValueError('feedback_not_deduplicated')
        self.http(path,'POST',dict(operation='revoke',reason='isolated acceptance'))
        if any(r['target_id']==identity for r in self.http(base+'/feedback')['feedback']): raise ValueError('revoked_feedback_visible')
        audit=self.http(base+'/feedback?status=revoked')['feedback']
        if not any(r['target_id']==identity for r in audit): raise ValueError('revoked_feedback_not_auditable')
        checks={}
        negatives=[('wrong_token',base+'/events','invalid-test-token'),('missing_token',base+'/events',False),
                   ('wrong_model','/api/care/not-this-model/'+urllib.parse.quote(person,safe='')+'/events',None),
                   ('wrong_person','/api/care/'+urllib.parse.quote(config['model_version'],safe='')+'/not-this-person/events',None)]
        for key,target,token in negatives:
            try:self.http(target,token=token);checks[key]=False
            except urllib.error.HTTPError as exc:checks[key]=exc.code==(404 if key in ('wrong_model','wrong_person') else 401)
        if not all(checks.values()): raise ValueError('feedback_authorization_failed')
        result=dict(status='INCOMPLETE',board_api='PASS',permission_checks=checks,
                    remaining=['real_MP4_playback_and_shared_clip','App_issue_25_end_to_end'],event_id=identity)
        write_json(self.session/'step3-feedback.json',result);self.set_step(3,'INCOMPLETE');return result

    def media_case(self):
        require_steps(self.ledger(),3)
        config=read_json(self.session/'config.json');isolated_database(config,self.session)
        care_ids={event['event_id'] for person in config['person_ids'] for event in self.http(self.scope(config,person)+'/events')['events']}
        pid=self.runner(['systemctl','show',SERVICE,'-p','MainPID','--value'])
        env=dict(x.split(b'=',1) for x in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0') if b'=' in x)
        token=env.get(b'AI_GUARDIAN_HISTORY_TOKEN')
        if not token: return dict(status='BLOCKED',reason='original_history_token_not_configured; never substitute face token')
        token=os.fsdecode(token)
        history=self.http('/api/history/events?limit=20',token=token)
        links={}
        for event in history.get('items',[]):
            if event['id'] not in care_ids: continue
            for clip in event.get('recordings',[]): links.setdefault(clip['id'],set()).add(event['id'])
        if not links: return dict(status='INCOMPLETE',reason='no real care-ID-linked recording; expected in shadow, do not relink legacy IDs or create fake video')
        recording=max(links,key=lambda key:len(links[key]));folder=self.session/'private-media';folder.mkdir(exist_ok=True,mode=0o700)
        # Generated opaque clip ID is used only inside the validated API path.
        request=urllib.request.Request('http://127.0.0.1:5000/api/history/recordings/'+urllib.parse.quote(recording,safe='')+'/video',headers={'Authorization':'Bearer '+token})
        target=folder/'actual-recording.mp4';limit=64*1024*1024;total=0
        with urllib.request.urlopen(request,timeout=20) as response, target.open('wb') as stream:
            while True:
                block=response.read(1048576)
                if not block: break
                total+=len(block)
                if total>limit: raise ValueError('media_exceeds_64MiB_review_manually')
                stream.write(block)
        result=dict(status='INCOMPLETE',download_bytes=total,history_linked_events=len(links[recording]),linked_event_ids=sorted(links[recording]))
        if not shutil.which('ffmpeg'): result['decode']='BLOCKED_ffmpeg_missing; no dependency installation'
        else:
            decoded=subprocess.run(['ffmpeg','-v','error','-threads','1','-i',str(target),'-t','5','-an','-f','null','-'],capture_output=True,timeout=45)
            result['decode']='PASS' if decoded.returncode==0 else 'FAIL'
            (folder/'decode-private.log').write_bytes(decoded.stderr)
        result['remaining']=['operator_playback_confirmation','care_event_to_real_clip_link_not_exercised_in_shadow','App_issue_25']
        write_json(self.session/'step3-media.json',result);return result

    def weekly_fixture(self):
        require_steps(self.ledger(),4)
        # Strictly isolated standard-library cases; never original personal data.
        command=[sys.executable,'-m','unittest','test_weekly_report.WeeklyTests','-v']
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        (self.session/'weekly-fixture.log').write_text(result.stdout+result.stderr,encoding='utf-8')
        config=read_json(self.session/'config.json')
        isolated_database(config,self.session)
        if not config.get('weekly_enabled'):
            status='INCOMPLETE';reason='real_weekly_api_disabled; enable only in a new backed-up test profile'
        else:
            person=config['person_ids'][0]
            day=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
            monday=day-datetime.timedelta(days=day.weekday())
            data=self.http(self.scope(config,person)+'/weekly?week_start='+monday.isoformat())
            status='PASS' if result.returncode==0 and isinstance(data.get('groups'),list) else 'FAIL';reason='fixture_and_actual_structured_api'
        value=dict(status=status,fixture_exit=result.returncode,reason=reason,
                   remaining='actual retention and personal-delete require isolated session confirmation')
        write_json(self.session/'step4-weekly.json',value);self.set_step(4,'INCOMPLETE' if status=='PASS' else status);return value

    def enable_weekly(self):
        require_steps(self.ledger(),4)
        config=read_json(self.session/'config.json');database=isolated_database(config,self.session)
        if not DROPIN.exists() or not owns_dropin(DROPIN.read_text(),self.session): raise ValueError('owned_shadow_configuration_required')
        backup_sqlite(database,self.session/('before-weekly-'+secrets.token_hex(4)+'.sqlite'))
        config.update(weekly_enabled=True,weekly_regions=['unknown'])
        write_json(self.session/'config.json',config);self.runner(['systemctl','restart',SERVICE]);self.wait_ready()
        return dict(status='PASS',weekly_enabled=True,original_data_untouched=True)

    def weekly_lifecycle(self, role='auto'):
        require_steps(self.ledger(),4)
        config=read_json(self.session/'config.json');database=isolated_database(config,self.session)
        backup_sqlite(database,self.session/('before-erase-'+secrets.token_hex(4)+'.sqlite'))
        # API erase affects only this generated model in this isolated SQLite DB.
        roles=read_json(self.session/'roles.json')
        candidates=[p for p in config['person_ids'] if (role=='auto' or roles[p]==role) and self.http(self.scope(config,p)+'/events')['events']]
        if len(candidates)!=1: raise ValueError('unique_test_role_with_actual_events_required')
        person=candidates[0];base=self.scope(config,person)
        if not config.get('weekly_enabled'): raise ValueError('enable_weekly_first')
        before=self.http(base+'/events')['events']
        self.http(base+'/weekly-policy','PUT',dict(retention_days=1,min_samples=30))
        self.http(base+'/data','DELETE')
        self.runner(['systemctl','restart',SERVICE]);self.wait_ready()
        after=self.http(base+'/events')['events']
        if after: raise ValueError('erased_subject_recreated_after_restart')
        self.http(base+'/data/resume','POST',{})
        result=dict(status='INCOMPLETE',role=roles[person],erased_event_ids=[e['event_id'] for e in before],erased_events=len(before),erasure_survived_restart=True,
                    resume_requested=True,remaining=['observe_real_recollection_after_resume','retention_fixture_result'])
        write_json(self.session/'step4-lifecycle.json',result);return result

    def complete_step(self, number, proof=None):
        """Operator evidence is explicit; absent prerequisites never become PASS."""
        require_steps(self.ledger(),number)
        if number==2: return self.assess()
        evidence=read_json(proof) if proof else {}
        if number==3:
            feedback=read_json(self.session/'step3-feedback.json')
            media=read_json(self.session/'step3-media.json')
            passed=(feedback.get('board_api')=='PASS' and media.get('decode')=='PASS'
                    and media.get('history_linked_events',0)>=2
                    and feedback['event_id'] in media.get('linked_event_ids',[])
                    and evidence.get('real_app') is True and evidence.get('played_on_client') is True
                    and evidence.get('app_event_id')==feedback['event_id']
                    and evidence.get('board_event_id')==feedback['event_id']
                    and evidence.get('app_revoke_confirmed') is True)
            remaining=['App #25 and actual care-ID/MP4/client playback proof required']
        elif number==4:
            fixture=read_json(self.session/'step4-weekly.json');lifecycle=read_json(self.session/'step4-lifecycle.json')
            config=read_json(self.session/'config.json');roles=read_json(self.session/'roles.json')
            person=next(p for p in config['person_ids'] if roles[p]==lifecycle['role'])
            events=self.http(self.scope(config,person)+'/events')['events']
            passed=(fixture['fixture_exit']==0 and lifecycle.get('erasure_survived_restart') is True
                    and lifecycle.get('resume_requested') is True and bool(events)
                    and not ({e['event_id'] for e in events}&set(lifecycle.get('erased_event_ids',[])))
                    and evidence.get('real_region_mapping_confirmed') is True)
            remaining=['actual recollection and coarse-region/timezone operator confirmation required']
        else:
            passed=False
            remaining=['real care audio/response/arbitration and receiver APIs are not implemented in the current baseline; do not override the gate']
        status='PASS' if passed else 'INCOMPLETE'
        result=dict(status=status,step=number,remaining=[] if passed else remaining)
        write_json(self.session/('step%d-signoff.json'%number),result);self.set_step(number,status)
        return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('offline','pack','probe','baseline-resources','stability','recover-off','start-shadow','mark','observe','assess2','restart-case','feedback','media','enable-weekly','weekly-fixture','weekly-lifecycle','complete-step','audio-readiness','rollback-readiness','code-rollback','watchdog'))
    parser.add_argument('--session',type=Path,default=Path('/root/guardian-care-staging/care-validation-20261117'))
    parser.add_argument('--app-root',type=Path,default=Path('/root/ai_guardian'))
    parser.add_argument('--output',type=Path,default=Path('.tmp/board-ready-kit'))
    parser.add_argument('--phase',choices=PHASES,default='baseline')
    parser.add_argument('--confirmed-action',action='store_true')
    parser.add_argument('--seconds',type=int,default=50)
    parser.add_argument('--kind',choices=('short','long'),default='short')
    parser.add_argument('--role',default='auto')
    parser.add_argument('--reference-time',type=float)
    parser.add_argument('--quiet',action='store_true')
    parser.add_argument('--fast-demo',action='store_true')
    parser.add_argument('--audio-demo',action='store_true')
    parser.add_argument('--step',type=int,choices=(2,3,4,5,6))
    parser.add_argument('--proof',type=Path)
    parser.add_argument('--include-session',type=Path,action='append',default=[])
    parser.add_argument('--flat-backup',type=Path,default=Path('/root/guardian-preflight-backups/20261116-env-adapt-135914/overlay'))
    parser.add_argument('--identity-backup',type=Path,default=Path('/root/guardian-care-staging/shadow-acceptance-20261116/pre-shadow-backup'))
    args=parser.parse_args(argv)
    if (args.fast_demo or args.audio_demo) and args.action!='start-shadow': parser.error('demo options only apply to start-shadow')
    if args.action=='offline': result=offline_audit(ROOT,args.output)
    elif args.action=='pack': result=build_kit(ROOT,args.output)
    else:
        if platform.system()!='Linux': raise ValueError('device_actions_require_target_Linux; use offline or pack here')
        device=DeviceRun(args.session,args.app_root,reference_time=args.reference_time)
        if args.action=='probe': result=device.probe()
        elif args.action in ('baseline-resources','stability'): result=device.resource_observe(args.seconds,args.action=='stability')
        elif args.action=='recover-off': result=device.recover_off()
        elif args.action=='start-shadow': result=device.start_shadow(args.quiet,args.fast_demo or args.audio_demo,args.audio_demo)
        elif args.action=='mark':
            role=args.role
            if role=='auto':
                role=visible_actor(device.sample())
            write_json(device.session/'phase.json',dict(name=args.phase,confirmed=args.confirmed_action,role=role));result=dict(status='RECORDED',phase=args.phase,role=role)
        elif args.action=='observe': result=device.observe(args.seconds)
        elif args.action=='assess2': result=device.assess(args.include_session)
        elif args.action=='restart-case': result=device.restart_case(args.kind,args.role)
        elif args.action=='feedback': result=device.feedback_case(args.role)
        elif args.action=='media': result=device.media_case()
        elif args.action=='enable-weekly': result=device.enable_weekly()
        elif args.action=='weekly-fixture': result=device.weekly_fixture()
        elif args.action=='weekly-lifecycle': result=device.weekly_lifecycle(args.role)
        elif args.action=='complete-step':
            if args.step is None: parser.error('--step required')
            result=device.complete_step(args.step,args.proof)
        elif args.action=='audio-readiness':
            require_steps(device.ledger(),5)
            result=dict(status='BLOCKED',reasons=['real_care_audio_adapter_missing','response_input_and_intercom_arbitration_unverified','receiver_end_to_end_not_ready'])
            write_json(device.session/'step5-audio.json',result)
        elif args.action=='rollback-readiness':
            require_steps(device.ledger(),6)
            result=rollback_plan(device.app_root,args.flat_backup,args.identity_backup)
            write_json(device.session/'step6-rollback-plan.json',result)
        elif args.action=='code-rollback': result=code_rollback(device,args.flat_backup,args.identity_backup)
        else:
            write_json(device.session/'watchdog-armed.json',dict(pid=os.getpid(),status='armed'))
            end=time.monotonic()+1800
            while True:
                if (device.session/'finish.request').exists() and not (device.session/'recovery-pending.json').exists():
                    result=dict(status='NO_CHANGE',reason='recovery_already_confirmed');break
                if time.monotonic()>=end or (device.session/'recovery-pending.json').exists():
                    try:
                        result=device.recover_off()
                        if result['status'] in ('PASS','NO_CHANGE') and device.mode_reader()=='off':break
                    except (OSError,ValueError,subprocess.SubprocessError) as exc:
                        write_json(device.session/'watchdog-last-error.json',dict(error=type(exc).__name__,status='retrying'))
                time.sleep(2)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False))
    return 0 if result['status'] in ('PASS','NO_CHANGE','RECORDED') else 2


if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,OSError,KeyError,sqlite3.Error,subprocess.SubprocessError) as exc:
        # Error text is limited to our own codes; never dump tokens or HTTP bodies.
        print(json.dumps(dict(status='BLOCKED',error=type(exc).__name__,reason=str(exc) if isinstance(exc,ValueError) else 'inspect private environment/evidence')),file=sys.stderr)
        raise SystemExit(2)
