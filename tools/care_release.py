"""Offline, hash-checked patch bundle and code rollback. Never starts a service."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '2499d1d'
FILES = (
    'src/ascend_board_server.py','src/sedentary_care.py','src/local_care_store.py',
    'src/local_care_migrations.py','src/shadow_mode.py','src/care_runtime.py',
    'src/care_delivery_store.py','src/care_api.py','src/care_transport.py',
    'src/weekly_store.py','src/weekly_report.py','src/migrations/local_care/004_weekly.sql',
    'test_weekly_report.py','tools/run_weekly_scenarios.py','docs/weekly-report-contract.md',
    'src/migrations/local_care/001_initial.sql','src/migrations/local_care/002_baseline_source.sql',
    'src/migrations/local_care/003_delivery.sql','tools/migrate_local_care.py',
    'tools/care_release.py','tools/run_care_delivery.py','test_care_delivery.py',
    'requirements-care-validation.txt','deploy/care-config.example.json',
    'docs/care-delivery-runbook.md',
    'docs/care-delivery-evidence.md',
)
REQUIRES = ('src/guardian_runtime.py','src/guardian_history.py','src/guardian_event_cache.py',
            'src/guardian_recording.py','src/guardian_storage.py','src/guardian_recording_config.py',
            'src/region_aggregation.py')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def _git(*args, optional=False):
    result = subprocess.run(['git', *args], cwd=ROOT, capture_output=True)
    if result.returncode and not optional:
        raise RuntimeError('cannot read release git reference')
    return None if result.returncode else result.stdout


def _safe(root, name):
    pure = PurePosixPath(name)
    if pure.is_absolute() or '..' in pure.parts or '\\' in name or ':' in name:
        raise ValueError('unsafe release path')
    result = root.joinpath(*pure.parts)
    if not result.resolve().is_relative_to(root.resolve()) or result.is_symlink():
        raise ValueError('release path escapes target root')
    return result


def pack(output, *, require_clean=True):
    dirty = bool(_git('status','--porcelain').strip())
    if require_clean and dirty:
        raise ValueError('commit and verify the working tree before building a delivery bundle')
    manifest = {'schema_version':1, 'baseline':BASELINE,
                'revision':_git('rev-parse','HEAD').decode().strip(), 'working_tree':dirty,
                'files':[], 'requires':{}}
    blobs = {}
    for name in FILES:
        current = (ROOT / name).read_bytes()
        before = _git('show', f'{BASELINE}:{name}', optional=True)
        manifest['files'].append({'path':name,'sha256':digest(current),
                                  'baseline_sha256':digest(before) if before is not None else None})
        blobs['payload/' + name] = current
        if before is not None:
            blobs['baseline/' + name] = before
    for name in REQUIRES:
        before = _git('show', f'{BASELINE}:{name}')
        manifest['requires'][name] = digest(before)
        blobs['baseline/' + name] = before
    blobs['manifest.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(blobs.items()):
            info = zipfile.ZipInfo(name, date_time=(1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, data)
    return manifest


def check(bundle, app_root):
    root = Path(app_root).resolve()
    if not root.is_dir():
        raise ValueError('application root must already exist')
    with zipfile.ZipFile(bundle) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if (manifest.get('schema_version') != 1 or manifest.get('baseline') != BASELINE
                or {r['path'] for r in manifest['files']} != set(FILES)
                or set(manifest['requires']) != set(REQUIRES)):
            raise ValueError('unknown release manifest')
        for name, expected in manifest['requires'].items():
            path = _safe(root, name)
            if not path.is_file() or digest(path.read_bytes()) != expected:
                raise ValueError('baseline dependency differs: ' + name)
        for row in manifest['files']:
            name = row['path']
            if digest(archive.read('payload/' + name)) != row['sha256']:
                raise ValueError('bundle hash mismatch: ' + name)
            path = _safe(root, name)
            if path.exists():
                if (not path.is_file() or row['baseline_sha256'] is None
                        or digest(path.read_bytes()) != row['baseline_sha256']):
                    raise ValueError('independent board modification: ' + name)
            elif row['baseline_sha256'] is not None:
                raise ValueError('baseline file missing: ' + name)
    return manifest


def apply(bundle, app_root, backup_dir, care_db=None):
    root, backup = Path(app_root).resolve(), Path(backup_dir).resolve()
    manifest = check(bundle, root)  # Complete preflight before any overwrite.
    backup.mkdir(parents=True, exist_ok=False, mode=0o700)
    saved = {'schema_version':1, 'baseline':BASELINE,'revision':manifest['revision'],
             'state':'prepared','files':[], 'db_backup':False}
    for row in manifest['files']:
        path = _safe(root, row['path'])
        saved['files'].append({'path':row['path'],'existed':path.exists(), 'installed_sha256':row['sha256']})
        if path.exists():
            destination = _safe(backup, 'code/' + row['path'])
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    if care_db is not None and Path(care_db).exists():
        source = sqlite3.connect(Path(care_db).resolve().as_uri() + '?mode=ro', uri=True)
        destination = sqlite3.connect(str(backup / 'care-db.sqlite'))
        try:
            source.backup(destination)
            saved['db_backup'] = True
        finally:
            destination.close()
            source.close()
    (backup / 'backup.json').write_text(json.dumps(saved, indent=2), encoding='utf-8')
    with zipfile.ZipFile(bundle) as archive:
        for row in manifest['files']:
            path = _safe(root, row['path'])
            path.parent.mkdir(parents=True, exist_ok=True)
            staged = _safe(root, row['path'] + '.care-install-tmp')
            staged.write_bytes(archive.read('payload/' + row['path']))
            staged.replace(path)
    saved['state'] = 'applied'
    # Keep the prepared rollback manifest immutable. Rewriting this only copy
    # after installation could truncate it on ENOSPC and destroy recovery.
    return saved


def rollback(app_root, backup_dir):
    root, backup = Path(app_root).resolve(), Path(backup_dir).resolve()
    saved = json.loads((backup / 'backup.json').read_text(encoding='utf-8'))
    if saved.get('schema_version') != 1 or saved.get('baseline') != BASELINE:
        raise ValueError('unknown rollback backup')
    if {r['path'] for r in saved['files']} != set(FILES):
        raise ValueError('unknown rollback paths')
    # Refuse to overwrite changes made AFTER installation. A partially applied
    # install may still have baseline bytes, which are also preserved in code/.
    for row in saved['files']:
        path = _safe(root, row['path'])
        previous = _safe(backup, 'code/' + row['path'])
        permitted = {row['installed_sha256']}
        if row['existed']:
            permitted.add(digest(previous.read_bytes()))
        if path.exists() and digest(path.read_bytes()) not in permitted:
            raise ValueError('post-install change requires manual review: ' + row['path'])
    for row in saved['files']:
        path = _safe(root, row['path'])
        if row['existed']:
            shutil.copy2(_safe(backup, 'code/' + row['path']), path)
        elif path.exists():
            path.unlink()
    # Never downgrade/delete a live care DB: newer feedback remains recoverable.
    return {'baseline':BASELINE,'database_preserved':True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('pack','check','apply','rollback'))
    parser.add_argument('--bundle', type=Path)
    parser.add_argument('--app-root', type=Path)
    parser.add_argument('--backup', type=Path)
    parser.add_argument('--care-db', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'pack':
        if not args.bundle:
            parser.error('--bundle required')
        result = pack(args.bundle)
    elif args.action == 'rollback':
        if not args.app_root or not args.backup:
            parser.error('--app-root and --backup required')
        result = rollback(args.app_root, args.backup)
    else:
        if not args.bundle or not args.app_root:
            parser.error('--bundle and --app-root required')
        if args.action == 'apply' and not args.backup:
            parser.error('--backup required')
        result = (check(args.bundle,args.app_root) if args.action == 'check' else
                  apply(args.bundle,args.app_root,args.backup,args.care_db))
    print(json.dumps({'baseline':result.get('baseline'), 'revision':result.get('revision'),
                      'status':'ok'}))


if __name__ == '__main__':
    main()
