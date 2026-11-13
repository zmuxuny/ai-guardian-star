"""db.py 数据访问层单元测试。

覆盖三条主线：
1. SQLite 未设置 DB_URL 时保持与历史 sqlite3 直连一致的行为；
2. DB_URL 指向 MySQL 时 SQL 方言、占位符与错误类型自动改写；
3. 建表初始化、只读连接、事务封装与连接池的边界分支。
"""

import queue
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import db


MYSQL_DSN = {
    "host": "db.internal",
    "port": 3307,
    "user": "guardian",
    "password": "p@ss",
    "database": "guardian",
    "charset": "utf8mb4",
}

MYSQL_CONFIG = {"kind": "mysql", "dsn": dict(MYSQL_DSN), "query": {}}

_schema_calls = []


def _record_schema(conn):
    _schema_calls.append(conn)


def _other_schema(conn):
    _schema_calls.append(conn)


def _failing_schema(conn):
    _schema_calls.append(conn)
    raise RuntimeError("schema boom")


class DbIsolationTest(unittest.TestCase):
    """隔离 db 模块的进程级注册表、初始化缓存与连接池。"""

    def setUp(self):
        self._saved_initializers = list(db._schema_initializers)
        self._saved_names = set(db._schema_names)
        self._saved_initialized = set(db._initialized)
        self._saved_pool = db._pool
        db._schema_initializers = []
        db._schema_names = set()
        db._initialized = set()
        db._pool = queue.LifoQueue(maxsize=db.POOL_SIZE)
        _schema_calls.clear()
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "guardian.db"

    def tearDown(self):
        db._schema_initializers = self._saved_initializers
        db._schema_names = self._saved_names
        db._initialized = self._saved_initialized
        db._pool = self._saved_pool

    def open_sqlite(self):
        raw = sqlite3.connect(self.path)
        raw.row_factory = sqlite3.Row
        conn = db.Connection(raw, mysql=False)
        self.addCleanup(conn.close)
        return conn

    def mysql_connection(self, raw=None, pooled=False):
        return db.Connection(raw or mock.MagicMock(), mysql=True, pooled=pooled)


class ParseDbUrlTest(DbIsolationTest):
    def test_missing_url_keeps_sqlite_default(self):
        for value in ("", None, "   "):
            config = db.parse_db_url(value)
            self.assertEqual("sqlite", config["kind"])
            self.assertEqual(db.DEFAULT_SQLITE_PATH, config["path"])
            self.assertEqual({}, config["query"])

    def test_sqlite_url_decodes_path(self):
        config = db.parse_db_url("sqlite:///tmp/my%20guardian.db")
        self.assertEqual("sqlite", config["kind"])
        self.assertEqual("/tmp/my guardian.db", config["path"])

    def test_sqlite_windows_drive_prefix_is_trimmed(self):
        config = db.parse_db_url("sqlite:///D:/data/guardian.db")
        self.assertEqual("D:/data/guardian.db", config["path"])

    def test_sqlite_relative_path(self):
        config = db.parse_db_url("sqlite://relative.db")
        self.assertEqual("relative.db", config["path"])

    def test_empty_sqlite_url_falls_back_to_default_path(self):
        config = db.parse_db_url("sqlite://")
        self.assertEqual(db.DEFAULT_SQLITE_PATH, config["path"])

    def test_mysql_url_parses_every_component(self):
        config = db.parse_db_url(
            "mysql://guardian:p%40ss@db.internal:3307/guardian?charset=latin1"
        )
        self.assertEqual("mysql", config["kind"])
        self.assertEqual(
            {
                "host": "db.internal",
                "port": 3307,
                "user": "guardian",
                "password": "p@ss",
                "database": "guardian",
                "charset": "latin1",
            },
            config["dsn"],
        )
        self.assertEqual(["latin1"], config["query"]["charset"])

    def test_mysql_url_applies_default_port_and_charset(self):
        config = db.parse_db_url("mysql://guardian:secret@db.internal/guardian")
        self.assertEqual(3306, config["dsn"]["port"])
        self.assertEqual("utf8mb4", config["dsn"]["charset"])

    def test_mysql_url_allows_missing_user(self):
        config = db.parse_db_url("mysql://db.internal/guardian")
        self.assertEqual("", config["dsn"]["user"])
        self.assertEqual("", config["dsn"]["password"])

    def test_mysql_url_without_host_is_rejected(self):
        with self.assertRaises(db.DatabaseError) as raised:
            db.parse_db_url("mysql:///guardian")
        self.assertEqual("DB_URL 缺少主机名或数据库名", str(raised.exception))

    def test_mysql_url_without_database_is_rejected(self):
        with self.assertRaises(db.DatabaseError) as raised:
            db.parse_db_url("mysql://db.internal/")
        self.assertEqual("DB_URL 缺少主机名或数据库名", str(raised.exception))

    def test_unsupported_scheme_is_rejected(self):
        with self.assertRaises(db.DatabaseError) as raised:
            db.parse_db_url("postgresql://db.internal/guardian")
        self.assertEqual("DB_URL 只支持 sqlite:// 或 mysql://", str(raised.exception))


