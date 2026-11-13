"""Database access layer shared by the account service and the MQTT plugins.

SQLite stays the default and keeps the historical behaviour. Setting ``DB_URL``
switches every caller to MySQL and translates the SQLite-only syntax this
project uses into MySQL equivalents.
"""

import os
import queue
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

try:
    import pymysql
    from pymysql.constants import CLIENT as MYSQL_CLIENT
    from pymysql.err import MySQLError
except ModuleNotFoundError:  # MySQL 模式才需要 PyMySQL
    pymysql = None
    MYSQL_CLIENT = None
    MySQLError = type("_MissingMySQLDriverError", (Exception,), {})


DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "guardian_users.db"
)
POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "8"))


class DatabaseError(Exception):
    """统一暴露存储层错误，调用方不再直接依赖 sqlite3 或 PyMySQL 的异常类型。"""


def _wrap_error(error):
    if isinstance(error, DatabaseError):
        return error
    return DatabaseError(str(error) or type(error).__name__)


def parse_db_url(url):
    """把 DB_URL 解析成 SQLite 或 MySQL 的连接描述。"""
    url = (url or "").strip()
    if not url:
        return {"kind": "sqlite", "path": DEFAULT_SQLITE_PATH, "query": {}}
    if url.startswith("sqlite://"):
        path = unquote(url[len("sqlite://"):])
        if re.match(r"^/[A-Za-z]:", path):
            path = path[1:]
        return {"kind": "sqlite", "path": path or DEFAULT_SQLITE_PATH, "query": {}}
    parsed = urlparse(url)
    if parsed.scheme.split("+")[0] not in ("mysql", "mariadb"):
        raise DatabaseError("DB_URL 只支持 sqlite:// 或 mysql://")
    database = parsed.path.lstrip("/")
    if not parsed.hostname or not database:
        raise DatabaseError("DB_URL 缺少主机名或数据库名")
    query = parse_qs(parsed.query)
    return {
        "kind": "mysql",
        "dsn": {
            "host": parsed.hostname,
            "port": parsed.port or 3306,
            "user": unquote(parsed.username or ""),
            "password": unquote(parsed.password or ""),
            "database": database,
            "charset": (query.get("charset") or ["utf8mb4"])[0],
        },
        "query": query,
    }


_CONFIG = parse_db_url(os.environ.get("DB_URL", ""))
IS_MYSQL = _CONFIG["kind"] == "mysql"


class Row:
    """按字段名或下标取值的行对象，语义对齐 sqlite3.Row。"""

    __slots__ = ("_keys", "_values")

    def __init__(self, keys, values):
        self._keys = tuple(keys)
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        try:
            return self._values[self._keys.index(key)]
        except ValueError:
            raise IndexError(f"没有名为 {key!r} 的列") from None

    def __iter__(self):
        return iter(self._values)

    def __len__(self):
        return len(self._values)

    def __contains__(self, key):
        return key in self._keys

    def keys(self):
        return list(self._keys)

    def get(self, key, default=None):
        try:
            return self[key]
        except (IndexError, KeyError, ValueError):
            return default

    def __eq__(self, other):
        if isinstance(other, Row):
            return self._values == other._values
        if isinstance(other, tuple):
            return self._values == other
        return NotImplemented

    def __repr__(self):
        return f"Row({dict(zip(self._keys, self._values))!r})"


class Cursor:
    """对底层游标的薄包装，MySQL 模式下把元组行转换成 Row。"""

    def __init__(self, raw, mysql):
        self._raw = raw
        self._mysql = mysql
        self._cache = None

    def _load(self):
        if self._cache is None:
            description = self._raw.description or ()
            keys = [column[0] for column in description]
            self._cache = [Row(keys, values) for values in self._raw.fetchall()]
        return self._cache

    def fetchone(self):
        if not self._mysql:
            return self._raw.fetchone()
        rows = self._load()
        return rows.pop(0) if rows else None

    def fetchall(self):
        if not self._mysql:
            return self._raw.fetchall()
        return list(self._load())

    def fetchmany(self, size=1):
        if not self._mysql:
            return self._raw.fetchmany(size)
        rows = self._load()
        chunk = rows[:size]
        del rows[:size]
        return chunk

    def __iter__(self):
        return iter(self.fetchall())

    @property
    def rowcount(self):
        return self._raw.rowcount

    @property
    def lastrowid(self):
        return self._raw.lastrowid

    @property
    def description(self):
        return self._raw.description

    def close(self):
        self._raw.close()


