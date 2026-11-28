import json,threading,time,urllib.request,urllib.error
from src.personalization_v5 import Store,iso
from tools.local_care_text_v3 import SemanticIntentClient
from tools.personalization_v5_text import Server,prepared_session,post,flush_outbox


def run_demo(root,*,model_url,model_id,stop_backend,restart_backend):
    root.mkdir()
    model=Store(root/'model.sqlite','fast-v5-synthetic','model')
    peer=Store(root/'peer.sqlite','fast-v5-synthetic','peer')
    session,gate=prepared_session(model,SemanticIntentClient(model_url,model_id),policy='v4-fast')
    decisions=[];original=session.classify
    def observed(text,*,timeout):
        decision=original(text,timeout=timeout);decisions.append(decision);return decision
    session.classify=observed
    server=Server(model,session,readiness=gate);receiver=Server(peer)
    stop=threading.Event();worker=None
    def wait_ready():
        start=time.monotonic()
        while time.monotonic()-start<75:
            try:
                with urllib.request.urlopen(server.url+'/health/ready',timeout=3) as response:health=json.load(response)
                if health['ready']:return time.monotonic()-start
            except urllib.error.HTTPError as error:
                assert error.code==503;error.close()
            time.sleep(.1)
        raise TimeoutError('automatic recovery deadline')
    def accept(name):
        now=time.time();payload=dict(schema_version='2',event_id=name,alert_type='late_wakeup',timestamp=iso(now),expires_at=iso(now+120),reason='合成自动恢复验证')
        peer.register_reminder(payload);flush_outbox(peer,server.url)
        action=session.tick(name,prompt_available=gate.ready);assert action['kind']=='prompt'
        print(json.dumps(action,ensure_ascii=False),flush=True);session.displayed(name)
    try:
        server.start();receiver.start()
        now=time.time();blocked=dict(schema_version='2',event_id='cold-rejected',alert_type='late_wakeup',timestamp=iso(now),expires_at=iso(now+120),reason='合成冷门禁')
        assert post(server.url+'/personalization/v2/reminders',blocked)[0]==503
        assert model.events()==[]
        worker=threading.Thread(target=gate.run,args=(stop,),daemon=True);worker.start()
        initial_wait=wait_ready();before=gate.snapshot();service_identity=id(session);gate_identity=id(gate)
        cases=[]
        for name,text,expected in (
            ('rule_ok','我现在没事，谢谢关心。','ok'),
            ('denial','我没有说我需要帮助。','unclear'),
            ('mixed_help','我没说我需要帮助，但我现在起不来。','needs_help'),
            ('weak_help','我没有表示不舒服，但我想找人来看看我。','needs_help')):
            accept(name);first=len(decisions);start=time.monotonic();count_before=gate.snapshot()['classification_calls']
            code,value=post(server.url+'/text/v1/answers',dict(event_id=name,text=text),timeout=7)
            prompts=1
            if name=='denial':
                assert code==202
                action=session.tick(name,prompt_available=gate.ready);assert action['attempt']==2
                print(json.dumps(action,ensure_ascii=False),flush=True);session.displayed(name);prompts=2
                code,value=post(server.url+'/text/v1/answers',dict(event_id=name,text=text),timeout=7)
                assert gate.snapshot()['classification_calls']==count_before
            elapsed=time.monotonic()-start
            assert code==200 and value['response']==expected,(name,code,value)
            flush_outbox(model,receiver.url);assert peer.event(name)['latest']==value
            assert post(receiver.url+'/personalization/v2/results',value)[1]['disposition']=='duplicate'
            cases.append({'event_id':name,'text':text,'result':value,'prompts':prompts,
                          'wall_seconds':elapsed,'policy_decisions':decisions[first:],
                          'classification_attempts':gate.snapshot()['classification_calls']-count_before})
        accept('outage')
        stop_backend()
        code,_=post(server.url+'/text/v1/answers',dict(event_id='outage',text='我想找人来看看我。'),timeout=7)
        assert code==202 and not gate.ready
        now=time.time();blocked=dict(schema_version='2',event_id='outage-rejected',alert_type='late_wakeup',timestamp=iso(now),expires_at=iso(now+120),reason='合成故障门禁')
        assert post(server.url+'/personalization/v2/reminders',blocked)[0]==503
        assert not any(e['event_id']==blocked['event_id'] for e in model.events())
        code,help_result=post(server.url+'/text/v1/answers',dict(event_id='outage',text='我现在起不来，帮帮我。'),timeout=7)
        assert code==200 and help_result['response']=='needs_help'
        restart_backend()
        recovery_wait=wait_ready();after=gate.snapshot()
        assert id(session)==service_identity and id(gate)==gate_identity
        assert after['warm_calls']>before['warm_calls'] and after['probe_calls']>before['probe_calls']
        accept('after_auto_recovery');first=len(decisions);start=time.monotonic()
        code,result=post(server.url+'/text/v1/answers',dict(event_id='after_auto_recovery',text='我想找人来看看我。'),timeout=7)
        elapsed=time.monotonic()-start
        assert code==200 and result['response']=='needs_help'
        flush_outbox(model,receiver.url)
        assert peer.event('outage')['latest']==help_result and peer.event('after_auto_recovery')['latest']==result
        assert len(peer.help_tasks())==4
        assert not model.pending() and not peer.pending()
        stop.set();worker.join(timeout=3)
        final=gate.snapshot()
        output={'synthetic':True,'mode':'fast_v5_same_service_automatic_model_recovery','policy':'v4-fast','cold_new_reminder_http':503,'outage_new_reminder_http':503,'initial_wait_seconds':initial_wait,
                'recovery_wait_seconds':recovery_wait,'before':before,'after':after,'final_counters':final,
                'same_session_and_gate':True,'help_preserved':help_result,'help_tasks':len(peer.help_tasks()),
                'backend_attempts':sum(final[k] for k in ('warm_calls','probe_calls','classification_calls')),
                'cases':cases+[{'event_id':'after_auto_recovery','text':'我想找人来看看我。','result':result,
                          'prompts':1,'wall_seconds':elapsed,'policy_decisions':decisions[first:]}]}
        (root/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
        return output
    finally:
        stop.set()
        if worker:worker.join(timeout=1)
        server.close();receiver.close()
