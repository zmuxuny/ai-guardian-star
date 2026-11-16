"""Offline persistence, isolation, atomicity and migration acceptance tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import json
import io
import re
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from src.local_care_store import LocalCareStore
from src.local_care_migrations import migrate_database, LATEST_VERSION


@contextmanager
def raw_db(path):
    db = sqlite3.connect(path)
    try:
        with db:
            yield db
    finally:
        db.close()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'care.db'
        self.now = 1000.0
        self.store = LocalCareStore(self.path, 'person-a', 'model-v1', clock=lambda: self.now)

    def submit(self, store=None, **kwargs):
        return (store or self.store).submit_feedback('event-1', 601, {'label': 'normal'}, **kwargs)

    def test_repeated_feedback_updates_one_row_preserves_created_and_logs_history(self):
        first = self.submit()
        self.assertEqual(first['window_start'], 600)
        for n in range(5):
            self.now = 2000 + n
            updated = self.store.submit_feedback('event-1', 601, {'label': f'new-{n}'})
        self.assertEqual(self.store.count_feedback(), 1)
        self.assertEqual(updated['created_at'], 1000)
        self.assertEqual(updated['updated_at'], 2004)
        self.assertEqual(updated['payload'], {'label': 'new-4'})
        self.assertEqual(updated['revision'], 6)
        history = self.store.feedback_audit('event-1', 601, status='active')
        self.assertEqual(len(history), 6)
        self.assertEqual(history[0]['snapshot']['payload'], {'label': 'normal'})
        with raw_db(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM feedback').fetchone()[0], 1)

    def test_event_time_not_submission_time_controls_window(self):
        self.submit()
        self.now = 99999
        self.submit()
        self.assertEqual(self.store.count_feedback(), 1)
        self.store.submit_feedback('event-1', 899.999, {'label': 'same-window'})
        self.assertEqual(self.store.count_feedback(), 1)
        self.store.submit_feedback('event-1', 900, {'label': 'next-window'})
        self.assertEqual(self.store.count_feedback(), 2)

    def test_revoke_default_hidden_explicit_visible_and_retry_does_not_restore(self):
        first = self.submit()
        self.now = 2000
        revoked = self.store.revoke_feedback('event-1', 601, reason='changed mind')
        self.assertTrue(revoked['is_revoked'])
        self.assertEqual(revoked['revoked_at'], 2000)
        self.assertEqual(self.store.list_feedback(), [])
        self.assertIsNone(self.store.get_feedback('event-1', 601))
        self.assertEqual(self.store.count_feedback(), 0)
        self.assertEqual(self.store.count_feedback(status='revoked'), 1)
        self.assertEqual(len(self.store.list_feedback(status='all')), 1)
        self.now = 3000
        retried = self.store.submit_feedback('event-1', 601, {'label': 'updated while revoked'})
        self.assertTrue(retried['is_revoked'])
        self.assertEqual(retried['created_at'], first['created_at'])
        self.assertEqual(retried['revoked_at'], 2000)
        self.assertEqual(self.store.count_feedback(), 0)
        self.assertEqual(self.store.get_feedback('event-1', 601, status='revoked')['payload'],
                         {'label': 'updated while revoked'})

    def test_explicit_restore_and_repeated_lifecycle_operations_are_auditable(self):
        self.submit()
        self.store.revoke_feedback('event-1', 601, reason='mistake')
        self.store.revoke_feedback('event-1', 601, reason='duplicate request')
        self.now = 2000
        restored = self.store.restore_feedback('event-1', 601)
        self.store.restore_feedback('event-1', 601)
        self.assertFalse(restored['is_revoked'])
        self.assertEqual(restored['created_at'], 1000)
        self.assertEqual(self.store.count_feedback(), 1)
        rows = self.store.feedback_audit('event-1', 601, status='all')
        self.assertEqual([r['operation'] for r in rows], ['submit', 'revoke', 'restore'])
        self.assertEqual(rows[1]['snapshot']['revocation_reason'], 'mistake')
        self.assertEqual(self.store.feedback_audit('event-1', 601, status='revoked'), [])
        with self.assertRaises(TypeError):
            self.store.feedback_audit('event-1', 601)

    def test_four_scopes_isolate_every_feedback_and_sample_operation(self):
        stores = [LocalCareStore(self.path, person, model, clock=lambda: self.now)
                  for person in ('person-a', 'person-b') for model in ('model-v1', 'model-v2')]
        for n, store in enumerate(stores):
            store.submit_feedback('same-target', 601, {'scope': n})
            store.put_sample('same-sample', 'posture', {'scope': n}, sampled_at=601)
        stores[0].revoke_feedback('same-target', 601)
        for n, store in enumerate(stores):
            self.assertEqual(store.count_feedback(), 0 if n == 0 else 1)
            self.assertEqual(store.get_feedback('same-target', 601, status='all')['payload'], {'scope': n})
            self.assertEqual(store.get_sample('same-sample')['payload'], {'scope': n})
            self.assertEqual(len(store.list_samples(category='posture')), 1)
            self.assertEqual(len(store.feedback_audit('same-target', 601, status='all')), 2 if n == 0 else 1)
        stores[0].restore_feedback('same-target', 601)
        stores[0].submit_feedback('same-target', 601, {'scope': 'updated'})
        stores[0].put_sample('same-sample', 'activity', {'scope': 'updated'}, sampled_at=602)
        self.assertEqual(stores[1].get_feedback('same-target', 601)['payload'], {'scope': 1})
        self.assertEqual(stores[1].get_sample('same-sample')['category'], 'posture')

    def test_out_of_scope_ids_cannot_be_read_or_mutated(self):
        self.submit()
        self.store.put_sample('sample-1', 'posture', {}, sampled_at=601)
        other = LocalCareStore(self.path, 'person-b', 'model-v2')
        self.assertIsNone(other.get_feedback('event-1', 601, status='all'))
        self.assertEqual(other.feedback_audit('event-1', 601, status='all'), [])
        self.assertIsNone(other.get_sample('sample-1'))
        for action in (other.revoke_feedback, other.restore_feedback):
            with self.assertRaises(LookupError):
                action('event-1', 601)
        self.assertFalse(self.store.get_feedback('event-1', 601)['is_revoked'])

    def test_samples_filter_category_and_upsert_without_resetting_created_at(self):
        for category in ('posture', 'activity', 'routine'):
            self.store.put_sample(category, category, {'value': 1}, sampled_at=601)
        self.now = 2000
        changed = self.store.put_sample('posture', 'activity', {'value': 2}, sampled_at=602, source='manual')
        self.assertEqual(changed['created_at'], 1000)
        self.assertEqual(changed['updated_at'], 2000)
        self.assertEqual(changed['sampled_at'], 602)
        self.assertEqual(changed['source'], 'manual')
        self.assertEqual(len(self.store.list_samples()), 3)
        self.assertEqual(self.store.list_samples(category='posture'), [])
        self.assertEqual(len(self.store.list_samples(category='activity')), 2)

    def test_bad_category_and_payload_are_atomic(self):
        self.submit()
        for category in ('unknown', '', None):
            with self.assertRaises(ValueError):
                self.store.put_sample('x', category, {}, sampled_at=601)
            with self.assertRaises(ValueError):
                self.store.list_samples(category=category if category is not None else 'None')
        for payload in ([], {'bad': float('nan')}, {'bad': object()}, {'large': 'a' * 70000}):
            with self.assertRaises(ValueError):
                self.store.submit_feedback('event-1', 601, payload)
        self.assertEqual(self.store.get_feedback('event-1', 601)['revision'], 1)
        self.assertEqual(self.store.list_samples(), [])

    def test_invalid_scope_status_and_event_time_are_rejected(self):
        for value in ('', ' ', ' person', 'p\x00', None):
            with self.assertRaises(ValueError):
                LocalCareStore(self.path, value, 'v1')
            with self.assertRaises(ValueError):
                LocalCareStore(self.path, 'person-a', value)
        for event_at in (-1, float('nan'), float('inf'), True):
            with self.assertRaises(ValueError):
                self.store.submit_feedback('x', event_at, {})
        for status in ('unknown', '', None):
            with self.assertRaises(ValueError):
                self.store.list_feedback(status=status)
        self.assertEqual(self.store.count_feedback(status='all'), 0)

    def test_clock_rollback_preserves_updated_time_revision_orders_changes(self):
        self.submit()
        self.now = 900
        updated = self.submit()
        self.assertEqual(updated['created_at'], 1000)
        self.assertEqual(updated['updated_at'], 1000)
        self.assertEqual(updated['revision'], 2)

    def test_audit_failure_rolls_back_feedback_write(self):
        self.submit()
        with raw_db(self.path) as db:
            db.execute("CREATE TRIGGER reject_audit BEFORE INSERT ON feedback_audit BEGIN SELECT RAISE(ABORT,'audit unavailable'); END")
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.submit_feedback('event-1', 601, {'changed': True})
        self.assertEqual(self.store.get_feedback('event-1', 601)['revision'], 1)
        self.assertEqual(self.store.get_feedback('event-1', 601)['payload'], {'label': 'normal'})
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.revoke_feedback('event-1', 601)
        self.assertFalse(self.store.get_feedback('event-1', 601)['is_revoked'])

    def test_concurrent_instances_keep_one_feedback_and_all_revisions(self):
        def submit(_):
            store = LocalCareStore(self.path, 'person-a', 'model-v1', clock=lambda: 2000)
            store.submit_feedback('concurrent', 601, {'valid': True})
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(submit, range(24)))
        self.assertEqual(self.store.count_feedback(), 1)
        self.assertEqual(self.store.get_feedback('concurrent', 601)['revision'], 24)
        self.assertEqual(len(self.store.feedback_audit('concurrent', 601, status='all')), 24)

    def test_restart_and_no_socket_available(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')), \
                patch.object(socket, 'create_connection', side_effect=AssertionError('network forbidden')):
            self.submit()
            self.store.put_sample('offline', 'routine', {'value': 2}, sampled_at=601)
            reopened = LocalCareStore(self.path, 'person-a', 'model-v1')
            self.assertEqual(reopened.count_feedback(), 1)
            reopened.revoke_feedback('event-1', 601)
            self.assertEqual(reopened.list_feedback(), [])
            self.assertEqual(len(reopened.list_feedback(status='revoked')), 1)
            reopened.restore_feedback('event-1', 601)
            self.assertEqual(reopened.get_sample('offline')['payload'], {'value': 2})

    def test_every_table_pk_and_index_include_both_scope_fields(self):
        with raw_db(self.path) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            self.assertEqual(set(tables), {'feedback', 'feedback_audit', 'baseline_samples',
                                          'care_events', 'care_sessions', 'care_outbox'})
            for table in tables:
                columns = db.execute(f'PRAGMA table_info({table})').fetchall()
                self.assertTrue({'person_id', 'model_version'} <= {r[1] for r in columns if r[5]})
                for index in db.execute(f'PRAGMA index_list({table})').fetchall():
                    names = {r[2] for r in db.execute(f'PRAGMA index_info({index[1]})')}
                    self.assertTrue({'person_id', 'model_version'} <= names)

    def test_database_category_constraint_rejects_raw_invalid_write(self):
        self.store.put_sample('valid', 'posture', {}, sampled_at=601)
        with raw_db(self.path) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE baseline_samples SET category='invalid' WHERE person_id=? AND model_version=?",
                           ('person-a', 'model-v1'))
        self.assertEqual(self.store.get_sample('valid')['category'], 'posture')

    def test_scoped_target_filter_and_independent_returned_payload(self):
        self.submit()
        self.store.submit_feedback('other-event', 601, {'label': 'other'})
        selected = self.store.list_feedback(target_id='event-1')
        self.assertEqual(len(selected), 1)
        selected[0]['payload']['label'] = 'changed only in memory'
        self.assertEqual(self.store.get_feedback('event-1', 601)['payload'], {'label': 'normal'})


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'care.db'

    def test_v1_upgrade_preserves_rows_creates_consistent_backup_and_is_idempotent(self):
        migrate_database(self.path, target_version=1)
        with raw_db(self.path) as db:
            db.execute("INSERT INTO baseline_samples VALUES ('person-a','v1','s1','posture','{}',601,1000,1000)")
            before = db.execute('SELECT * FROM baseline_samples').fetchall()
        result = migrate_database(self.path)
        with raw_db(self.path) as db:
            row = db.execute('SELECT * FROM baseline_samples').fetchone()
            self.assertEqual(row[:-1], before[0])
            self.assertIsNone(row[-1])
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], LATEST_VERSION)
        with raw_db(result['backup_path']) as backup:
            self.assertEqual(backup.execute('SELECT * FROM baseline_samples').fetchall(), before)
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 1)
        self.assertIsNone(migrate_database(self.path)['backup_path'])

    def test_failed_migration_rolls_back_ddl_and_version(self):
        import src.local_care_migrations as migrations
        migrate_database(self.path, target_version=1)
        bad = Path(self.temp.name) / 'broken.sql'
        bad.write_text('ALTER TABLE baseline_samples ADD COLUMN extra TEXT; INVALID SQL;', encoding='utf-8')
        with patch.object(migrations, 'MIGRATIONS', {**migrations.MIGRATIONS, 2: bad}):
            with self.assertRaises(sqlite3.OperationalError):
                migrate_database(self.path)
        with raw_db(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertNotIn('extra', [r[1] for r in db.execute('PRAGMA table_info(baseline_samples)')])

    def test_unknown_future_and_downgrade_refused_without_changing_data(self):
        with raw_db(self.path) as db:
            db.execute('CREATE TABLE private_data (value TEXT)')
            db.execute("INSERT INTO private_data VALUES ('keep')")
        with self.assertRaises(ValueError):
            migrate_database(self.path)
        with raw_db(self.path) as db:
            self.assertEqual(db.execute('SELECT * FROM private_data').fetchall(), [('keep',)])
        other = Path(self.temp.name) / 'other.db'
        migrate_database(other)
        with self.assertRaises(ValueError):
            migrate_database(other, target_version=1)
        with raw_db(other) as db:
            db.execute('PRAGMA user_version=99')
        with self.assertRaises(ValueError):
            migrate_database(other)

    def test_wal_backup_includes_uncheckpointed_committed_rows(self):
        migrate_database(self.path, target_version=1)
        with raw_db(self.path) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute("INSERT INTO baseline_samples VALUES ('person-a','v1','s1','routine','{}',601,1000,1000)")
            db.commit()
            result = migrate_database(self.path)
            with raw_db(result['backup_path']) as backup:
                self.assertEqual(backup.execute('SELECT sample_id FROM baseline_samples').fetchall(), [('s1',)])
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 1)

    def test_backup_failure_prevents_upgrade(self):
        import src.local_care_migrations as migrations
        migrate_database(self.path, target_version=1)
        with patch.object(migrations, '_backup', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                migrate_database(self.path)
        with raw_db(self.path) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 1)

    def test_cli_migrates_and_reports_errors_without_success_exit(self):
        from tools.migrate_local_care import main
        with redirect_stdout(io.StringIO()) as output:
            code = main([str(self.path), '--target-version', '1'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue()),
                         {'from_version': 0, 'to_version': 1, 'backup_file': None})
        with redirect_stdout(io.StringIO()) as output:
            code = main([str(self.path)])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())['backup_file'].endswith('.backup.db'))
        with redirect_stderr(io.StringIO()) as error:
            self.assertEqual(main([str(self.path), '--target-version', '1']), 1)
        self.assertIn('downgrade', error.getvalue())

    def test_version_change_before_writer_lock_still_gets_backup(self):
        import src.local_care_migrations as migrations
        original_connect = sqlite3.connect
        injected = False
        path = self.path

        class InterleavedConnection(sqlite3.Connection):
            def execute(self, sql, parameters=()):
                nonlocal injected
                if sql == 'BEGIN IMMEDIATE' and not injected:
                    injected = True
                    # Deterministically simulate another process winning the
                    # writer lock, creating v1 and adding data before this writer.
                    migrate_database(path, target_version=1)
                    with raw_db(path) as other:
                        other.execute("INSERT INTO baseline_samples VALUES ('person-a','v1','s1','posture','{}',601,1000,1000)")
                return super().execute(sql, parameters)

        def connect(*args, **kwargs):
            kwargs.setdefault('factory', InterleavedConnection)
            return original_connect(*args, **kwargs)

        with patch.object(migrations.sqlite3, 'connect', side_effect=connect):
            result = migrate_database(self.path)
        self.assertEqual(result['from_version'], 1)
        self.assertIsNotNone(result['backup_path'])
        with raw_db(result['backup_path']) as backup:
            self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(backup.execute('SELECT sample_id FROM baseline_samples').fetchall(), [('s1',)])

    def test_missing_required_index_and_unscoped_extra_index_are_rejected(self):
        migrate_database(self.path)
        with raw_db(self.path) as db:
            db.execute('DROP INDEX feedback_scope_status_time')
        with self.assertRaises(ValueError):
            migrate_database(self.path)
        with raw_db(self.path) as db:
            db.execute('CREATE INDEX feedback_scope_status_time ON feedback(person_id,model_version,is_revoked,updated_at,target_id,window_start)')
            db.execute('CREATE UNIQUE INDEX wrong_scope ON baseline_samples(sample_id)')
        with self.assertRaises(ValueError):
            migrate_database(self.path)

    def test_fresh_database_initialization_is_concurrent_safe(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: migrate_database(self.path), range(16)))
        self.assertEqual({r['to_version'] for r in results}, {LATEST_VERSION})
        self.assertEqual(sum(r['from_version'] == 0 for r in results), 1)

    def test_schema_without_scoped_audit_foreign_key_is_rejected(self):
        import src.local_care_migrations as migrations
        broken = Path(self.temp.name) / 'unscoped.sql'
        script = migrations.MIGRATIONS[1].read_text(encoding='utf-8')
        script = re.sub(r',\s*FOREIGN KEY \(person_id, model_version, target_id, window_start\)\s*'
                        r'REFERENCES feedback\(person_id, model_version, target_id, window_start\)', '', script)
        broken.write_text(script, encoding='utf-8')
        with patch.object(migrations, 'MIGRATIONS', {**migrations.MIGRATIONS, 1: broken}):
            with self.assertRaises(ValueError):
                migrate_database(self.path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
