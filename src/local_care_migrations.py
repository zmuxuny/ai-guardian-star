"""Transactional migrations for a dedicated, local-only SQLite database.

Schema/PRAGMA queries are database-level maintenance. Business tables and all
business queries use both person_id and model_version. No global metadata table
or cloud connection is used. Existing databases are backed up before upgrading.
"""

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3
import uuid


APPLICATION_ID = 0x43415245
LATEST_VERSION = 3
_SQL_ROOT = Path(__file__).resolve().parent / 'migrations' / 'local_care'
MIGRATIONS = {1: _SQL_ROOT / '001_initial.sql', 2: _SQL_ROOT / '002_baseline_source.sql',
              3: _SQL_ROOT / '003_delivery.sql'}
_KEYS = {
    'feedback': ('person_id', 'model_version', 'target_id', 'window_start'),
    'feedback_audit': ('person_id', 'model_version', 'target_id', 'window_start', 'revision'),
    'baseline_samples': ('person_id', 'model_version', 'sample_id'),
    'care_events': ('person_id', 'model_version', 'event_id'),
    'care_sessions': ('person_id', 'model_version', 'mode'),
    'care_outbox': ('person_id', 'model_version', 'message_id'),
}
_COLUMNS = {
    'feedback': {'person_id', 'model_version', 'target_id', 'window_start', 'event_at',
                 'payload_json', 'created_at', 'updated_at', 'is_revoked', 'revoked_at',
                 'revocation_reason', 'revision'},
    'feedback_audit': {'person_id', 'model_version', 'target_id', 'window_start', 'revision',
                       'operation', 'recorded_at', 'snapshot_json'},
    'baseline_samples': {'person_id', 'model_version', 'sample_id', 'category',
                         'payload_json', 'sampled_at', 'created_at', 'updated_at'},
    'care_events': {'person_id','model_version','event_id','mode','kind','region_id','started_at','ended_at'},
    'care_sessions': {'person_id','model_version','mode','checkpoint_json','active_event_id','updated_at'},
    'care_outbox': {'person_id','model_version','message_id','mode','event_id','message_type','revision',
                    'payload_json','created_at','attempts','last_error','delivered_at'},
}
_INDEXES = {
    'feedback_scope_status_time': ('feedback', ('person_id', 'model_version', 'is_revoked',
                                               'updated_at', 'target_id', 'window_start')),
    'baseline_scope_category_time': ('baseline_samples', ('person_id', 'model_version',
                                                          'category', 'sampled_at', 'sample_id')),
    'care_events_scope_time': ('care_events', ('person_id','model_version','mode','started_at','event_id')),
    'care_outbox_scope_pending': ('care_outbox', ('person_id','model_version','delivered_at','created_at',
                                               'event_id','message_type','revision')),
}


def database_path(path):
    if not isinstance(path, (str, os.PathLike)) or not str(path).strip():
        raise ValueError('a local database file is required')
    if str(path) == ':memory:' or str(path).startswith('file:'):
        raise ValueError('memory databases and SQLite URI paths are not durable local stores')
    result = Path(path).expanduser().resolve()
    if result.is_dir():
        raise ValueError('database path must be a file')
    return result


@contextmanager
def connection(path):
    db = sqlite3.connect(str(path), timeout=5, isolation_level=None)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=5000')
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA journal_mode').fetchone()[0].lower() not in ('delete', 'wal', 'truncate', 'persist'):
            raise ValueError('database must use a durable journal mode')
        yield db
    finally:
        db.close()


