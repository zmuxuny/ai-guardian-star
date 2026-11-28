"""Synthetic isolated child-process recovery checks; never restarts production."""
import json
import subprocess
import sys
import time

from src.personalization_v5 import Store, iso
from tools.personalization_v5_text import Server


def run_recovery(root):
    root.mkdir()
    peer=Store(root/'peer.sqlite','recovery-synthetic','peer')
    now=time.time()
    payload=dict(schema_version='2',event_id='help-restart',alert_type='late_wakeup',
                 timestamp=iso(now),expires_at=iso(now+120),reason='合成恢复验证')
    peer.register_reminder(payload)
    common="""
import json,sys
from src.personalization_v5 import Store
from src.personalization_v5_session import Session
from tools.local_care_text_v3 import classify_reply
from tools.personalization_v5_text import flush_outbox
store=Store(sys.argv[1],'recovery-synthetic','model')
session=Session(store,lambda text,timeout:classify_reply(text,lambda _: {'intent':'unclear'}))
"""
    def child(body,path,*args):
        run=subprocess.run([sys.executable,'-c',common+body,str(path),*args],
                           text=True,capture_output=True,timeout=20,check=True)
        return json.loads(run.stdout.splitlines()[-1])
    first=child("""
session.accept(json.loads(sys.argv[2]))
action=session.tick('help-restart');print(json.dumps(action));session.displayed('help-restart')
result=session.answer('help-restart','我现在起不来，帮帮我。')
flush_outbox(store,'http://127.0.0.1:1')
print(json.dumps({'result':result,'event':store.event('help-restart')}))
""",root/'help.sqlite',json.dumps(payload))
    time.sleep(5.2)
    receiver=Server(peer);receiver.start()
    try:
        second=child("""
session.recover()
before=store.pending()
flush_outbox(store,sys.argv[2])
print(json.dumps({'before':before,'after':store.pending(),'result':store.event('help-restart')['latest']}))
""",root/'help.sqlite',receiver.url)
        assert second['result']==first['result']==peer.event('help-restart')['latest']
        assert second['before'][0]['attempts']==1 and not second['after']
        assert len(peer.help_tasks())==1
    finally:receiver.close()
    crashes=[]
    for stage in ('marked_before_display','displayed_before_result'):
        event={**payload,'event_id':stage}
        child("""
session.accept(json.loads(sys.argv[2]));action=session.tick(sys.argv[3])
if sys.argv[3]=='displayed_before_result':
 print(json.dumps(action));session.displayed(sys.argv[3])
print(json.dumps({'phase':store.event(sys.argv[3])['state']['phase']}))
""",root/(stage+'.sqlite'),json.dumps(event),stage)
        recovered=child("""
session.recover()
print(json.dumps(store.event(sys.argv[2])))
""",root/(stage+'.sqlite'),stage)
        assert recovered['latest']['error_code']=='interrupted'
        assert recovered['state']['prompt_count']==1 and recovered['latest']['revision']==1
        crashes.append({'stage':stage,'result':recovered['latest'],'prompt_count':1})
    return {'synthetic':True,'process_restart':'actual independent Python child exits/reopens; not power loss',
            'classification':'V3 explicit-help rule; no inference in recovery checks',
            'help_payload_unchanged':True,'help_result':second['result'],'help_tasks':len(peer.help_tasks()),
            'disconnected_attempts_before_restart':second['before'][0]['attempts'],'crash_points':crashes}
