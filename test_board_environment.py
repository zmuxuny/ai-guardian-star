"""Existing Python/flat layout regressions. No sensors or real service imports."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT=Path(__file__).resolve().parent


class PythonCompatibilityTests(unittest.TestCase):
    def test_care_modules_import_with_original_interpreter(self):
        program="import sys; sys.path.insert(0,sys.argv[1]); import sedentary_care, local_care_store, care_delivery_store, weekly_store, care_runtime, care_api; print('imports_ok')"
        result=subprocess.run([sys.executable,'-c',program,str(ROOT/'src')],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('imports_ok',result.stdout)


class FlatReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.app=self.root/'app';self.app.mkdir()
        self.entry=self.root/'device.py'
        self.baseline=subprocess.check_output(['git','show','2499d1d:src/ascend_board_server.py'],cwd=ROOT)
        # Reproduce the two independent device enhancements without private data.
        self.device=self.baseline.replace(b'video_hw.update_frame(frame)',b'video_hw.update_frame(frame, captured_at=monotonic_at)').replace(b'last_frame = None',b'last_frame = None  # independent camera enhancement',1)
        self.entry.write_bytes(self.device)
        self.bundle=self.root/'flat.zip';self.backup=self.root/'backup'

    def prepare(self):
        from tools.care_flat_release import pack_flat,REQUIRES
        manifest=pack_flat(self.bundle,self.entry,require_clean=False)
        (self.app/'ascend_board_server.py').write_bytes(self.device)
        for name in REQUIRES:
            (self.app/Path(name).name).write_bytes(subprocess.check_output(['git','show','2499d1d:'+name],cwd=ROOT))
        return manifest

    def test_merge_keeps_device_video_and_adds_care(self):
        from tools.care_flat_release import apply_flat,rollback_flat
        self.prepare()
        (self.app/'start.sh').write_bytes(b'original launcher')
        (self.app/'best.om').write_bytes(b'original model')
        apply_flat(self.bundle,self.app,self.backup)
        installed=(self.app/'ascend_board_server.py').read_text(encoding='utf-8')
        self.assertIn('captured_at=monotonic_at',installed)
        self.assertIn('independent camera enhancement',installed)
        self.assertIn('dispatch_care_detection(care_runtime',installed)
        self.assertTrue((self.app/'care_runtime.py').is_file())
        self.assertTrue((self.app/'migrations/local_care/004_weekly.sql').is_file())
        self.assertFalse((self.app/'src').exists())
        rollback_flat(self.app,self.backup)
        self.assertEqual((self.app/'ascend_board_server.py').read_bytes(),self.device)
        self.assertFalse((self.app/'care_runtime.py').exists())
        self.assertEqual((self.app/'start.sh').read_bytes(),b'original launcher')
        self.assertEqual((self.app/'best.om').read_bytes(),b'original model')

    def test_drift_and_corrupt_payload_fail_before_backup_or_write(self):
        from tools.care_flat_release import apply_flat
        self.prepare()
        target=self.app/'ascend_board_server.py'
        target.write_bytes(self.device+b'\n# changed after review\n')
        with self.assertRaises(ValueError): apply_flat(self.bundle,self.app,self.backup)
        self.assertFalse(self.backup.exists())
        target.write_bytes(self.device)
        with zipfile.ZipFile(self.bundle,'a') as archive:
            archive.writestr('payload/care_runtime.py',b'corrupted')
        with self.assertRaises(ValueError): apply_flat(self.bundle,self.app,self.backup)
        self.assertEqual(target.read_bytes(),self.device)
        self.assertFalse(self.backup.exists())

    def test_unknown_module_or_dependency_is_not_overwritten(self):
        from tools.care_flat_release import apply_flat
        self.prepare()
        target=self.app/'care_runtime.py';target.write_text('private changes',encoding='utf-8')
        with self.assertRaises(ValueError): apply_flat(self.bundle,self.app,self.backup)
        self.assertEqual(target.read_text(),'private changes')
        target.unlink()
        (self.app/'guardian_runtime.py').write_text('dependency drift',encoding='utf-8')
        with self.assertRaises(ValueError): apply_flat(self.bundle,self.app,self.backup)
        self.assertFalse(self.backup.exists())

    def test_rollback_refuses_post_install_changes_and_preserves_database(self):
        from tools.care_flat_release import apply_flat,rollback_flat
        self.prepare();apply_flat(self.bundle,self.app,self.backup)
        data=self.app/'care.db';data.write_bytes(b'new feedback must survive')
        target=self.app/'care_runtime.py';original=target.read_bytes();target.write_bytes(b'later change')
        with self.assertRaises(ValueError): rollback_flat(self.app,self.backup)
        target.write_bytes(original);rollback_flat(self.app,self.backup)
        self.assertEqual(data.read_bytes(),b'new feedback must survive')

    def test_partial_write_can_be_rolled_back(self):
        from tools.care_flat_release import apply_flat,rollback_flat
        from unittest.mock import patch
        self.prepare()
        original=Path.open
        class PartialWriter:
            def __init__(self,stream): self.stream=stream
            def __enter__(self): return self
            def __exit__(self,*args): self.stream.close()
            def write(self,data):
                self.stream.write(data[:16]);self.stream.flush()
                raise OSError('simulated disk-full during write')
        def interrupted(path,*args,**kwargs):
            stream=original(path,*args,**kwargs)
            if path.name.startswith('local_care_store.py.care-flat-') and args and args[0]=='xb':
                return PartialWriter(stream)
            return stream
        with patch.object(Path,'open',interrupted):
            with self.assertRaises(OSError): apply_flat(self.bundle,self.app,self.backup)
        rollback_flat(self.app,self.backup)
        self.assertEqual((self.app/'ascend_board_server.py').read_bytes(),self.device)
        self.assertFalse((self.app/'sedentary_care.py').exists())

    def test_interrupted_rollback_does_not_truncate_entry_and_can_retry(self):
        from tools.care_flat_release import apply_flat,rollback_flat
        from unittest.mock import patch
        import shutil
        self.prepare();apply_flat(self.bundle,self.app,self.backup)
        entry=self.app/'ascend_board_server.py';installed=entry.read_bytes()
        def partial_copy(source,target):
            Path(target).write_bytes(Path(source).read_bytes()[:16])
            raise OSError('simulated interrupted restore')
        with patch.object(shutil,'copy2',partial_copy):
            with self.assertRaises(OSError): rollback_flat(self.app,self.backup)
        self.assertEqual(entry.read_bytes(),installed)
        rollback_flat(self.app,self.backup)
        self.assertEqual(entry.read_bytes(),self.device)

    def test_conflicting_device_entry_is_rejected(self):
        from tools.care_flat_release import pack_flat
        self.entry.write_bytes(self.baseline.replace(b'def run_system():',b'def renamed_independent_entry():'))
        with self.assertRaises(ValueError): pack_flat(self.bundle,self.entry,require_clean=False)
        self.assertFalse(self.bundle.exists())

    def test_interrupted_install_has_working_rollback_manifest(self):
        from tools.care_flat_release import apply_flat,rollback_flat
        from unittest.mock import patch
        self.prepare()
        replace=Path.replace
        calls=[]
        def fail_second(path,target):
            calls.append(path)
            if len(calls)==2: raise OSError('simulated interrupted install')
            return replace(path,target)
        with patch.object(Path,'replace',fail_second):
            with self.assertRaises(OSError): apply_flat(self.bundle,self.app,self.backup)
        rollback_flat(self.app,self.backup)
        self.assertEqual((self.app/'ascend_board_server.py').read_bytes(),self.device)
        self.assertFalse((self.app/'care_runtime.py').exists())


if __name__=='__main__': unittest.main(verbosity=2)