def _version(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    app_id = db.execute('PRAGMA application_id').fetchone()[0]
    objects = db.execute("SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
    if version == 0:
        if objects or app_id not in (0, APPLICATION_ID):
            raise ValueError('refusing to adopt an unknown database')
    elif app_id != APPLICATION_ID or version not in (1, 2, 3):
        raise ValueError('unknown database or unsupported schema version')
    else:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected_tables = set(_KEYS) if version >= 3 else set(_KEYS) - {'care_events','care_sessions','care_outbox'}
        if tables != expected_tables:
            raise ValueError('incomplete local care schema')
        for table, key in _KEYS.items():
            if table not in expected_tables:
                continue
            # Identifiers are internal constants, never caller-supplied SQL.
            columns = db.execute(f'PRAGMA table_info({table})').fetchall()
            actual_key = tuple(r['name'] for r in sorted(columns, key=lambda r: r['pk']) if r['pk'])
            expected = _COLUMNS[table] | ({'source'} if table == 'baseline_samples' and version >= 2 else set())
            if actual_key != key or {r['name'] for r in columns} != expected:
                raise ValueError('incompatible local care schema')
            indexes = db.execute(f'PRAGMA index_list({table})').fetchall()
            actual_indexes = {}
            for index in indexes:
                names = tuple(r[0] for r in db.execute(
                    'SELECT name FROM pragma_index_info(?) ORDER BY seqno', (index['name'],)))
                if not {'person_id', 'model_version'} <= set(names):
                    raise ValueError('index is missing person/model scope')
                actual_indexes[index['name']] = names
            for name, (owner, expected_columns) in _INDEXES.items():
                if owner == table and actual_indexes.get(name) != expected_columns:
                    raise ValueError('required scope index is missing or incompatible')
        foreign_keys = db.execute('PRAGMA foreign_key_list(feedback_audit)').fetchall()
        if (len(foreign_keys) != 4 or len({r['id'] for r in foreign_keys}) != 1
                or any(r['table'] != 'feedback' for r in foreign_keys)
                or tuple((r['from'], r['to']) for r in sorted(foreign_keys, key=lambda r: r['seq']))
                != tuple((name, name) for name in _KEYS['feedback'])):
            raise ValueError('audit foreign key is missing person/model scope')
    return version


def _statements(script):
    """Do not use executescript: it can commit a caller's transaction."""
    pending = ''
    for character in script:
        pending += character
        if character == ';' and sqlite3.complete_statement(pending):
            yield pending
            pending = ''
    if pending.strip():
        raise ValueError('migration must end with a complete SQL statement')


def _backup(db, path, version):
    target = path.with_name(path.name + f'.v{version}-{uuid.uuid4().hex}.backup.db')
    # Never overwrite an existing backup. backup() handles committed WAL data too.
    descriptor = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    try:
        destination = sqlite3.connect(str(target))
        try:
            db.backup(destination)
        finally:
            destination.close()
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return str(target)


def migrate_database(path, target_version=None):
    """Create/upgrade atomically; never downgrade, erase or rewrite old rows.

    Return from_version, to_version, and backup_path (None for fresh/no-op runs).
    Upgrading an existing store creates a SQLite-consistent sibling backup.
    SQL files are packaged next to this module and must be deployed with it.
    """
    target = LATEST_VERSION if target_version is None else target_version
    if type(target) is not int or target not in MIGRATIONS:
        raise ValueError('unsupported target version')
    path = database_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with connection(path) as db:
        db.execute('BEGIN IMMEDIATE')
        try:
            # All version/structure reads use one writer-locked snapshot. A
            # concurrent initializer cannot change the version between reads.
            version = _version(db)
            if version > target:
                raise ValueError('schema downgrade is forbidden')
            if 0 < version < target:
                # This writer has not changed anything yet. Its reserved lock
                # blocks other writers but permits a separate read connection
                # to back up the committed snapshot. Backing up THIS connection
                # inside its write transaction could block on itself.
                with connection(path) as source:
                    backup = _backup(source, path, version)
            for next_version in range(version + 1, target + 1):
                for statement in _statements(MIGRATIONS[next_version].read_text(encoding='utf-8')):
                    db.execute(statement)
                db.execute(f'PRAGMA application_id={APPLICATION_ID}')
                db.execute(f'PRAGMA user_version={next_version}')
            _version(db)
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction:
                db.execute('ROLLBACK')
            raise
    return {'from_version': version, 'to_version': target, 'backup_path': backup}
