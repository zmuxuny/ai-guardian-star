"""Offline weekly-report acceptance; fixed UTC timestamps, no waiting."""
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone
from src.weekly_store import WeeklyStore


def ts(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


class WeeklyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = ts('2026-11-16T00:00:00')
        self.path = Path(self.tmp.name) / 'care.db'
        self.store = WeeklyStore(self.path, 'p', 'v1', clock=lambda: self.now)

    def event(self, identity, at, store=None):
        (store or self.store).create_event(dict(event_id=identity, mode='shadow', kind='fall',
            region_id='room', started_at=at, ended_at=at))

    def observation(self, identity, start, end, **kw):
        self.store.observe('shadow', identity, 'room', start, end, **kw)

    def report(self, **kw):
        return self.store.weekly('shadow', '2026-11-09', regions=('room',), offset_minutes=0, **kw)

    def row(self, result, period='night'):
        return next(r for r in result['groups'] if r['region_id']=='room' and
                    r['period_id']==period and r['event_type']=='fall')

    def test_cross_week_duplicate_and_threshold(self):
        edge = ts('2026-11-09T00:00:00')
        self.event('old', edge-1)
        self.event('new', edge)
        self.event('new', edge)
        self.observation('cross', edge-60, edge+60, quality=.8)
        self.observation('duplicate', edge-60, edge+60, quality=.8)
        row = self.row(self.report(min_samples=1))
        self.assertEqual(row['current']['event_count'], 1)
        self.assertEqual(row['current']['effective_observation_seconds'], 60)
        self.assertEqual(row['current']['sample_count'], 1)
        self.assertEqual(row['current']['perception_quality']['score'], .8)
        self.assertIsNone(row['trend'])  # previous event is in evening, not night

    def test_feedback_revoke(self):
        at = ts('2026-11-09T01:00:00')
        self.event('one', at)
        self.store.event_feedback('one', 'shadow', {'confirmed': True})
        self.assertEqual(self.row(self.report())['current']['human_confirmed_count'], 1)
        self.store.event_feedback('one', 'shadow', operation='revoke')
        row = self.row(self.report())
        self.assertEqual(row['current']['human_confirmed_count'], 0)
        self.assertEqual(row['current']['event_count'], 1)

    def test_duplicate_events(self):
        at=ts('2026-11-09T00:00:00')
        for _ in range(5):
            self.event('one',at)
        self.assertEqual(self.row(self.report())['current']['event_count'],1)

    def test_timezone(self):
        self.event('edge', ts('2026-11-08T17:00:00'))
        result = self.store.weekly('shadow', '2026-11-09', regions=('room',), offset_minutes=480)
        self.assertEqual(self.row(result)['current']['event_count'], 1)
        self.assertEqual(self.row(self.report())['current']['event_count'], 0)

    def test_missing_and_observed_zero_and_trend(self):
        row = self.row(self.report())
        self.assertEqual(row['current']['observation_status'], 'no_observations')
        self.assertIsNone(row['current']['event_rate_per_hour'])
        self.observation('current', ts('2026-11-09T00:00:00'), ts('2026-11-09T00:01:00'))
        self.assertEqual(self.row(self.report())['current']['event_rate_per_hour'], 0)
        self.assertIsNone(self.row(self.report())['trend'])
        self.observation('previous', ts('2026-11-02T00:00:00'), ts('2026-11-02T00:01:00'))
        self.assertEqual(self.row(self.report(min_samples=1))['trend']['direction'], 'flat')

    def test_v3_migration_preserves_history_and_backup(self):
        from src.local_care_migrations import migrate_database,connection
        path=Path(self.tmp.name)/'v3.db'
        migrate_database(path,target_version=3)
        with connection(path) as db:
            db.execute("INSERT INTO care_events VALUES ('p','v1','original','shadow','fall','room',1000,1001)")
            before=tuple(db.execute('SELECT * FROM care_events').fetchone())
        result=migrate_database(path)
        self.assertEqual(result['to_version'],4)
        with connection(path) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM care_events').fetchone()),before)
        with connection(result['backup_path']) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],3)
            self.assertEqual(tuple(db.execute('SELECT * FROM care_events').fetchone()),before)

    def test_cleanup_is_mode_scoped_and_preserves_active_event(self):
        from src.local_care_migrations import connection
        at=ts('2026-11-09T00:00:00')
        self.event('old',at)
        self.store.create_event(dict(event_id='live',mode='live',kind='fall',region_id='room',started_at=at,ended_at=at))
        self.store.save_step('shadow',{},'old')
        self.observation('cross',self.now-86400-30,self.now-86400+30)
        self.store.set_policy('shadow',retention_days=1,min_samples=30)
        self.store.maintain('shadow')
        self.assertEqual(len(self.store.events('shadow')),1)
        self.assertEqual(len(self.store.events('live')),1)
        with connection(self.path) as db:
            row=db.execute("SELECT * FROM weekly_observations WHERE person_id='p' AND model_version='v1'").fetchone()
            self.assertEqual(row['started_at'],self.now-86400)
        self.assertEqual(self.store.maintain('shadow')['status'],'clock_or_interval_skip')
        self.now-=7200
        self.assertEqual(self.store.maintain('shadow')['status'],'clock_or_interval_skip')

    def test_expiry_and_personal_delete(self):
        self.event('old', ts('2026-11-09T01:00:00'))
        self.store.event_feedback('old', 'shadow', {'confirmed':True})
        self.observation('old', ts('2026-11-09T01:00:00'), ts('2026-11-09T01:01:00'))
        other = WeeklyStore(self.path, 'other', 'v1', clock=lambda:self.now)
        self.event('old', ts('2026-11-09T01:00:00'), other)
        self.store.set_policy('shadow', retention_days=1, min_samples=30)
        self.store.maintain('shadow')
        self.assertEqual(self.store.events('shadow'), [])
        self.assertEqual(self.store.feedback_for_mode('shadow', 'all'), [])
        self.assertEqual(len(other.events('shadow')), 1)
        self.assertEqual(self.row(self.report())['current']['observation_status'], 'no_observations')
        other.erase()
        self.assertTrue(other.erased())
        self.assertEqual(other.events('shadow'), [])

    def test_union_quality_and_invalid_observations(self):
        a=ts('2026-11-09T00:00:00')
        self.observation('a',a,a+60,quality=.8)
        self.observation('a',a,a+60,quality=.8)
        self.observation('b',a,a+60,quality=.4)
        self.observation('invalid',a+60,a+120,valid=False)
        row=self.row(self.report())['current']
        self.assertEqual(row['effective_observation_seconds'],60)
        self.assertEqual(row['sample_count'],1)
        self.assertAlmostEqual(row['perception_quality']['score'],.4)
        self.assertEqual(row['perception_quality']['valid_fraction'],.5)
        with self.assertRaises(ValueError):
            self.observation('a',a,a+61)

    def test_scope_version_mode_and_delete_derived(self):
        a=ts('2026-11-09T00:00:00')
        other=WeeklyStore(self.path,'p','v2',clock=lambda:self.now)
        self.event('same',a,other)
        self.event('same',a)
        self.store.create_event(dict(event_id='live',mode='live',kind='fall',region_id='room',started_at=a,ended_at=a))
        self.assertEqual(self.row(self.report())['current']['event_count'],1)
        self.store.erase()
        self.assertEqual(self.row(self.report())['current']['event_count'],0)
        self.assertEqual(len(other.events('shadow')),1)
        with self.assertRaises(ValueError):
            self.observation('blocked',a,a+60)

    def test_trend_rate_threshold_and_boundary(self):
        a=ts('2026-11-09T00:00:00')
        self.observation('new',a,a+60)
        self.observation('old',a-604800,a-604800+120)
        self.event('new',a)
        self.event('old',a-604800)
        self.assertIsNone(self.row(self.report(min_samples=2))['trend'])
        trend=self.row(self.report(min_samples=1))['trend']
        self.assertEqual(trend,dict(direction='up',rate_delta=30.0,relative_delta=1.0))
        self.observation('boundary',a+21570,a+21630)
        self.assertEqual(self.row(self.report(),'morning')['current']['effective_observation_seconds'],30)

    def test_invalid_inputs(self):
        for offset in (True,841,1):
            with self.assertRaises(ValueError):
                self.store.weekly('shadow','2026-11-09',regions=('room',),offset_minutes=offset)
        with self.assertRaises(ValueError):
            self.store.weekly('shadow','2026-11-10',regions=('room',))
        with self.assertRaises(ValueError):
            self.store.set_policy('shadow',retention_days=0,min_samples=30)


