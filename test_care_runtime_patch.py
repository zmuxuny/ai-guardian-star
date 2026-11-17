"""Stopped-service, fingerprinted three-file patch; preserve native board code."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import care_runtime_patch as release


class PatchTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.repo=self.root/'repo';(self.repo/'src').mkdir(parents=True)
        self.original=self.root/'original';self.original.mkdir()
        native=b'NATIVE_VIDEO_ENHANCEMENT = True\ndef build():\n    alerts.append({\n                "sit_duration_sec": sit_duration_sec,\n    })\n'
        for name in release.FILES:
            data=native if name=='ascend_main_other.py' else b'old_value = 1\n'
            (self.original/name).write_bytes(data)
            (self.repo/'src'/name).write_bytes(b'new_value = 2\n')
        self.baseline={'expected_files':{name:release.digest((self.original/name).read_bytes()) for name in release.FILES}}
        self.bundle=self.root/'patch.zip';self.backup=self.root/'backup'

    def pack(self):
        return release.pack_patch(self.repo,self.original,self.baseline,self.bundle,'test-revision')

    def test_native_enhancements_preserved_and_bundle_reproducible(self):
        result=self.pack();first=self.bundle.read_bytes();self.pack()
        self.assertEqual(first,self.bundle.read_bytes())
        import zipfile
        with zipfile.ZipFile(self.bundle) as archive:
            native=archive.read('payload/ascend_main_other.py')
        self.assertIn(b'NATIVE_VIDEO_ENHANCEMENT = True',native)
        self.assertIn(b'"care_observation"',native)
        self.assertEqual(len(result['files']),3)

    def test_apply_and_rollback_preserve_original_bytes_and_new_database_data(self):
        self.pack();(self.original/'data.db').write_bytes(b'original data')
        release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:True)
        (self.original/'data.db').write_bytes(b'new feedback after patch')
        release.rollback(self.original,self.backup,stopped=lambda:True)
        self.assertEqual((self.original/'guardian_runtime.py').read_bytes(),b'old_value = 1\n')
        self.assertEqual((self.original/'data.db').read_bytes(),b'new feedback after patch')

    def test_active_service_and_fingerprint_drift_fail_before_backup_or_application_write(self):
        self.pack()
        with self.assertRaises(ValueError):release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:False)
        (self.original/'care_runtime.py').write_text('another_edit = 1')
        with self.assertRaises(ValueError):release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:True)
        self.assertFalse(self.backup.exists())

    def test_interrupted_patch_is_recoverable_and_backup_cannot_be_overwritten(self):
        self.pack();replace=release._replace;count=[0]
        def fail_second(path,data):
            count[0]+=1
            if count[0]==2:raise OSError('interrupted')
            replace(path,data)
        with patch.object(release,'_replace',side_effect=fail_second):
            with self.assertRaises(OSError):release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:True)
        release.rollback(self.original,self.backup,stopped=lambda:True)
        with self.assertRaises(FileExistsError):release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:True)

    def test_rollback_refuses_unknown_edits_without_overwriting_them(self):
        self.pack();release.apply_patch(self.original,self.bundle,self.backup,stopped=lambda:True)
        edited=self.original/'ascend_main_other.py';edited.write_text('unrelated_change = 1')
        with self.assertRaises(ValueError):release.rollback(self.original,self.backup,stopped=lambda:True)
        self.assertEqual(edited.read_text(),'unrelated_change = 1')
