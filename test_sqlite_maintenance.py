import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from deploy.sqlite_maintenance import create_backup, restore_backup


class SqliteMaintenanceTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)
        self.database = self.root / "guardian_users.db"
        conn = sqlite3.connect(self.database)
        conn.execute("CREATE TABLE t_user (username TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO t_user VALUES ('alice')")
        conn.commit()
        conn.close()

    def test_backup_is_restorable_and_removes_expired_snapshots(self):
        backup_dir = self.root / "backups"
        backup_dir.mkdir()
        expired = backup_dir / "guardian_users-20260701T000000Z.db"
        expired.write_bytes(b"expired")
        old_time = datetime(2026, 7, 1, tzinfo=timezone.utc).timestamp()
        os.utime(expired, (old_time, old_time))

        backup = create_backup(
            self.database,
            backup_dir,
            retention_days=14,
            now=datetime(2026, 7, 28, 8, 30, tzinfo=timezone.utc),
        )
        restored = restore_backup(backup, self.root / "restored.db")

        self.assertFalse(expired.exists())
        self.assertEqual(backup.name, "guardian_users-20260728T083000Z.db")
        conn = sqlite3.connect(restored)
        self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(
            conn.execute("SELECT username FROM t_user").fetchall(), [("alice",)]
        )
        conn.close()

    def test_restore_refuses_to_overwrite_existing_database(self):
        backup = create_backup(self.database, self.root / "backups")
        target = self.root / "existing.db"
        target.write_bytes(b"keep")

        with self.assertRaises(FileExistsError):
            restore_backup(backup, target)

        self.assertEqual(target.read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