class RuntimeWeeklyTests(unittest.TestCase):
    def setUp(self):
        from src.care_runtime import CareRuntime, RuntimeConfig
        from src.sedentary_care import VirtualClock
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.clock=VirtualClock(datetime(2026,11,9,tzinfo=timezone.utc))
        self.config=RuntimeConfig(Path(self.tmp.name)/'care.db',('p',),'v1',
            weekly_enabled=True,weekly_regions=('room',),region_id='room')
        self.runtime=CareRuntime(self.config,clock=self.clock)
        self.addCleanup(lambda:self.runtime.close())

    def detect(self):
        return self.runtime.on_detection([dict(id=1,care_person_id='p',is_sitting=True,care_quality=.8)],{})

    def test_runtime_ttl_restart_delete_resume_and_automatic_cleanup(self):
        from src.care_runtime import CareRuntime
        self.detect()
        self.clock.advance(60)
        self.runtime.tick()
        report=self.runtime.weekly('p','2026-11-09',0)
        row=next(r for r in report['groups'] if r['period_id']=='night' and r['event_type']=='sit')
        self.assertEqual(row['current']['effective_observation_seconds'],30)
        self.assertIsNotNone(self.runtime.store('p').policy('shadow')['last_cleanup'])
        self.runtime.close()
        self.clock.advance(3600)
        self.runtime=CareRuntime(self.config,clock=self.clock)
        self.runtime.tick()
        self.assertEqual(self.runtime.weekly('p','2026-11-09',0)['groups'],report['groups'])
        self.runtime.erase_person('p')
        self.assertEqual(self.runtime.shadow_reports(),[])
        self.detect(); self.runtime.tick()
        self.runtime.drain_shadow()
        reports=self.runtime.shadow_reports()
        self.assertTrue(all(not r['candidate']['groups'] for r in reports if r.get('candidate')))
        self.assertEqual(self.runtime.events('p'),[])
        self.runtime.resume_person('p')
        self.detect()
        self.assertEqual(len(self.runtime.events('p')),1)

    def test_authenticated_structured_api(self):
        import json
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.care_api import create_care_router
        app=FastAPI(); app.include_router(create_care_router(self.runtime,lambda:'local-test'))
        with TestClient(app) as client:
            path='/api/care/v1/p'
            self.assertEqual(client.get(path+'/weekly?week_start=2026-11-09').status_code,401)
            client.headers['authorization']='Bearer local-test'
            response=client.get(path+'/weekly?week_start=2026-11-09')
            self.assertEqual(response.status_code,200)
            data=response.json()
            self.assertEqual(len(data['groups']),12)
            self.assertEqual(data['groups'][0]['current']['observation_status'],'no_observations')
            encoded=json.dumps(data)
            for forbidden in ('零风险','narrative','summary','no_risk'):
                self.assertNotIn(forbidden,encoded)
            self.assertEqual(client.put(path+'/weekly-policy',json=dict(retention_days=1,min_samples=3)).status_code,200)
            self.assertEqual(client.delete(path+'/data').json(),{'status':'erased'})
            self.assertEqual(client.post(path+'/data/resume').json(),{'status':'resumed'})
            self.assertEqual(client.get('/api/care/v2/p/weekly?week_start=2026-11-09').status_code,404)


if __name__ == '__main__':
    unittest.main(verbosity=2)