class RowTest(unittest.TestCase):
    def setUp(self):
        self.row = db.Row(["id", "name"], [7, "alice"])

    def test_reads_by_column_name_and_index(self):
        self.assertEqual(7, self.row["id"])
        self.assertEqual("alice", self.row["name"])
        self.assertEqual(7, self.row[0])
        self.assertEqual("alice", self.row[-1])
        self.assertEqual((7, "alice"), self.row[0:2])

    def test_iteration_and_length(self):
        self.assertEqual([7, "alice"], list(self.row))
        self.assertEqual(2, len(self.row))

    def test_keys_and_membership(self):
        self.assertEqual(["id", "name"], self.row.keys())
        self.assertIn("name", self.row)
        self.assertNotIn("missing", self.row)

    def test_get_returns_default_for_unknown_column(self):
        self.assertEqual("alice", self.row.get("name"))
        self.assertEqual("fallback", self.row.get("missing", "fallback"))
        self.assertIsNone(self.row.get("missing"))

    def test_unknown_column_raises_index_error_like_sqlite_row(self):
        with self.assertRaises(IndexError):
            self.row["missing"]
        with self.assertRaises(IndexError):
            self.row[9]

    def test_equality_with_row_and_tuple(self):
        self.assertEqual(db.Row(["id", "name"], [7, "alice"]), self.row)
        self.assertEqual((7, "alice"), self.row)
        self.assertNotEqual([7, "alice"], self.row)
        self.assertNotEqual(object(), self.row)

    def test_repr_shows_column_mapping(self):
        self.assertEqual("Row({'id': 7, 'name': 'alice'})", repr(self.row))


class CursorTest(unittest.TestCase):
    def _raw(self, rows=None):
        raw = mock.MagicMock()
        raw.description = (("id",), ("name",))
        raw.fetchall.return_value = rows if rows is not None else [(1, "a"), (2, "b")]
        raw.fetchmany.return_value = rows if rows is not None else [(1, "a"), (2, "b")]
        return raw

    def test_mysql_fetchone_converts_rows_and_consumes_them(self):
        raw = self._raw()
        cursor = db.Cursor(raw, mysql=True)
        first = cursor.fetchone()
        self.assertIsInstance(first, db.Row)
        self.assertEqual(1, first["id"])
        self.assertEqual("b", cursor.fetchone()["name"])
        self.assertIsNone(cursor.fetchone())
        raw.fetchall.assert_called_once_with()

    def test_mysql_fetchall_returns_dict_rows(self):
        raw = self._raw()
        rows = db.Cursor(raw, mysql=True).fetchall()
        self.assertEqual(["a", "b"], [row["name"] for row in rows])
        self.assertEqual([1, 2], [row[0] for row in rows])

    def test_mysql_fetchmany_slices_cached_rows(self):
        raw = self._raw([(1, "a"), (2, "b")])
        cursor = db.Cursor(raw, mysql=True)
        chunk = cursor.fetchmany(1)
        self.assertEqual(["a"], [row["name"] for row in chunk])
        self.assertEqual(["b"], [row["name"] for row in cursor.fetchall()])

    def test_mysql_iteration_returns_all_rows(self):
        cursor = db.Cursor(self._raw(), mysql=True)
        self.assertEqual([1, 2], [row["id"] for row in cursor])

    def test_mysql_empty_result(self):
        cursor = db.Cursor(self._raw([]), mysql=True)
        self.assertIsNone(cursor.fetchone())
        self.assertEqual([], cursor.fetchall())

    def test_mysql_exposes_underlying_cursor_metadata(self):
        raw = self._raw()
        raw.rowcount = 3
        raw.lastrowid = 9
        cursor = db.Cursor(raw, mysql=True)
        self.assertEqual(3, cursor.rowcount)
        self.assertEqual(9, cursor.lastrowid)
        self.assertEqual(raw.description, cursor.description)
        cursor.close()
        raw.close.assert_called_once_with()

    def test_sqlite_mode_forwards_every_call(self):
        raw = self._raw()
        raw.fetchone.return_value = (5, "raw")
        cursor = db.Cursor(raw, mysql=False)
        self.assertEqual((5, "raw"), cursor.fetchone())
        raw.fetchone.assert_called_once_with()
        self.assertEqual([(1, "a"), (2, "b")], cursor.fetchall())
        raw.fetchall.assert_called_once_with()
        self.assertEqual([(1, "a"), (2, "b")], list(cursor))
        self.assertEqual([(1, "a"), (2, "b")], cursor.fetchmany(2))
        raw.fetchmany.assert_called_once_with(2)



