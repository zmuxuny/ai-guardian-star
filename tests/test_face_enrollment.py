"""Multi-photo file/SQLite lifecycle with synthetic decode and no hardware."""

import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

import numpy as np

from test_runtime import load_definition


class MultiPhotoEnrollmentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        class HTTPException(Exception):
            def __init__(self, status_code, detail):
                self.status_code, self.detail = status_code, detail
        self.api = dict(os=os, np=np, shutil=shutil, time=time, uuid=uuid,
            _sqlite3=sqlite3, HTTPException=HTTPException,
            _FACE_DIR=str(self.root / "faces"), _DB_PATH=str(self.root / "faces.db"),
            _FACE_UPLOAD_MAX_BYTES=8 * 1024 * 1024, _FACE_ENROLL_HINT="一张也可登记，建议上传不同方向照片",
            system_detector=None, Form=lambda *args: None, File=lambda *args: None,
            UploadFile=object, JSONResponse=lambda value: value, print=lambda *args: None,
            cv2=SimpleNamespace(IMREAD_COLOR=1,
                imdecode=lambda *args: np.full((80, 80, 3), 100, np.uint8),
                imencode=lambda *args: (True, np.array([1, 2, 3], np.uint8))))
        for name in ("_validate_face_fields", "_face_sample_paths", "_connect_face_db",
                     "_db_get_face_name", "_db_log_face", "_db_delete_face", "_db_list_faces",
                     "_reload_face_library_for_api", "face_enroll", "face_delete", "face_list"):
            load_definition("ascend_board_server.py", name, self.api)

    async def upload(self, user_id="user", name="Yang"):
        async def read(limit):
            return b"image"
        return await self.api["face_enroll"](name, user_id, SimpleNamespace(read=read))

    def samples(self, name="Yang", user_id="user"):
        return self.api["_face_sample_paths"](str(self.root / "faces" / name), user_id)

    async def test_one_photo_works_and_more_are_optional_append_only(self):
        for count in range(1, 6):
            result = await self.upload()
            self.assertTrue(result["ok"])
            self.assertEqual(result["photo_count"], count)
            self.assertIn("一张也可登记", result["hint"])
            self.assertEqual(len(self.samples()), count)
        listed = await self.api["face_list"]()
        self.assertEqual(listed["faces"][0]["photo_count"], 5)
        self.assertIn("hint", listed)

    async def test_delete_removes_all_owned_samples_but_not_similar_user_id(self):
        await self.upload("user")
        await self.upload("user")
        await self.upload("user_a")
        (self.root / "faces" / "Yang" / "user_1726000000.jpg").write_bytes(b"legacy")
        other = self.samples(user_id="user_a")[0]
        await self.api["face_delete"]("user")
        self.assertEqual(self.samples(), [])
        self.assertTrue(Path(other).is_file())
        self.assertEqual(self.api["_db_get_face_name"]("user_a"), "Yang")

    async def test_rename_preserves_all_photos_and_other_users(self):
        await self.upload()
        await self.upload()
        await self.upload("user_a")
        (self.root / "faces" / "Yang" / "user_1726000000.jpg").write_bytes(b"legacy")
        result = await self.upload(name="Renamed")
        self.assertEqual(result["photo_count"], 4)
        self.assertEqual(self.samples(), [])
        self.assertEqual(len(self.samples(name="Renamed")), 4)
        self.assertEqual(len(self.samples(user_id="user_a")), 1)
        self.assertEqual(self.api["_db_get_face_name"]("user"), "Renamed")

    async def test_database_failure_on_append_removes_only_new_photo(self):
        await self.upload()
        original = self.samples()
        with patch.dict(self.api, {"_db_log_face": Mock(side_effect=OSError("database failed"))}):
            with self.assertRaises(self.api["HTTPException"]):
                await self.upload()
        self.assertEqual(self.samples(), original)
        self.assertEqual(self.api["_db_get_face_name"]("user"), "Yang")

    async def test_database_failure_on_rename_restores_old_paths(self):
        await self.upload()
        await self.upload()
        original = self.samples()
        with patch.dict(self.api, {"_db_log_face": Mock(side_effect=OSError("database failed"))}):
            with self.assertRaises(self.api["HTTPException"]):
                await self.upload(name="Renamed")
        self.assertEqual(self.samples(), original)
        self.assertEqual(self.samples(name="Renamed"), [])
        self.assertEqual(self.api["_db_get_face_name"]("user"), "Yang")

    async def test_database_failure_on_delete_restores_all_photos(self):
        await self.upload()
        await self.upload()
        original = self.samples()
        with patch.dict(self.api, {"_db_delete_face": Mock(side_effect=OSError("database failed"))}):
            with self.assertRaises(self.api["HTTPException"]):
                await self.api["face_delete"]("user")
        self.assertEqual(self.samples(), original)
        self.assertEqual(self.api["_db_get_face_name"]("user"), "Yang")


if __name__ == "__main__":
    unittest.main()