_BEGIN_IMMEDIATE = re.compile(r"^\s*BEGIN\s+IMMEDIATE\s*$", re.IGNORECASE)
_INSERT_OR_REPLACE = re.compile(
    r"^(\s*)INSERT\s+OR\s+REPLACE\s+INTO\b", re.IGNORECASE
)
_ON_CONFLICT = re.compile(
    r"\s*ON\s+CONFLICT\s*\([^)]*\)\s*DO\s+UPDATE\s+SET\s+", re.IGNORECASE
)
_EXCLUDED = re.compile(r"\bexcluded\.([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def adapt_sql(sql, mysql=None, has_params=False):
    """SQLite 专属写法在 MySQL 模式下的等价改写。SQLite 模式原样返回。"""
    mysql = IS_MYSQL if mysql is None else mysql
    if not mysql:
        return sql
    text = sql
    if _BEGIN_IMMEDIATE.match(text):
        return "START TRANSACTION"
    text = _INSERT_OR_REPLACE.sub(r"\1REPLACE INTO", text)
    if _ON_CONFLICT.search(text):
        text = _ON_CONFLICT.sub(" ON DUPLICATE KEY UPDATE ", text)
        text = _EXCLUDED.sub(lambda match: f"VALUES({match.group(1)})", text)
    if has_params:
        text = text.replace("%", "%%")
    return text.replace("?", "%s")


class Connection:
    """统一连接接口；SQLite 模式原样转发，MySQL 模式做方言适配。"""

    def __init__(self, raw, mysql=None, pooled=False):
        self._raw = raw
        self._mysql = IS_MYSQL if mysql is None else mysql
        self._pooled = pooled
        self._closed = False
        self._write_locked = False

    def _begin_immediate(self):
        # SQLite 的 BEGIN IMMEDIATE 会立刻拿到全库写锁，业务里“先查后改”都靠它串行。
        # MySQL 的 START TRANSACTION 不加锁，所以先拿同名的会话锁再开事务，语义对齐。
        # 上限：所有写事务全局串行，吞吐与 SQLite 相同；要并发时改成逐处 SELECT ... FOR UPDATE。
        _named_lock(self._raw, _WRITE_LOCK)
        self._write_locked = True
        try:
            self._raw.cursor().execute("START TRANSACTION")
        except MySQLError as error:
            self._release_write_lock()
            raise _wrap_error(error) from error
        return Cursor(self._raw.cursor(), True)

    def _release_write_lock(self):
        if self._write_locked:
            self._write_locked = False
            _named_unlock(self._raw, _WRITE_LOCK)

    def execute(self, sql, params=None):
        if self._mysql and _BEGIN_IMMEDIATE.match(sql):
            return self._begin_immediate()
        statement = adapt_sql(sql, self._mysql, bool(params))
        try:
            cursor = self._raw.cursor()
            if params:
                cursor.execute(statement, tuple(params))
            else:
                cursor.execute(statement)
        except (sqlite3.Error, MySQLError) as error:
            raise _wrap_error(error) from error
        return Cursor(cursor, self._mysql)

    def executemany(self, sql, params):
        statement = adapt_sql(sql, self._mysql, True)
        try:
            cursor = self._raw.cursor()
            cursor.executemany(statement, [tuple(row) for row in params])
        except (sqlite3.Error, MySQLError) as error:
            raise _wrap_error(error) from error
        return Cursor(cursor, self._mysql)

    def executescript(self, script):
        if not self._mysql:
            try:
                self._raw.executescript(script)
            except sqlite3.Error as error:
                raise _wrap_error(error) from error
            return None
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement.strip())
        return None

    def commit(self):
        try:
            self._raw.commit()
        except (sqlite3.Error, MySQLError) as error:
            raise _wrap_error(error) from error
        finally:
            self._release_write_lock()

    def rollback(self):
        try:
            self._raw.rollback()
        except (sqlite3.Error, MySQLError) as error:
            raise _wrap_error(error) from error
        finally:
            self._release_write_lock()

    def close(self):
        if self._closed:
            return
        self._closed = True
        if self._write_locked:
            # 会话锁跟着物理连接走，放回连接池前必须释放，否则下一个借用者会一直占着
            try:
                self._raw.rollback()
            except MySQLError:
                pass
            self._release_write_lock()
        if self._pooled:
            _release(self._raw)
        else:
            self._raw.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


