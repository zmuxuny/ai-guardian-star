"""Deployment materials must work on a local sparse copy, without any service."""
from pathlib import Path
import tempfile
import unittest
import zipfile
import json
from unittest.mock import patch

from tools.care_release import pack, apply, rollback


class ReleaseTests(unittest.TestCase):
    def test_prepared_rollback_manifest_is_never_rewritten_after_install(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle, app, backup = root/'release.zip', root/'app', root/'backup'
            pack(bundle, require_clean=False)
            app.mkdir()
            with zipfile.ZipFile(bundle) as archive:
                for name in archive.namelist():
                    if name.startswith('baseline/'):
                        target = app / name[len('baseline/'):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            writes = []
            original_write = Path.write_text
            def fail_second(path, *args, **kwargs):
                if path.name == 'backup.json':
                    writes.append(path)
                    if len(writes) > 1:
                        path.write_bytes(b'')
                        raise OSError('simulated failure after manifest truncation')
                return original_write(path, *args, **kwargs)
            with patch.object(Path, 'write_text', fail_second):
                apply(bundle, app, backup)
            self.assertEqual(len(writes), 1)
            rollback(app, backup)
            self.assertFalse((app/'src/care_runtime.py').exists())

    def test_local_install_and_code_rollback_restore_exact_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / 'release.zip'
            manifest = pack(bundle, require_clean=False)
            app = root / 'app'
            app.mkdir()
            with zipfile.ZipFile(bundle) as archive:
                for name in archive.namelist():
                    if name.startswith('baseline/'):
                        target = app / name[len('baseline/'):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            original = {p:p.read_bytes() for p in app.rglob('*') if p.is_file()}
            backup = root / 'backup'
            apply(bundle, app, backup)
            self.assertTrue((app / 'src/care_runtime.py').is_file())
            self.assertEqual(json.loads((backup / 'backup.json').read_text())['baseline'], '2499d1d')
            installed = (app / 'src/care_runtime.py').read_bytes()
            (app / 'src/care_runtime.py').write_text('post-install changes', encoding='utf-8')
            with self.assertRaises(ValueError):
                rollback(app, backup)
            (app / 'src/care_runtime.py').write_bytes(installed)
            rollback(app, backup)
            self.assertFalse((app / 'src/care_runtime.py').exists())
            self.assertTrue(all(p.read_bytes()==data for p,data in original.items()))
            self.assertGreater(len(manifest['files']), 10)

    def test_drift_is_rejected_before_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / 'release.zip'
            pack(bundle, require_clean=False)
            app = root / 'app'
            app.mkdir()
            with zipfile.ZipFile(bundle) as archive:
                for name in archive.namelist():
                    if name.startswith('baseline/'):
                        target = app / name[len('baseline/'):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            target = app / 'src/ascend_board_server.py'
            target.write_text('independent board changes', encoding='utf-8')
            with self.assertRaises(ValueError):
                apply(bundle, app, root / 'backup')
            self.assertEqual(target.read_text(), 'independent board changes')

    def test_sqlite_backup_and_code_rollback_preserve_new_feedback(self):
        from src.local_care_migrations import migrate_database, connection
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            bundle = root / 'release.zip'
            pack(bundle, require_clean=False)
            app = root / 'app'
            app.mkdir()
            with zipfile.ZipFile(bundle) as archive:
                for name in archive.namelist():
                    if name.startswith('baseline/'):
                        target = app / name[len('baseline/'):]
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
            database = root / 'private.db'
            migrate_database(database, target_version=2)
            with connection(database) as db:
                db.execute("INSERT INTO feedback VALUES ('p1','m1','old',600,601,'{}',1000,1000,0,NULL,NULL,1)")
            backup = root / 'backup'
            apply(bundle, app, backup, database)
            with connection(backup / 'care-db.sqlite') as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)
                self.assertEqual(db.execute('SELECT count(*) FROM feedback').fetchone()[0], 1)
            migrate_database(database)
            with connection(database) as db:
                db.execute("INSERT INTO feedback VALUES ('p1','m1','new',600,601,'{}',1000,1000,0,NULL,NULL,1)")
            rollback(app, backup)
            with connection(database) as db:
                self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
                self.assertEqual(db.execute('SELECT count(*) FROM feedback').fetchone()[0], 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
