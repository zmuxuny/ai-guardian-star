"""Apply verified camera patch to a stopped board service.

Usage: python3 camera-recovery-apply.py /path/to/board [--check]
Requires the system `patch` command. Keeps a same-directory .camera-before backup.
Never prints source contents. Refuses source drift or partially applied files.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    assets = Path(__file__).resolve().parent
    manifest = json.loads((assets / 'camera-recovery-sha256.json').read_text(encoding='utf-8'))
    target = args.directory.resolve(strict=True)
    actual = {name: digest(target / name) for name in manifest}
    if all(actual[name] == hashes['after'] for name, hashes in manifest.items()):
        print('Camera patch already applied; SHA-256 verified.')
        return
    if not all(actual[name] == hashes['before'] for name, hashes in manifest.items()):
        raise SystemExit('Source differs from verified originals; refusing to modify files.')
    patch = shutil.which('patch')
    if not patch:
        raise SystemExit('System patch command is required.')
    # Stage and validate all results before touching the service files.
    with tempfile.TemporaryDirectory(prefix='camera-recovery-') as tmp:
        staged = Path(tmp)
        for name in manifest:
            shutil.copy2(target / name, staged / name)
        result = subprocess.run([patch, '--batch', '--forward', '-p1', '-i',
                                 str(assets / 'camera-recovery.patch')], cwd=staged,
                                capture_output=True, text=True)
        if result.returncode:
            raise SystemExit('Patch validation failed; service files unchanged.')
        for name, hashes in manifest.items():
            content = (staged / name).read_bytes()
            if digest(staged / name) != hashes['after']:
                raise SystemExit('Patched SHA-256 differs; service files unchanged.')
            compile(content, name, 'exec')
        if args.check:
            print('Original hashes, patch and Python syntax verified; no files changed.')
            return
        for name in manifest:
            backup = target / (name + '.camera-before')
            if backup.exists() and digest(backup) != manifest[name]['before']:
                raise SystemExit('Existing backup differs; service files unchanged.')
        for name in manifest:
            backup = target / (name + '.camera-before')
            if not backup.exists():
                shutil.copy2(target / name, backup)
        for name in manifest:
            shutil.copyfile(staged / name, target / name)
        if not all(digest(target / name) == hashes['after'] for name, hashes in manifest.items()):
            raise SystemExit('Post-write SHA-256 failed; restore .camera-before backups before restarting.')
    print('Camera patch applied; SHA-256 and Python syntax verified. Backups retained.')


if __name__ == '__main__':
    main()