_pool = queue.LifoQueue(maxsize=POOL_SIZE)
_schema_initializers = []
_schema_names = set()
_initialized = set()
_schema_lock = threading.Lock()


def register_schema(initializer):
    """注册建表函数；同一函数重复注册只保留一次。"""
    name = f"{initializer.__module__}.{initializer.__qualname__}"
    with _schema_lock:
        if name in _schema_names:
            return
        _schema_names.add(name)
        _schema_initializers.append(initializer)


def _new_mysql_connection():
    if pymysql is None:
        raise DatabaseError("DB_URL 指向 MySQL，但当前环境没有安装 PyMySQL")
    config = dict(_CONFIG["dsn"])
    try:
        return pymysql.connect(
            **config,
            autocommit=False,
            connect_timeout=5,
            client_flag=MYSQL_CLIENT.FOUND_ROWS,
        )
    except MySQLError as error:
        raise _wrap_error(error) from error


LOCK_TIMEOUT_SECONDS = 10
_WRITE_LOCK = "write"
_SCHEMA_LOCK = "schema"


def _lock_name(kind):
    # 会话锁是整个 MySQL 实例共享的，带上库名，免得同实例的其他库互相阻塞
    return f"caring:{_CONFIG.get('dsn', {}).get('database', '')}:{kind}"[:64]


def _named_lock(raw, kind):
    try:
        cursor = raw.cursor()
        cursor.execute("SELECT GET_LOCK(%s, %s)", (_lock_name(kind), LOCK_TIMEOUT_SECONDS))
        got = cursor.fetchone()[0]
    except MySQLError as error:
        raise _wrap_error(error) from error
    if got != 1:
        raise DatabaseError("database is locked")


def _named_unlock(raw, kind):
    try:
        raw.cursor().execute("SELECT RELEASE_LOCK(%s)", (_lock_name(kind),))
    except MySQLError:
        pass


def _acquire():
    try:
        raw = _pool.get_nowait()
    except queue.Empty:
        return _new_mysql_connection()
    try:
        raw.ping(reconnect=True)
    except MySQLError:
        try:
            raw.close()
        except MySQLError:
            pass
        return _new_mysql_connection()
    return raw


def _release(raw):
    try:
        raw.rollback()
    except MySQLError:
        pass
    try:
        _pool.put_nowait(raw)
    except queue.Full:
        try:
            raw.close()
        except MySQLError:
            pass


def _schema_key(path):
    if IS_MYSQL:
        dsn = _CONFIG["dsn"]
        return f"mysql:{dsn['host']}:{dsn['port']}/{dsn['database']}"
    return "sqlite:" + os.path.abspath(path or DEFAULT_SQLITE_PATH)


def ensure_schema(conn, key):
    """每个进程、每个目标库只初始化一次表结构。"""
    if key in _initialized:
        return
    with _schema_lock:
        if key in _initialized:
            return
        # 多个 worker 同时启动会并发 DROP/CREATE TRIGGER、ALTER TABLE，
        # 实测报 “Trigger already exists” 和死锁；用跨进程会话锁让建表一个一个来
        locked = isinstance(conn, Connection) and conn._mysql
        if locked:
            _named_lock(conn._raw, _SCHEMA_LOCK)
        try:
            for initializer in tuple(_schema_initializers):
                initializer(conn)
            conn.commit()
        finally:
            if locked:
                _named_unlock(conn._raw, _SCHEMA_LOCK)
        _initialized.add(key)


def reset_schema_cache():
    """仅供测试：清空“已初始化”标记。"""
    with _schema_lock:
        _initialized.clear()


