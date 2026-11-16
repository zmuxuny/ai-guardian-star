"""Bind private local face labels to immutable IDs; preserve legacy alerts."""
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import tempfile
import unittest
from src.care_runtime import CareRuntime,RuntimeConfig
from src.sedentary_care import VirtualClock, Config

class IdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.clock=VirtualClock(datetime(2026,11,16,12,tzinfo=timezone.utc))
    def config(self,aliases):
        return RuntimeConfig(Path(self.temp.name)/'care.db',('uid-a','uid-b'),'model',face_label_ids=aliases)
    def test_registered_label_maps_to_original_id_and_keeps_input_unchanged(self):
        runtime=CareRuntime(self.config({'display-a':'uid-a'}),clock=self.clock);self.addCleanup(runtime.close)
        alerts=[dict(id=7,face_label='known:display-a',is_sitting=True)]
        original=deepcopy(alerts)
        runtime.on_detection(alerts,{'sit':alerts})
        self.assertEqual(runtime.state('uid-a')['state'],'SITTING')
        self.assertEqual(runtime.state('uid-b')['state'],'IDLE')
        self.assertEqual(runtime.events('uid-a')[0]['person_id'],'uid-a')
        self.assertEqual(runtime.events('uid-b'),[])
        self.assertEqual(alerts,original)
    def test_alias_configuration_is_validated_and_copied(self):
        aliases={'display-a':'uid-a'};config=self.config(aliases);aliases['display-a']='uid-b'
        self.assertEqual(config.face_label_ids['display-a'],'uid-a')
        with self.assertRaises(TypeError): config.face_label_ids['display-a']='uid-b'
        for aliases in ({'display-a':'foreign-id'},{'uid-b':'uid-a'},{'':'uid-a'},[]):
            with self.assertRaises(ValueError): self.config(aliases)
    def test_unmapped_renamed_label_does_not_bind_or_reuse_tracker_id(self):
        runtime=CareRuntime(self.config({'display-a':'uid-a'}),clock=self.clock);self.addCleanup(runtime.close)
        runtime.on_detection([dict(id='uid-a',face_label='known:renamed',is_sitting=True)],{})
        self.assertEqual(runtime.events('uid-a'),[])
        runtime.on_detection([dict(id=7,care_person_id='uid-a',face_label='known:renamed',is_sitting=True)],{})
        self.assertEqual(runtime.events('uid-a')[0]['person_id'],'uid-a')
    def test_shadow_broadcasts_are_exact_detached_and_do_not_enqueue_live(self):
        config=RuntimeConfig(Path(self.temp.name)/'care.db',('uid-a',),'model',
            machine=Config(l0_seconds=1,upgrade_seconds=1,repeat_seconds=1,quiet_start=None,quiet_end=None))
        runtime=CareRuntime(config,clock=self.clock);self.addCleanup(runtime.close)
        for second in range(4):
            if second:self.clock.advance(1)
            runtime.on_detection([dict(id=1,care_person_id='uid-a',is_sitting=True)],{})
        rows=runtime.shadow_broadcasts()
        self.assertEqual([row['text_id'] for row in rows],['sedentary.l0','sedentary.l1','sedentary.l1'])
        self.assertEqual([row['at'] for row in rows],[1,2,3])
        self.assertEqual(runtime.pending('uid-a'),[])
        rows.clear();self.assertEqual(len(runtime.shadow_broadcasts()),3)
        runtime.erase_person('uid-a');self.assertEqual(runtime.shadow_broadcasts(),[])

    def test_without_aliases_original_id_contract_still_works(self):
        config=RuntimeConfig(Path(self.temp.name)/'care.db',('uid-a',),'model')
        runtime=CareRuntime(config,clock=self.clock);self.addCleanup(runtime.close)
        runtime.on_detection([dict(id=9,face_label='known:uid-a',is_sitting=True)],{})
        self.assertEqual(runtime.events('uid-a')[0]['person_id'],'uid-a')

if __name__=='__main__':unittest.main(verbosity=2)