class AdaptSqlTest(unittest.TestCase):
    def test_sqlite_mode_returns_sql_unchanged(self):
        sql = "SELECT * FROM t_user WHERE username=? AND name LIKE '%x%'"
        self.assertEqual(sql, db.adapt_sql(sql, mysql=False, has_params=True))

    def test_begin_immediate_becomes_start_transaction(self):
        self.assertEqual(
            "START TRANSACTION", db.adapt_sql("BEGIN IMMEDIATE", mysql=True)
        )
        self.assertEqual(
            "START TRANSACTION", db.adapt_sql("  begin   immediate ", mysql=True)
        )

    def test_unrelated_begin_keeps_original_text(self):
        sql = "BEGIN; INSERT INTO t VALUES(1)"
        self.assertEqual(sql, db.adapt_sql(sql, mysql=True))

    def test_insert_or_replace_becomes_replace_into(self):
        adapted = db.adapt_sql(
            "  insert or replace into state(key,value) values(?,?)",
            mysql=True,
            has_params=True,
        )
        self.assertEqual("  REPLACE INTO state(key,value) values(%s,%s)", adapted)

    def test_on_conflict_becomes_on_duplicate_key_update(self):
        sql = (
            "INSERT INTO t_ai_permission(username,enabled,access_level,version) "
            "VALUES(?,?,?,?) "
            "ON CONFLICT(username) DO UPDATE SET enabled=excluded.enabled, "
            "access_level=excluded.access_level, version=excluded.version"
        )
        adapted = db.adapt_sql(sql, mysql=True, has_params=True)
        self.assertIn("ON DUPLICATE KEY UPDATE enabled=VALUES(enabled)", adapted)
        self.assertIn("access_level=VALUES(access_level)", adapted)
        self.assertIn("version=VALUES(version)", adapted)
        self.assertNotIn("excluded.", adapted)
        self.assertIn("VALUES(%s,%s,%s,%s)", adapted)

    def test_placeholders_are_converted_when_params_are_present(self):
        self.assertEqual(
            "SELECT a FROM t WHERE b=%s AND c=%s",
            db.adapt_sql("SELECT a FROM t WHERE b=? AND c=?", mysql=True, has_params=True),
        )
        self.assertEqual(
            "SELECT a FROM t WHERE b=%s",
            db.adapt_sql("SELECT a FROM t WHERE b=?", mysql=True),
        )

    def test_percent_literals_are_escaped_only_when_driver_formats_params(self):
        sql = "SELECT * FROM t WHERE name LIKE ? AND tail LIKE '%x%'"
        self.assertEqual(
            "SELECT * FROM t WHERE name LIKE %s AND tail LIKE '%%x%%'",
            db.adapt_sql(sql, mysql=True, has_params=True),
        )
        self.assertEqual(
            "SELECT * FROM t WHERE name LIKE %s AND tail LIKE '%x%'",
            db.adapt_sql(sql, mysql=True, has_params=False),
        )