def get_db(path=None):
    """返回可读写的连接；首次访问某个目标库时执行一次建表。"""
    if IS_MYSQL:
        conn = Connection(_acquire(), mysql=True, pooled=True)
    else:
        target = os.path.abspath(path or DEFAULT_SQLITE_PATH)
        try:
            raw = sqlite3.connect(target)
            raw.row_factory = sqlite3.Row
        except sqlite3.Error as error:
            raise _wrap_error(error) from error
        conn = Connection(raw, mysql=False)
    key = _schema_key(path)
    if key in _initialized:
        return conn
    try:
        ensure_schema(conn, key)
    except Exception:
        conn.close()
        raise
    return conn


def connect_readonly(path=None):
    """只读连接。SQLite 打不开已存在的库时直接失败，不会悄悄新建空库。"""
    if IS_MYSQL:
        return Connection(_acquire(), mysql=True, pooled=True)
    target = os.path.abspath(path or DEFAULT_SQLITE_PATH)
    try:
        raw = sqlite3.connect(
            Path(target).resolve().as_uri() + "?mode=ro", uri=True, timeout=1
        )
        raw.row_factory = sqlite3.Row
    except sqlite3.Error as error:
        raise _wrap_error(error) from error
    return Connection(raw, mysql=False)


@contextmanager
def transaction(conn=None):
    """事务封装：SQLite 用 BEGIN IMMEDIATE，MySQL 用 START TRANSACTION。"""
    owned = conn is None
    current = conn or get_db()
    try:
        current.execute("BEGIN IMMEDIATE")
        yield current
        current.commit()
    except Exception:
        current.rollback()
        raise
    finally:
        if owned:
            current.close()


_SQLITE_CORE_SCHEMA = """
    CREATE TABLE IF NOT EXISTS t_user (
        username      TEXT PRIMARY KEY,
        nickname      TEXT,
        phone         TEXT,
        password_hash TEXT NOT NULL,
        avatar_path   TEXT,
        email         TEXT,
        address       TEXT,
        create_time   INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS t_session (
        access_token_hash  TEXT PRIMARY KEY,
        refresh_token_hash TEXT NOT NULL UNIQUE,
        username           TEXT NOT NULL,
        access_expires_at  INTEGER NOT NULL,
        refresh_expires_at INTEGER NOT NULL,
        create_time        INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS t_sms_challenge (
        challenge_hash TEXT PRIMARY KEY,
        phone          TEXT NOT NULL,
        purpose        TEXT NOT NULL,
        requester_ip   TEXT NOT NULL,
        sent_at        INTEGER NOT NULL,
        expires_at     INTEGER NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        checking_at    INTEGER,
        consumed_at    INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_sms_challenge_phone_sent
        ON t_sms_challenge(phone, sent_at);
    CREATE INDEX IF NOT EXISTS idx_sms_challenge_ip_sent
        ON t_sms_challenge(requester_ip, sent_at);
    CREATE TABLE IF NOT EXISTS t_contact_challenge (
        challenge_hash TEXT PRIMARY KEY,
        username       TEXT NOT NULL,
        kind           TEXT NOT NULL,
        value          TEXT NOT NULL,
        code_hash      TEXT,
        requester_ip   TEXT NOT NULL,
        sent_at        INTEGER NOT NULL,
        expires_at     INTEGER NOT NULL,
        failed_attempts INTEGER NOT NULL DEFAULT 0,
        checking_at    INTEGER,
        consumed_at    INTEGER
    );
    CREATE INDEX IF NOT EXISTS idx_contact_value_sent
        ON t_contact_challenge(kind, value, sent_at);
    CREATE INDEX IF NOT EXISTS idx_contact_ip_sent
        ON t_contact_challenge(requester_ip, sent_at);
"""

_MYSQL_USER_COLUMNS = (
    ("avatar_data", "MEDIUMBLOB"),
    ("avatar_mime", "VARCHAR(64)"),
    ("avatar_updated_at", "BIGINT"),
    ("is_frozen", "TINYINT NOT NULL DEFAULT 0"),
)

