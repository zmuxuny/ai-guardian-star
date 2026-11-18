"""AF-01: real durable runtime with a restarted stationary proxy, no devices."""
from datetime import datetime, timezone
from pathlib import Path
import tempfile
import unittest

from src.care_runtime import CareRuntime, RuntimeConfig
from src.guardian_runtime import StationaryTimer
from src.sedentary_care import Config, VirtualClock


class RestartInputTests(unittest.TestCase):
    def test_demo_tolerates_small_jitter_and_reminds_at_four_seconds_then_clears_on_motion(self):
        from dataclasses import replace
        demo=CareRuntime(replace(self.config,db_path=Path(self.temp.name)/'demo.db',
            machine=Config(l0_seconds=2,upgrade_seconds=3,repeat_seconds=5,quiet_start=None,quiet_end=None)),clock=self.clock)
        self.addCleanup(demo.close)
        timer=StationaryTimer()
        for second in range(13):
            if second:self.clock.advance(1)
            shift=second%3
            timer.update([shift,0,100+shift,200],self.clock.now)
            demo.on_detection([dict(id=1,care_person_id='p1',is_sitting=timer.duration(self.clock.now)>=2,
                care_observation=timer.care_observation(self.clock.now,2))],{})
            if second==3:self.assertEqual(demo.state('p1')['counts']['L0'],0)
            if second==4:self.assertEqual(demo.state('p1')['counts']['L0'],1)
            if second==7:self.assertEqual(demo.state('p1')['counts']['L1'],1)
        self.assertEqual(demo.state('p1')['counts'],{'L0':1,'L1':2})
        self.assertEqual(demo.events('p2'),[])
        self.clock.advance(1);timer.update([80,0,180,200],self.clock.now)
        demo.on_detection([dict(id=1,care_person_id='p1',is_sitting=False,
            care_observation=timer.care_observation(self.clock.now,2))],{})
        self.assertEqual(demo.state('p1')['seated_seconds'],0)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=VirtualClock(datetime(2026,11,17,12,tzinfo=timezone.utc))
        self.config=RuntimeConfig(Path(self.temp.name)/'care.db',('p1','p2'),'restart-test',
            machine=Config(l0_seconds=15,upgrade_seconds=10,repeat_seconds=10,quiet_start=None,quiet_end=None))
        self.runtime=CareRuntime(self.config,clock=self.clock)
        self.addCleanup(lambda:self.runtime.close())

    def frame(self, sitting=True, observation='still', person='p1'):
        return self.runtime.on_detection([dict(id=1,care_person_id=person,is_sitting=sitting,
            care_observation=observation)],{})

    def exhausted(self):
        self.frame()
        for _ in range(7):self.clock.advance(5);self.frame()
        self.assertEqual(self.runtime.state('p1')['counts'],{'L0':1,'L1':2})
        return self.runtime.events('p1')[0]['event_id']

    def restart(self, seconds):
        self.runtime.close();self.clock.advance(seconds)
        self.clock=VirtualClock(self.clock.wall_at(self.clock.now))
        self.runtime=CareRuntime(self.config,clock=self.clock)

    def test_short_restart_warmup_preserves_exhausted_event_and_does_not_repeat_l0(self):
        identity=self.exhausted();self.restart(5)
        for _ in range(10):
            self.frame(False,'warming');self.clock.advance(1)
        self.assertEqual(self.runtime.state('p1')['seated_seconds'],35)
        self.frame()
        self.assertEqual([e['event_id'] for e in self.runtime.events('p1')],[identity])
        self.assertEqual(self.runtime.state('p1')['counts'],{'L0':1,'L1':2})
        self.assertEqual(self.runtime.shadow_broadcasts(),[])
        self.assertEqual(self.runtime.pending('p1'),[])
        self.assertEqual(self.runtime.events('p2'),[])

    def test_actual_motion_during_recovery_still_resets_immediately(self):
        identity=self.exhausted();self.restart(5)
        self.frame(False,'warming');self.frame(False,'moving')
        self.assertEqual(self.runtime.state('p1')['phase'],'IDLE')
        self.assertEqual(self.runtime.state('p1')['seated_seconds'],0)
        self.frame()
        self.assertNotEqual(self.runtime.events('p1')[-1]['event_id'],identity)

    def test_unreliable_and_missing_identity_never_extend_the_120_second_deadline(self):
        self.exhausted();self.restart(5)
        for _ in range(23):
            self.frame(False,'unreliable');self.clock.advance(5)
        self.runtime.on_detection([],{})
        self.assertEqual(self.runtime.state('p1')['phase'],'IDLE')
        self.assertEqual(self.runtime.state('p1')['counts'],{'L0':0,'L1':0})

    def test_long_restart_requires_a_new_round_even_with_warmup_metadata(self):
        identity=self.exhausted();self.restart(130)
        self.frame(False,'warming');self.clock.advance(10);self.frame()
        self.assertNotEqual(self.runtime.events('p1')[-1]['event_id'],identity)

    def test_timer_distinguishes_warmup_from_motion_without_changing_duration(self):
        timer=StationaryTimer();box=[0,0,100,200]
        timer.update(box,100)
        self.assertEqual(timer.care_observation(100,10),'warming')
        for t in range(101,111):timer.update(box,t)
        self.assertEqual(timer.duration(110),10)
        self.assertEqual(timer.care_observation(110,10),'still')
        timer.update([80,0,180,200],111)
        self.assertEqual(timer.care_observation(111,10),'moving')
        timer.update([80,0,180,200],112)
        self.assertEqual(timer.care_observation(112,10),'warming')
        timer.update(box,120)  # unobserved gap is not evidence of movement
        self.assertEqual(timer.care_observation(120,10),'unreliable')
        self.assertEqual(timer.care_observation(125,10),'unreliable')
