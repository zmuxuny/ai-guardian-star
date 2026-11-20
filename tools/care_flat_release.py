"""Device-reviewed, flat-layout overlay. Never changes launchers, SDKs or data.

Pack on the development host using the privately reviewed device entry. Apply
only while the operator has stopped the service after its full private backup.
Conflicts, changed dependencies and post-review drift are rejected, not hidden.
"""
import argparse
import ast
import json
import os
import uuid
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile

if __package__ in (None, ''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.care_release import ROOT, BASELINE, _git, _safe, digest, REQUIRES as SOURCE_REQUIRES

MODULES = ('sedentary_care','local_care_store','local_care_migrations','shadow_mode',
           'region_aggregation','care_runtime','care_delivery_store','care_api',
           'care_transport','weekly_store','weekly_report','posture_features','personal_baseline_store','personal_baseline')
MIGRATIONS = ('001_initial.sql','002_baseline_source.sql','003_delivery.sql','004_weekly.sql','005_personal_baseline.sql')
REQUIRES = tuple(p for p in SOURCE_REQUIRES if p != 'src/region_aggregation.py')
ENTRY = 'ascend_board_server.py'
PATHS = tuple(m+'.py' for m in MODULES) + tuple('migrations/local_care/'+s for s in MIGRATIONS) + (ENTRY,)
HEX = re.compile(r'[0-9a-f]{64}')


def safe(root,name):
    path=_safe(root,name)
    cursor=root
    for part in Path(name).parts:
        cursor=cursor/part
        if cursor.is_symlink():
            raise ValueError('symlink is not permitted in an overlay path')
    return path


def app_directory(value):
    root=Path(value)
    if root.is_symlink() or not root.is_dir():
        raise ValueError('use an existing nonsymlink application directory')
    return root.resolve()


def pack_flat(output,device_entry,*,require_clean=True):
    if require_clean and _git('status','--porcelain').strip():
        raise ValueError('commit verified work before packing')
    device=Path(device_entry).read_bytes()
    baseline=_git('show',BASELINE+':src/'+ENTRY)
    incoming=(ROOT/'src'/ENTRY).read_bytes()
    with tempfile.TemporaryDirectory() as temp:
        files=[]
        for index,data in enumerate((device,baseline,incoming)):
            path=Path(temp)/str(index)
            path.write_bytes(data.replace(b'\r\n',b'\n'))
            files.append(str(path))
        merged=subprocess.run(['git','merge-file','-p']+files,capture_output=True)
    if merged.returncode:
        raise ValueError('device entry conflicts with care integration; review required')
    # Keep syntax failures out of installable artifacts, without importing hardware.
    compile(merged.stdout,ENTRY,'exec')
    payload={m+'.py':(ROOT/'src'/(m+'.py')).read_bytes() for m in MODULES}
    payload.update({'migrations/local_care/'+m:(ROOT/'src/migrations/local_care'/m).read_bytes() for m in MIGRATIONS})
    payload[ENTRY]=merged.stdout
    rows=[dict(path=p,sha256=digest(payload[p]),before_sha256=digest(device) if p==ENTRY else None) for p in PATHS]
    manifest=dict(schema_version=1,kind='care-flat',baseline=BASELINE,
                  revision=_git('rev-parse','HEAD').decode().strip(),
                  files=rows,requires={Path(p).name:digest(_git('show',BASELINE+':'+p)) for p in REQUIRES})
    try:
        tree=ast.parse(merged.stdout)
    except SyntaxError as exc:
        raise ValueError('merged device entry is not valid Python') from exc
    required={'run_system','dispatch_care_detection','trigger_history_event','poll_care_without_observation'}
    if not required <= {getattr(node,'name',None) for node in tree.body}:
        raise ValueError('merged device entry lost required service entry points')
    target=Path(output);target.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(target,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path,data in sorted({'manifest.json':(json.dumps(manifest,sort_keys=True,indent=2)+'\n').encode(),
                                 **{'payload/'+name:data for name,data in payload.items()}}.items()):
            info=zipfile.ZipInfo(path,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            archive.writestr(info,data)
    return manifest


def manifest_rows(value):
    if (not isinstance(value,dict) or value.get('schema_version')!=1 or value.get('kind')!='care-flat'
            or value.get('baseline')!=BASELINE or not isinstance(value.get('files'),list)):
        raise ValueError('unknown flat manifest')
    rows=value['files']
    if len(rows)!=len(PATHS) or {r.get('path') for r in rows}!=set(PATHS):
        raise ValueError('unexpected flat paths')
    for row in rows:
        if (not isinstance(row.get('sha256'),str) or not HEX.fullmatch(row['sha256'])
                or (row.get('before_sha256') is not None and
                    (not isinstance(row['before_sha256'],str) or not HEX.fullmatch(row['before_sha256'])))):
            raise ValueError('invalid flat fingerprints')
        if (row['path']==ENTRY) != (row.get('before_sha256') is not None):
            raise ValueError('only the reviewed entry may replace an existing file')
    return rows


def check_flat(bundle,app_root):
    root=app_directory(app_root)
    with zipfile.ZipFile(bundle) as archive:
        manifest=json.loads(archive.read('manifest.json'))
        rows=manifest_rows(manifest)
        expected={'manifest.json'}|{'payload/'+p for p in PATHS}
        if len(archive.namelist())!=len(expected) or set(archive.namelist())!=expected:
            raise ValueError('unexpected or duplicate archive entries')
        dependencies=manifest.get('requires')
        if not isinstance(dependencies,dict) or set(dependencies)!={Path(p).name for p in REQUIRES}:
            raise ValueError('unexpected dependencies')
        for name,fingerprint in dependencies.items():
            p=safe(root,name)
            if not p.is_file() or digest(p.read_bytes())!=fingerprint:
                raise ValueError('existing dependency differs: '+name)
        for row in rows:
            name=row['path'];p=safe(root,name)
            if digest(archive.read('payload/'+name))!=row['sha256']:
                raise ValueError('payload fingerprint differs: '+name)
            before=digest(p.read_bytes()) if p.is_file() else None
            if p.exists() and not p.is_file() or before!=row['before_sha256']:
                raise ValueError('post-review device drift: '+name)
            if safe(root,name+'.care-flat-tmp').exists():
                raise ValueError('incomplete installation must be rolled back first')
    return manifest


def apply_flat(bundle,app_root,backup_dir):
    root=app_directory(app_root)
    manifest=check_flat(bundle,root)
    backup=Path(backup_dir)
    backup.mkdir(parents=True,exist_ok=False,mode=0o700)
    saved=dict(schema_version=1,kind='care-flat-backup',baseline=BASELINE,
               install_nonce=uuid.uuid4().hex,files=[])
    for row in manifest['files']:
        target=safe(root,row['path'])
        item=dict(row,mode=stat.S_IMODE(target.stat().st_mode) if target.exists() else 0o644)
        saved['files'].append(item)
        if row['before_sha256'] is not None:
            dest=safe(backup,'code/'+row['path']);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(target,dest)
    # Write exactly once, before changing the first target; works after partial install.
    with (backup/'backup.json').open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(saved,sort_keys=True,indent=2))
        stream.flush();os.fsync(stream.fileno())
    with zipfile.ZipFile(bundle) as archive:
        for row in manifest['files']:
            p=safe(root,row['path']);p.parent.mkdir(parents=True,exist_ok=True)
            actual=digest(p.read_bytes()) if p.exists() else None
            if actual!=row['before_sha256']:
                raise ValueError('device changed during installation')
            staged=safe(root,row['path']+'.care-flat-'+saved['install_nonce']+'.tmp')
            with staged.open('xb') as stream:
                stream.write(archive.read('payload/'+row['path']))
                stream.flush();os.fsync(stream.fileno())
            staged.chmod(next(r['mode'] for r in saved['files'] if r['path']==row['path']))
            staged.replace(p)
    return dict(status='applied',revision=manifest['revision'],files=len(saved['files']))


def rollback_flat(app_root,backup_dir):
    root=app_directory(app_root);backup=app_directory(backup_dir)
    saved=json.loads((backup/'backup.json').read_text(encoding='utf-8'))
    nonce=saved.get('install_nonce')
    if saved.get('kind')!='care-flat-backup' or not isinstance(nonce,str) or not re.fullmatch(r'[0-9a-f]{32}',nonce):
        raise ValueError('unknown flat backup')
    rows=manifest_rows(dict(saved,kind='care-flat'))
    for row in rows:
        p=safe(root,row['path']);before=row['before_sha256']
        if p.exists() and digest(p.read_bytes()) not in (row['sha256'],before):
            raise ValueError('post-install change requires review: '+row['path'])
        if before is not None and digest(safe(backup,'code/'+row['path']).read_bytes())!=before:
            raise ValueError('backup fingerprint differs')
        staged=safe(root,row['path']+'.care-flat-'+saved['install_nonce']+'.tmp')
        # Unique nonce and exclusive creation identify our partial stage.
        # Unknown paths/symlinks are still rejected by safe().
        safe(root,row['path']+'.care-flat-'+nonce+'.restore')
    # Restore entry before removing new modules; interrupted restore can retry.
    for row in sorted(rows,key=lambda r:r['path']!=ENTRY):
        p=safe(root,row['path'])
        if row['before_sha256'] is not None:
            actual=digest(p.read_bytes()) if p.exists() else None
            if actual!=row['before_sha256']:
                p.parent.mkdir(parents=True,exist_ok=True)
                restore=safe(root,row['path']+'.care-flat-'+nonce+'.restore')
                if restore.exists(): restore.unlink()
                shutil.copy2(safe(backup,'code/'+row['path']),restore)
                if digest(restore.read_bytes())!=row['before_sha256']:
                    raise ValueError('restore staging fingerprint differs')
                restore.chmod(row['mode'] | stat.S_IWUSR)
                with restore.open('r+b') as stream: os.fsync(stream.fileno())
                restore.chmod(row['mode'])
                restore.replace(p)
        elif p.exists():
            p.unlink()
        staged=safe(root,row['path']+'.care-flat-'+nonce+'.tmp')
        if staged.exists(): staged.unlink()
        restore=safe(root,row['path']+'.care-flat-'+nonce+'.restore')
        if restore.exists(): restore.unlink()
    return dict(status='rolled_back',database_preserved=True)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('pack','check','apply','rollback'))
    parser.add_argument('--bundle',type=Path)
    parser.add_argument('--device-entry',type=Path)
    parser.add_argument('--app-root',type=Path)
    parser.add_argument('--backup',type=Path)
    args=parser.parse_args(argv)
    if args.action=='pack':
        if not args.bundle or not args.device_entry: parser.error('--bundle and --device-entry required')
        value=pack_flat(args.bundle,args.device_entry)
    elif args.action=='rollback':
        if not args.app_root or not args.backup: parser.error('--app-root and --backup required')
        value=rollback_flat(args.app_root,args.backup)
    else:
        if not args.bundle or not args.app_root: parser.error('--bundle and --app-root required')
        if args.action=='apply' and not args.backup: parser.error('--backup required')
        value=check_flat(args.bundle,args.app_root) if args.action=='check' else apply_flat(args.bundle,args.app_root,args.backup)
    print(json.dumps(dict(status=value.get('status','checked'),revision=value.get('revision'))))


if __name__=='__main__': main()