_MYSQL_TABLE_SUFFIX = " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin"

_MYSQL_CORE_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS t_user (
        username          VARCHAR(64) NOT NULL PRIMARY KEY,
        nickname          VARCHAR(128),
        phone             VARCHAR(20),
        password_hash     VARCHAR(255) NOT NULL,
        avatar_path       VARCHAR(512),
        email             VARCHAR(254),
        address           VARCHAR(512),
        create_time       BIGINT NOT NULL,
        avatar_data       MEDIUMBLOB,
        avatar_mime       VARCHAR(64),
        avatar_updated_at BIGINT,
        is_frozen         TINYINT NOT NULL DEFAULT 0,
        KEY idx_user_phone (phone),
        KEY idx_user_email (email)
    )""" + _MYSQL_TABLE_SUFFIX,
    """
    CREATE TABLE IF NOT EXISTS t_session (
        access_token_hash  VARCHAR(64) NOT NULL PRIMARY KEY,
        refresh_token_hash VARCHAR(64) NOT NULL UNIQUE,
        username           VARCHAR(64) NOT NULL,
        access_expires_at  BIGINT NOT NULL,
        refresh_expires_at BIGINT NOT NULL,
        create_time        BIGINT NOT NULL,
        KEY idx_session_user (username),
        KEY idx_session_refresh_expires (refresh_expires_at)
    )""" + _MYSQL_TABLE_SUFFIX,
    """
    CREATE TABLE IF NOT EXISTS t_sms_challenge (
        challenge_hash  VARCHAR(64) NOT NULL PRIMARY KEY,
        phone           VARCHAR(20) NOT NULL,
        purpose         VARCHAR(32) NOT NULL,
        requester_ip    VARCHAR(64) NOT NULL,
        sent_at         BIGINT NOT NULL,
        expires_at      BIGINT NOT NULL,
        failed_attempts INT NOT NULL DEFAULT 0,
        checking_at     BIGINT NULL,
        consumed_at     BIGINT NULL,
        KEY idx_sms_challenge_phone_sent (phone, sent_at),
        KEY idx_sms_challenge_ip_sent (requester_ip, sent_at)
    )""" + _MYSQL_TABLE_SUFFIX,
    """
    CREATE TABLE IF NOT EXISTS t_contact_challenge (
        challenge_hash  VARCHAR(64) NOT NULL PRIMARY KEY,
        username        VARCHAR(64) NOT NULL,
        kind            VARCHAR(16) NOT NULL,
        `value`         VARCHAR(254) NOT NULL,
        code_hash       VARCHAR(64),
        requester_ip    VARCHAR(64) NOT NULL,
        sent_at         BIGINT NOT NULL,
        expires_at      BIGINT NOT NULL,
        failed_attempts INT NOT NULL DEFAULT 0,
        checking_at     BIGINT NULL,
        consumed_at     BIGINT NULL,
        KEY idx_contact_value_sent (kind, `value`, sent_at),
        KEY idx_contact_ip_sent (requester_ip, sent_at)
    )""" + _MYSQL_TABLE_SUFFIX,
)


def _sqlite_core_schema(conn):
    conn.executescript(_SQLITE_CORE_SCHEMA)
    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(t_user)").fetchall()
    }
    for column, definition in _MYSQL_USER_COLUMNS:
        if column not in columns:
            conn.execute(f"ALTER TABLE t_user ADD COLUMN {column} {definition}")


def _mysql_core_schema(conn):
    for statement in _MYSQL_CORE_STATEMENTS:
        conn.execute(statement)
    rows = conn.execute(
        "SELECT COLUMN_NAME AS name FROM information_schema.columns "
        "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='t_user'"
    ).fetchall()
    columns = {row["name"] for row in rows}
    for column, definition in _MYSQL_USER_COLUMNS:
        if column not in columns:
            conn.execute(f"ALTER TABLE t_user ADD COLUMN {column} {definition}")


def create_core_schema(conn):
    """账号库核心表：SQLite 原生脚本或 MySQL 等价 DDL。"""
    if IS_MYSQL:
        _mysql_core_schema(conn)
    else:
        _sqlite_core_schema(conn)