class ConnectionTest(DbIsolationTest):
    def test_sqlite_rows_are_read_by_column_name(self):
        conn = self.open_sqlite()
        conn.execute(
            "CREATE TABLE t_user(username TEXT PRIMARY KEY, nickname TEXT)"
        )
        conn.execute("INSERT INTO t_user VALUES(?,?)", ("alice", "Alice"))
        conn.commit()
        row = conn.execute(
            "SELECT username, nickname FROM t_user WHERE username=?", ("alice",)
        ).fetchone()
        self.assertEqual("alice", row["username"])
        self.assertEqual("Alice", row[1])
        self.assertEqual([("alice", "Alice")], [tuple(r) for r in conn.execute("SELECT * FROM t_user")])

    def test_sqlite_accepts_list_params_and_executemany(self):
        conn = self.open_sqlite()
        conn.execute("CREATE TABLE t(a INTEGER, b TEXT)")
        conn.executemany("INSERT INTO t VALUES(?,?)", [(1, "x"), (2, "y")])
        conn.commit()
        self.assertEqual(2, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])
        conn.execute("INSERT INTO t VALUES(?,?)", [3, "z"])
        conn.commit()
        self.assertEqual(3, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])

    def test_sqlite_executescript_runs_multiple_statements(self):
        conn = self.open_sqlite()
        conn.executescript("CREATE TABLE t(a INTEGER); INSERT INTO t VALUES(1);")
        conn.commit()
        self.assertEqual(1, conn.execute("SELECT a FROM t").fetchone()[0])

    def test_sqlite_rollback_discards_writes(self):
        conn = self.open_sqlite()
        conn.execute("CREATE TABLE t(a INTEGER)")
        conn.commit()
        conn.execute("INSERT INTO t VALUES(1)")
        conn.rollback()
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])

    def test_sqlite_errors_are_wrapped_with_cause(self):
        conn = self.open_sqlite()
        with self.assertRaises(db.DatabaseError) as raised:
            conn.execute("SELECT * FROM missing_table")
        self.assertIsInstance(raised.exception.__cause__, sqlite3.Error)
        self.assertIn("missing_table", str(raised.exception))

    def test_commit_and_rollback_errors_are_wrapped(self):
        raw = mock.MagicMock()
        raw.commit.side_effect = sqlite3.OperationalError("commit boom")
        raw.rollback.side_effect = sqlite3.OperationalError("rollback boom")
        conn = db.Connection(raw, mysql=False)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.commit()
        self.assertEqual("commit boom", str(raised.exception))
        with self.assertRaises(db.DatabaseError) as raised:
            conn.rollback()
        self.assertEqual("rollback boom", str(raised.exception))

    def test_existing_database_error_is_not_rewrapped(self):
        raw = mock.MagicMock()
        raw.cursor.side_effect = db.DatabaseError("already wrapped")
        conn = db.Connection(raw, mysql=True)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.execute("SELECT 1")
        self.assertEqual("already wrapped", str(raised.exception))

    def test_context_manager_commits_and_closes(self):
        raw = mock.MagicMock()
        conn = db.Connection(raw, mysql=False)
        with conn as entered:
            self.assertIs(conn, entered)
        raw.commit.assert_called_once_with()
        raw.close.assert_called_once_with()

    def test_context_manager_rolls_back_on_error(self):
        raw = mock.MagicMock()
        conn = db.Connection(raw, mysql=False)
        with self.assertRaises(ValueError):
            with conn:
                raise ValueError("boom")
        raw.rollback.assert_called_once_with()
        raw.close.assert_called_once_with()

    def test_close_is_idempotent(self):
        raw = mock.MagicMock()
        conn = db.Connection(raw, mysql=False)
        conn.close()
        conn.close()
        raw.close.assert_called_once_with()

    def test_mysql_execute_translates_sql_and_parameters(self):
        raw = mock.MagicMock()
        conn = self.mysql_connection(raw)
        conn.execute("SELECT * FROM t WHERE a=? AND b=?", [1, 2])
        raw.cursor.return_value.execute.assert_called_once_with(
            "SELECT * FROM t WHERE a=%s AND b=%s", (1, 2)
        )

    def test_mysql_execute_without_params_passes_only_sql(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.fetchone.return_value = (1,)
        conn = self.mysql_connection(raw)
        conn.execute("BEGIN IMMEDIATE")
        # 先拿全局写锁再开事务，对齐 SQLite BEGIN IMMEDIATE 的串行语义
        self.assertEqual(
            [
                mock.call("SELECT GET_LOCK(%s, %s)", (db._lock_name("write"), db.LOCK_TIMEOUT_SECONDS)),
                mock.call("START TRANSACTION"),
            ],
            raw.cursor.return_value.execute.call_args_list,
        )

    def test_mysql_begin_immediate_fails_when_write_lock_times_out(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.fetchone.return_value = (0,)
        conn = self.mysql_connection(raw)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.execute("BEGIN IMMEDIATE")
        self.assertEqual("database is locked", str(raised.exception))
        self.assertFalse(conn._write_locked)

    def test_mysql_close_releases_write_lock_before_returning_to_pool(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.fetchone.return_value = (1,)
        conn = db.Connection(raw, mysql=True, pooled=True)
        conn.execute("BEGIN IMMEDIATE")
        conn.close()
        raw.cursor.return_value.execute.assert_called_with(
            "SELECT RELEASE_LOCK(%s)", (db._lock_name("write"),)
        )
        self.assertFalse(conn._write_locked)

    def test_mysql_executemany_translates_rows(self):
        raw = mock.MagicMock()
        conn = self.mysql_connection(raw)
        conn.executemany("INSERT INTO t VALUES(?,?)", [(1, "a"), (2, "b")])
        raw.cursor.return_value.executemany.assert_called_once_with(
            "INSERT INTO t VALUES(%s,%s)", [(1, "a"), (2, "b")]
        )

    def test_sqlite_executemany_error_is_wrapped(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.executemany.side_effect = sqlite3.OperationalError(
            "many boom"
        )
        conn = db.Connection(raw, mysql=False)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.executemany("INSERT INTO t VALUES(?)", [(1,)])
        self.assertEqual("many boom", str(raised.exception))

    def test_sqlite_executescript_error_is_wrapped(self):
        raw = mock.MagicMock()
        raw.executescript.side_effect = sqlite3.OperationalError("script boom")
        conn = db.Connection(raw, mysql=False)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.executescript("BAD SQL")
        self.assertEqual("script boom", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, sqlite3.Error)

    def test_mysql_executescript_splits_statements(self):
        raw = mock.MagicMock()
        conn = self.mysql_connection(raw)
        conn.executescript("CREATE TABLE a(x INT); ; CREATE TABLE b(y INT);")
        cursor = raw.cursor.return_value
        self.assertEqual(
            [mock.call("CREATE TABLE a(x INT)"), mock.call("CREATE TABLE b(y INT)")],
            cursor.execute.call_args_list,
        )

    def test_mysql_errors_are_wrapped(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.execute.side_effect = db.MySQLError("access denied")
        conn = self.mysql_connection(raw)
        with self.assertRaises(db.DatabaseError) as raised:
            conn.execute("SELECT 1")
        self.assertEqual("access denied", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, db.MySQLError)

    def test_pooled_connection_is_released_instead_of_closed(self):
        raw = mock.MagicMock()
        conn = self.mysql_connection(raw, pooled=True)
        with mock.patch.object(db, "_release") as release:
            conn.close()
        release.assert_called_once_with(raw)
        raw.close.assert_not_called()


class SchemaTest(DbIsolationTest):
    def test_register_schema_deduplicates_the_same_callable(self):
        db.register_schema(_record_schema)
        db.register_schema(_record_schema)
        db.register_schema(_other_schema)
        self.assertEqual(2, len(db._schema_initializers))
        self.assertEqual(1, db._schema_initializers.count(_record_schema))

    def test_ensure_schema_runs_only_once_per_key(self):
        conn = mock.MagicMock()
        db.register_schema(_record_schema)
        db.ensure_schema(conn, "key-once")
        db.ensure_schema(conn, "key-once")
        self.assertEqual([conn], _schema_calls)
        conn.commit.assert_called_once_with()

    def test_ensure_schema_failure_is_not_cached(self):
        conn = mock.MagicMock()
        db.register_schema(_failing_schema)
        with self.assertRaises(RuntimeError):
            db.ensure_schema(conn, "key-fail")
        self.assertNotIn("key-fail", db._initialized)
        with self.assertRaises(RuntimeError):
            db.ensure_schema(conn, "key-fail")
        self.assertEqual(2, len(_schema_calls))

    def test_reset_schema_cache_forgets_initialized_keys(self):
        db._initialized.add("sqlite:/tmp/a.db")
        db.reset_schema_cache()
        self.assertEqual(set(), db._initialized)

    def test_schema_key_uses_absolute_path_for_sqlite(self):
        self.assertEqual(
            "sqlite:" + str(Path(self.path).absolute()), db._schema_key(str(self.path))
        )
        self.assertEqual(
            "sqlite:" + db.DEFAULT_SQLITE_PATH, db._schema_key(None)
        )

    def test_schema_key_uses_dsn_for_mysql(self):
        with mock.patch.object(db, "IS_MYSQL", True), mock.patch.object(
            db, "_CONFIG", MYSQL_CONFIG
        ):
            self.assertEqual("mysql:db.internal:3307/guardian", db._schema_key(None))

    def test_sqlite_core_schema_creates_tables_and_backfills_columns(self):
        raw = sqlite3.connect(self.path)
        raw.row_factory = sqlite3.Row
        raw.execute("CREATE TABLE t_user(username TEXT PRIMARY KEY)")
        raw.commit()
        conn = db.Connection(raw, mysql=False)
        self.addCleanup(conn.close)
        db.create_core_schema(conn)
        conn.commit()
        columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(t_user)").fetchall()
        }
        self.assertTrue(
            {
                "username",
                "avatar_data",
                "avatar_mime",
                "avatar_updated_at",
                "is_frozen",
            }
            <= columns
        )
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertTrue({"t_user", "t_session", "t_sms_challenge", "t_contact_challenge"} <= tables)

    def test_mysql_core_schema_reads_information_schema_and_backfills_columns(self):
        conn = mock.MagicMock()
        cursor = mock.MagicMock()
        cursor.fetchall.return_value = [{"name": "username"}]
        conn.execute.return_value = cursor
        with mock.patch.object(db, "IS_MYSQL", True):
            db.create_core_schema(conn)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(9, len(statements))
        self.assertIn("information_schema.columns", statements[4])
        for column in ("avatar_data", "avatar_mime", "avatar_updated_at", "is_frozen"):
            self.assertTrue(
                any(f"ADD COLUMN {column}" in statement for statement in statements[5:])
            )

    def test_mysql_core_schema_skips_existing_columns(self):
        conn = mock.MagicMock()
        cursor = mock.MagicMock()
        cursor.fetchall.return_value = [
            {"name": name}
            for name in (
                "username",
                "avatar_data",
                "avatar_mime",
                "avatar_updated_at",
                "is_frozen",
            )
        ]
        conn.execute.return_value = cursor
        with mock.patch.object(db, "IS_MYSQL", True):
            db.create_core_schema(conn)
        statements = [call.args[0] for call in conn.execute.call_args_list]
        self.assertEqual(5, len(statements))


class GetDbTest(DbIsolationTest):
    def test_sqlite_get_db_creates_schema_once_and_returns_named_rows(self):
        db.register_schema(db.create_core_schema)
        first = db.get_db(str(self.path))
        self.addCleanup(first.close)
        first.execute(
            "INSERT INTO t_user(username, password_hash, create_time) VALUES(?,?,?)",
            ("alice", "hash", 1),
        )
        first.commit()
        second = db.get_db(str(self.path))
        self.addCleanup(second.close)
        row = second.execute(
            "SELECT username FROM t_user WHERE username=?", ("alice",)
        ).fetchone()
        self.assertEqual("alice", row["username"])
        self.assertEqual(1, len([key for key in db._initialized if key.startswith("sqlite:")]))

    def test_sqlite_get_db_closes_connection_when_schema_fails(self):
        raw = mock.MagicMock()
        db.register_schema(_failing_schema)
        with mock.patch.object(db.sqlite3, "connect", return_value=raw):
            with self.assertRaises(RuntimeError):
                db.get_db(str(self.path))
        raw.close.assert_called_once_with()
        self.assertNotIn("sqlite:" + str(Path(self.path).absolute()), db._initialized)

    def test_mysql_get_db_uses_pool_and_initializes_once(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.fetchone.return_value = (1,)
        db.register_schema(_record_schema)
        with mock.patch.object(db, "IS_MYSQL", True), mock.patch.object(
            db, "_CONFIG", MYSQL_CONFIG
        ), mock.patch.object(db, "_acquire", return_value=raw) as acquire:
            first = db.get_db()
            second = db.get_db()
            self.assertTrue(first._mysql)
            self.assertTrue(first._pooled)
            self.assertEqual(1, len(_schema_calls))
            self.assertEqual(2, acquire.call_count)
            # 建表期间持有跨进程 schema 锁，结束后释放
            executed = [c.args[0] for c in raw.cursor.return_value.execute.call_args_list]
            self.assertEqual(
                ["SELECT GET_LOCK(%s, %s)", "SELECT RELEASE_LOCK(%s)"], executed
            )
            first.close()
        raw.rollback.assert_called_once_with()
        self.assertEqual(1, db._pool.qsize())

    def test_connect_readonly_sqlite_reads_existing_database(self):
        writer = sqlite3.connect(self.path)
        writer.execute("CREATE TABLE t(a INTEGER)")
        writer.execute("INSERT INTO t VALUES(1)")
        writer.commit()
        writer.close()
        reader = db.connect_readonly(str(self.path))
        self.addCleanup(reader.close)
        self.assertEqual(1, reader.execute("SELECT a FROM t").fetchone()[0])
        with self.assertRaises(db.DatabaseError):
            reader.execute("INSERT INTO t VALUES(2)")

    def test_connect_readonly_sqlite_rejects_missing_database(self):
        missing = Path(self.tempdir.name) / "missing.db"
        with self.assertRaises(db.DatabaseError):
            db.connect_readonly(str(missing))

    def test_connect_readonly_mysql_returns_pooled_connection(self):
        raw = mock.MagicMock()
        with mock.patch.object(db, "IS_MYSQL", True), mock.patch.object(
            db, "_CONFIG", MYSQL_CONFIG
        ), mock.patch.object(db, "_acquire", return_value=raw):
            conn = db.connect_readonly()
        self.assertTrue(conn._mysql)
        conn.close()
        raw.rollback.assert_called_once_with()


class TransactionTest(DbIsolationTest):
    def test_sqlite_transaction_commits_on_success(self):
        conn = self.open_sqlite()
        conn.execute("CREATE TABLE t(a INTEGER)")
        conn.commit()
        with db.transaction(conn):
            conn.execute("INSERT INTO t VALUES(1)")
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])

    def test_sqlite_transaction_rolls_back_and_reraises(self):
        conn = self.open_sqlite()
        conn.execute("CREATE TABLE t(a INTEGER)")
        conn.commit()
        with self.assertRaises(ValueError):
            with db.transaction(conn):
                conn.execute("INSERT INTO t VALUES(1)")
                raise ValueError("abort")
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM t").fetchone()[0])
        self.assertFalse(conn._closed)

    def test_owned_transaction_commits_and_closes(self):
        conn = mock.MagicMock()
        with mock.patch.object(db, "get_db", return_value=conn):
            with db.transaction():
                pass
        conn.execute.assert_called_once_with("BEGIN IMMEDIATE")
        conn.commit.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_owned_transaction_rolls_back_and_closes_on_error(self):
        conn = mock.MagicMock()
        with mock.patch.object(db, "get_db", return_value=conn):
            with self.assertRaises(RuntimeError):
                with db.transaction():
                    raise RuntimeError("abort")
        conn.rollback.assert_called_once_with()
        conn.close.assert_called_once_with()

    def test_mysql_transaction_uses_start_transaction(self):
        raw = mock.MagicMock()
        raw.cursor.return_value.fetchone.return_value = (1,)
        conn = self.mysql_connection(raw)
        with db.transaction(conn):
            pass
        executed = [c.args[0] for c in raw.cursor.return_value.execute.call_args_list]
        self.assertEqual(
            ["SELECT GET_LOCK(%s, %s)", "START TRANSACTION", "SELECT RELEASE_LOCK(%s)"],
            executed,
        )
        raw.commit.assert_called_once_with()
        raw.close.assert_not_called()


class PoolTest(DbIsolationTest):
    def test_new_connection_requires_driver_when_mysql_requested(self):
        with mock.patch.object(db, "pymysql", None):
            with self.assertRaises(db.DatabaseError) as raised:
                db._new_mysql_connection()
        self.assertIn("PyMySQL", str(raised.exception))

    def test_new_connection_passes_dsn_timeouts_and_flags(self):
        driver = mock.MagicMock()
        driver.connect.return_value = "raw-connection"
        with mock.patch.object(db, "pymysql", driver), mock.patch.object(
            db, "_CONFIG", MYSQL_CONFIG
        ):
            self.assertEqual("raw-connection", db._new_mysql_connection())
        kwargs = driver.connect.call_args.kwargs
        self.assertEqual("db.internal", kwargs["host"])
        self.assertEqual(3307, kwargs["port"])
        self.assertEqual("guardian", kwargs["user"])
        self.assertEqual("p@ss", kwargs["password"])
        self.assertEqual("guardian", kwargs["database"])
        self.assertEqual("utf8mb4", kwargs["charset"])
        self.assertFalse(kwargs["autocommit"])
        self.assertEqual(5, kwargs["connect_timeout"])
        self.assertEqual(db.MYSQL_CLIENT.FOUND_ROWS, kwargs["client_flag"])

    def test_new_connection_failure_is_wrapped(self):
        driver = mock.MagicMock()
        driver.connect.side_effect = db.MySQLError("refused")
        with mock.patch.object(db, "pymysql", driver), mock.patch.object(
            db, "_CONFIG", MYSQL_CONFIG
        ):
            with self.assertRaises(db.DatabaseError) as raised:
                db._new_mysql_connection()
        self.assertEqual("refused", str(raised.exception))
        self.assertIsInstance(raised.exception.__cause__, db.MySQLError)

    def test_acquire_creates_connection_when_pool_is_empty(self):
        with mock.patch.object(db, "_new_mysql_connection", return_value="fresh"):
            self.assertEqual("fresh", db._acquire())

    def test_acquire_reuses_and_pings_pooled_connection(self):
        raw = mock.MagicMock()
        db._pool.put(raw)
        self.assertIs(raw, db._acquire())
        raw.ping.assert_called_once_with(reconnect=True)

    def test_acquire_replaces_dead_pooled_connection(self):
        raw = mock.MagicMock()
        raw.ping.side_effect = db.MySQLError("dead")
        db._pool.put(raw)
        with mock.patch.object(db, "_new_mysql_connection", return_value="fresh"):
            self.assertEqual("fresh", db._acquire())
        raw.close.assert_called_once_with()

    def test_release_rolls_back_and_returns_connection_to_pool(self):
        raw = mock.MagicMock()
        db._release(raw)
        raw.rollback.assert_called_once_with()
        self.assertIs(raw, db._pool.get_nowait())

    def test_release_closes_connection_when_pool_is_full(self):
        with mock.patch.object(db, "_pool", queue.LifoQueue(maxsize=1)) as pool:
            pool.put("occupied")
            raw = mock.MagicMock()
            db._release(raw)
            raw.close.assert_called_once_with()
            self.assertEqual("occupied", pool.get_nowait())

    def test_release_survives_rollback_failure(self):
        raw = mock.MagicMock()
        raw.rollback.side_effect = db.MySQLError("lost")
        db._release(raw)
        self.assertIs(raw, db._pool.get_nowait())


if __name__ == "__main__":
    unittest.main()