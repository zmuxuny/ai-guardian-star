"""AF-01 three-file release. Never starts services, changes SDKs or restores data."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid
import zipfile

FILES=('guardian_runtime.py','ascend_main_other.py','care_runtime.py')
ANCHOR=b'                "sit_duration_sec": sit_duration_sec,\n'
INSERT=(b'                "care_observation": (timer.care_observation(now_ts, VLM_LONG_SIT_THRESHOLD_SECONDS)\n'
        b'                                     if timer is not None else "unreliable"),\n')


def digest(data):return hashlib.sha256(data).hexdigest()


def patch_native(data):
    newline=b'\r\n' if b'\r\n' in data else b'\n'
    anchor=ANCHOR.replace(b'\n',newline);insert=INSERT.replace(b'\n',newline)
    if data.count(anchor)!=1:raise ValueError('native_alert_anchor_not_unique')
    before=ast.parse(data);candidate=data.replace(anchor,anchor+insert,1);after=ast.parse(candidate)
    removed=0
    for node in ast.walk(after):
        if isinstance(node,ast.Dict):
            for index in range(len(node.keys)-1,-1,-1):
                if isinstance(node.keys[index],ast.Constant) and node.keys[index].value=='care_observation':
                    del node.keys[index];del node.values[index];removed+=1
    if removed!=1 or ast.dump(before)!=ast.dump(after):raise ValueError('native_patch_not_additive')
    compile(candidate,'ascend_main_other.py','exec')
    return candidate


def pack_patch(repo, originals, baseline, output, revision):
    repo,originals,output=map(Path,(repo,originals,output))
    rows=[];blobs={}
    for name in FILES:
        original=(originals/name).read_bytes()
        if digest(original)!=baseline['expected_files'][name]:raise ValueError('unreviewed_device_file')
        data=patch_native(original) if name=='ascend_main_other.py' else (repo/'src'/name).read_bytes()
        compile(data,name,'exec');blobs['payload/'+name]=data
        rows.append(dict(path=name,before_sha256=digest(original),sha256=digest(data)))
    manifest=dict(kind='care-af01-patch',schema_version=1,revision=revision,files=rows)
    blobs['manifest.json']=(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name,data in sorted(blobs.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return manifest


def _rows(manifest):
    rows=manifest.get('files',[])
    if (manifest.get('kind')!='care-af01-patch' or manifest.get('schema_version')!=1
            or len(rows)!=3 or {r['path'] for r in rows}!=set(FILES)):
        raise ValueError('unknown_patch_manifest')
    for row in rows:
        for key in ('before_sha256','sha256'):
            value=row[key]
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):
                raise ValueError('invalid_fingerprint')
    return {row['path']:row for row in rows}


def _roots(app_root, backup):
    app_root,backup=Path(app_root),Path(backup)
    if app_root.is_symlink() or backup.is_symlink() or not app_root.is_dir():raise ValueError('unsafe_root')
    app_root,backup=app_root.resolve(),backup.resolve()
    if app_root==backup or app_root in backup.parents or backup in app_root.parents:
        raise ValueError('backup_must_be_outside_application')
    for name in FILES:
        if (app_root/name).is_symlink() or not (app_root/name).is_file():raise ValueError('unsafe_target')
    return app_root,backup


def service_stopped():
    result=subprocess.run(['systemctl','is-active','guardian-board.service'],capture_output=True,text=True)
    return result.returncode==3 and result.stdout.strip()=='inactive'


def _replace(path, data):
    temp=path.with_name(path.name+'.af01-'+uuid.uuid4().hex)
    try:
        with temp.open('xb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        temp.chmod(path.stat().st_mode & 0o777);os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()


def apply_patch(app_root, bundle, backup, *, stopped=service_stopped):
    if not stopped():raise ValueError('service_must_be_stopped')
    app_root,backup=_roots(app_root,backup)
    with zipfile.ZipFile(bundle) as archive:
        manifest=json.loads(archive.read('manifest.json'));rows=_rows(manifest)
        names=['manifest.json']+['payload/'+name for name in FILES]
        if len(archive.namelist())!=4 or set(archive.namelist())!=set(names):raise ValueError('unexpected_package_files')
        payload={name:archive.read('payload/'+name) for name in FILES}
    for name in FILES:
        if digest(payload[name])!=rows[name]['sha256']:raise ValueError('payload_changed')
        if digest((app_root/name).read_bytes())!=rows[name]['before_sha256']:raise ValueError('device_changed')
        compile(payload[name],name,'exec')
    backup.mkdir(mode=0o700,parents=True,exist_ok=False)
    for name in FILES:
        shutil.copy2(app_root/name,backup/name)
        with (backup/name).open('r+b') as stream:os.fsync(stream.fileno())
        if digest((backup/name).read_bytes())!=rows[name]['before_sha256']:raise ValueError('backup_verification_failed')
    with (backup/'manifest.json').open('x',encoding='utf-8') as stream:
        json.dump(manifest,stream,sort_keys=True,indent=2);stream.flush();os.fsync(stream.fileno())
    # The service must remain stopped throughout a non-atomic multi-file patch.
    # A process interruption is recoverable from this immutable backup manifest.
    for name in FILES:
        if not stopped():raise ValueError('service_started_during_patch')
        if (app_root/name).is_symlink() or digest((app_root/name).read_bytes())!=rows[name]['before_sha256']:
            raise ValueError('device_changed_after_backup')
        _replace(app_root/name,payload[name])
        if digest((app_root/name).read_bytes())!=rows[name]['sha256']:raise ValueError('installed_hash_mismatch')
    return dict(status='PASS',files=3,database_action='untouched',backup_verified=True)


def rollback(app_root, backup, *, stopped=service_stopped):
    if not stopped():raise ValueError('service_must_be_stopped')
    app_root,backup=_roots(app_root,backup)
    rows=_rows(json.loads((backup/'manifest.json').read_text(encoding='utf-8')))
    for name in FILES:
        if digest((backup/name).read_bytes())!=rows[name]['before_sha256']:raise ValueError('backup_changed')
        if digest((app_root/name).read_bytes()) not in (rows[name]['before_sha256'],rows[name]['sha256']):
            raise ValueError('post_patch_edit_requires_review')
    for name in reversed(FILES):
        if not stopped():raise ValueError('service_started_during_rollback')
        _replace(app_root/name,(backup/name).read_bytes())
    return dict(status='PASS',files=3,database_action='untouched')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('pack','apply','rollback'))
    parser.add_argument('--app-root',type=Path,default=Path('/root/ai_guardian'))
    parser.add_argument('--originals',type=Path);parser.add_argument('--baseline',type=Path)
    parser.add_argument('--bundle',type=Path);parser.add_argument('--backup',type=Path)
    parser.add_argument('--revision',default='unversioned')
    args=parser.parse_args()
    if args.action=='pack':
        if not args.originals or not args.baseline or not args.bundle:parser.error('pack requires originals, baseline, bundle')
        result=pack_patch(Path(__file__).resolve().parents[1],args.originals,json.loads(args.baseline.read_text(encoding='utf-8')),args.bundle,args.revision)
    else:
        if not args.backup:parser.error('backup required')
        if args.action=='apply':
            if not args.bundle:parser.error('bundle required')
            result=apply_patch(args.app_root,args.bundle,args.backup)
        else:result=rollback(args.app_root,args.backup)
    print(json.dumps(result,sort_keys=True))


if __name__=='__main__':main()
