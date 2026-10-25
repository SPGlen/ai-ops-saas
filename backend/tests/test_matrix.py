"""Matrix tests use fake model/channel transports; no external posting or billing."""
import io, json
from datetime import timedelta
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from PIL import Image
from app.models import *
from app.db import engine, set_scope, TENANT_TABLES
from app import matrix as m
from app.matrix_worker import execute_run
from app.worker import execute
from app.integrations import aliyun, publishing
from app.matrix_agents import TopicSelection, MatrixDraft
from app.agents import RubricScore
from .conftest import add, login
from .test_staff_social import staff, sign


def setup_matrix(client, monkeypatch, count=2):
    monkeypatch.setattr(aliyun,'config',lambda *a:('fake-key','https://dashscope.aliyuncs.com'))
    with Session(engine()) as s:
        t=s.get(Tenant,'tenant-a')
        t.settings={**t.settings,'matrix_monthly_budget_fen':100000,'quotas':{'text_tokens':5000000,'images':100,'video_seconds':1000,'speech_characters':10000,'cost_fen':100000},'publishing_enabled':True,'auto_publish':True}
        s.add(t)
        cfg=s.get(PlatformSettings,1)
        cfg.plans={**cfg.plans,'prices':{**cfg.plans['prices'],'speech_thousand_fen':100}}
        s.add(cfg);s.commit()
    knowledge=add(client,'knowledge',{'name':'公开课程资料','body':'机构提供AI入门教育，亲子探索课程，课程共八次，不承诺成绩。','approved':True})
    r=client.post('/api/v1/media-profiles',json={'name':'校园品牌','audience':'小学家长','style':'专业而温和','knowledge_ids':[knowledge['id']]})
    assert r.status_code==201,r.text
    profile=r.json()
    accounts=[]
    for i in range(count):
        a=client.post('/api/v1/social-accounts',json={'platform':'xiaohongshu','name':'校区账号'+str(i)}).json()
        r=client.patch('/api/v1/social-accounts/'+a['id']+'/matrix',json={'profile_id':profile['id'],'positioning':'校区'+str(i),'monthly_budget_fen':20000})
        assert r.status_code==200,r.text
        with Session(engine()) as s:
            obj=s.get(SocialAccount,a['id']);obj.identity_key='xiaohongshu:public:test'+str(i);obj.status='connected';obj.config={**obj.config,'verified_capabilities':{'publish_image':True}}
            s.add(obj);s.commit()
        accounts.append(a)
    spec={'direction':'用观察练习理解人工智能','account_ids':[a['id'] for a in accounts],'run_budget_fen':20000,'daily_budget_fen':50000}
    r=client.post('/api/v1/automation-plans',json={'profile_id':profile['id'],'name':'每周矩阵计划','spec':spec})
    assert r.status_code==201,r.text
    return profile,accounts,r.json(),knowledge


def fake_models(monkeypatch, knowledge_id):
    calls=[]
    def text_agent(*args,**kwargs):
        cls=args[5];data=json.loads(args[4]);calls.append((cls.__name__,data))
        if cls is TopicSelection:
            return TopicSelection(title='亲子观察练习',source_urls=[],reason='这是适合小学家长的常青教育选题。'),100
        if cls is MatrixDraft:
            name=data['account']['name'][-1]
            return MatrixDraft(title='亲子观察练习'+name,body='和孩子一起观察生活，记录疑问，比较人工智能工具的回答，并核对真实世界。'+name,cards=['观察','提出问题','比较与核对'],image_prompt='温暖的教育插画，不含文字',render_mode='program',decision_reason='本选题以清晰解释步骤为主，程序排版足以表达。',source_ids=[knowledge_id],scenes=[]),200
        if cls is RubricScore:
            return RubricScore(clarity=4,relevance=4,usefulness=4,credibility=4,narrative=4,actionability=4,accessibility=4,reasoning='最终图文清楚呈现观察步骤，课程事实有明确来源，适合目标家长。',bet='预计家长更愿意保存这份练习建议。'),100
        raise AssertionError(cls)
    monkeypatch.setattr(aliyun,'text_agent',text_agent)
    monkeypatch.setattr(aliyun,'create_image',lambda *a: (['https://fake.invalid/image.png'],'fake-image-request'))
    raw=io.BytesIO();Image.new('RGB',(100,100),'#aacb98').save(raw,format='PNG')
    monkeypatch.setattr('app.worker.download_result',lambda url:raw.getvalue())
    return calls


def drive(run_id, limit=35):
    for _ in range(limit):
        execute_run('tenant-a',run_id)
        with Session(engine()) as s:
            agents=[a.id for a in s.exec(select(AgentRun).where(AgentRun.tenant_id=='tenant-a',AgentRun.status=='queued')).all()]
            media=[a.id for a in s.exec(select(MediaJob).where(MediaJob.tenant_id=='tenant-a',MediaJob.status.in_(['queued','polling','finishing']))).all()]
        for aid in agents:execute('agent','tenant-a',aid)
        for mid in media:execute('media','tenant-a',mid)
        with Session(engine()) as s:
            r=s.get(AutomationRun,run_id)
            if r.status in ('trial_ready','succeeded'):
                return
    with Session(engine()) as s:
        tasks=s.exec(select(AutomationAccountTask).where(AutomationAccountTask.run_id==run_id)).all()
        raise AssertionError([(t.stage,t.status,t.error_code,t.error) for t in tasks])


def test_matrix_frozen_targets_dedup_and_brand_boundaries(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    g=client.post('/api/v1/account-groups',json={'name':'同品牌矩阵','profile_id':p['id'],'account_ids':[a['id'] for a in accounts]}).json()
    spec={**plan['spec'],'group_ids':[g['id']]}
    plan=client.patch('/api/v1/automation-plans/'+plan['id'],json={'name':plan['name'],'profile_id':p['id'],'version':1,'spec':spec}).json()
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'freeze-targets-01'})
    assert r.status_code==202,r.text
    frozen=r.json();assert len(frozen['tasks'])==2
    assert client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'freeze-targets-01'}).json()['id']==frozen['id']
    client.patch('/api/v1/account-groups/'+g['id'],json={'name':g['name'],'profile_id':p['id'],'account_ids':[accounts[0]['id']],'version':1})
    assert len(client.get('/api/v1/automation-runs/'+frozen['id']).json()['tasks'])==2
    other=client.post('/api/v1/media-profiles',json={'name':'另一个品牌','audience':'中学生家长'}).json()
    assert client.post('/api/v1/account-groups',json={'name':'错误归组','profile_id':other['id'],'account_ids':[accounts[0]['id']]}).status_code==400


def test_trial_full_pipeline_per_account_blind_and_shared_cost(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    calls=fake_models(monkeypatch,k['id'])
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'trial-two-accounts'})
    assert r.status_code==202,r.text
    drive(r.json()['id'])
    run=client.get('/api/v1/automation-runs/'+r.json()['id']).json()
    assert run['status']=='trial_ready'
    assert run['cost']['actual_fen'] > 0 and run['shared_cost']['actual_fen'] > 0
    assert any(step['cost']['shared'] for task in run['tasks'] for step in task['steps'])
    assert len({t['version_id'] for t in run['tasks']})==2
    assert sum(name=='TopicSelection' for name,_ in calls)==1
    assert sum(name=='MatrixDraft' for name,_ in calls)==2
    for name,payload in calls:
        if name=='RubricScore':
            assert 'metrics' not in json.dumps(payload) and 'self_media' not in payload
    with Session(engine()) as s:
        assert not s.exec(select(PublishJob)).all()
        charges=s.exec(select(MatrixCharge)).all()
        assert len([c for c in charges if not c.account_id])==1
        assert all(c.state=='settled' for c in charges)
        assert len(s.exec(select(Prediction)).all())==2
    enabled=client.post('/api/v1/automation-plans/'+plan['id']+'/enabled',json={'version':plan['version'],'enabled':True})
    assert enabled.status_code==200,enabled.text
    overview=client.get('/api/v1/matrix/overview').json()
    assert overview['shared_cost_fen']>0
    assert overview['published']==0
    assert len(client.get('/api/v1/matrix/calendar').json())>=2


def test_role_scoped_all_institution_accounts_and_revoke(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    with Session(engine()) as s:
        staff(s,'matrix-ops',['content_ops'])
        staff(s,'matrix-fin',['finance'])
    sign(client,'matrix-ops')
    assert len(client.get('/api/v1/matrix/overview').json()['accounts'])==2
    assert client.patch('/api/v1/social-accounts/'+accounts[0]['id']+'/matrix',json={'profile_id':p['id']}).status_code==403
    assert client.post('/api/v1/automation-plans/'+plan['id']+'/enabled',json={'enabled':True,'version':1}).status_code==403
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'role-revoke-queued'}).json()
    with Session(engine()) as s:
        member=s.exec(select(Membership).where(Membership.user_id=='matrix-ops')).one();member.status='disabled';s.add(member);s.commit()
    called=Mock();monkeypatch.setattr(aliyun,'text_agent',called)
    execute_run('tenant-a',r['id']);assert not called.called
    sign(client,'matrix-fin');assert client.get('/api/v1/matrix/overview').status_code==403
    login(client,'b')
    assert client.get('/api/v1/automation-runs/'+r['id']).status_code==404
    assert client.get('/api/v1/matrix/overview?account_id='+accounts[0]['id']).status_code==404
    assert client.get('/api/v1/contents/not-mine').status_code==404


def test_account_limit_owner_controls_and_identity_uniqueness(client,monkeypatch):
    _,accounts,_,_=setup_matrix(client,monkeypatch)
    assert client.patch('/api/v1/platform/tenants/tenant-a',json={'account_limit':2}).status_code==200
    assert client.post('/api/v1/social-accounts',json={'name':'第三个','platform':'douyin'}).status_code==400
    assert client.get('/api/v1/matrix/overview').json()['account_limit']==2
    monkeypatch.setattr(publishing,'check_login',lambda *a:{'status':'connected','external_user_id':'test0','identity_namespace':'public','identity_verified':True})
    r=client.post('/api/v1/matrix/accounts/batch',json={'account_ids':[accounts[1]['id']],'operation':'check'})
    assert r.json()['results'][0]['status']=='failed'
    with Session(engine()) as s:
        a=s.get(SocialAccount,accounts[1]['id']);assert a.identity_key.endswith('test1')


def test_matrix_zero_budget_reservation_idempotency_and_pause(client,monkeypatch):
    _,accounts,plan,_=setup_matrix(client,monkeypatch)
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'budget-pause-case'}).json()
    tid=r['tasks'][0]['id']
    with Session(engine()) as s:
        set_scope(s,'tenant-a');task=s.get(AutomationAccountTask,tid)
        m.charge(s,'tenant-a',task,'matrix-cost-01','images',1,'platform');s.commit()
        m.charge(s,'tenant-a',task,'matrix-cost-01','images',1,'platform');s.commit()
        assert len(s.exec(select(MatrixCharge)).all())==1
        a=s.get(SocialAccount,task.account_id);a.config={**a.config,'matrix':{**a.config['matrix'],'monthly_budget_fen':0}};s.add(a);s.commit()
        with pytest.raises(HTTPException):m.charge(s,'tenant-a',task,'matrix-cost-02','images',1,'platform')
    client.post('/api/v1/automation-runs/'+r['id']+'/pause')
    called=Mock();monkeypatch.setattr(aliyun,'text_agent',called)
    execute_run('tenant-a',r['id']);assert not called.called


def test_changed_profile_invalidates_authorization_and_unknown_is_not_retried(client,monkeypatch):
    p,_,plan,k=setup_matrix(client,monkeypatch,count=1)
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'unknown-model-case'}).json()
    calls=Mock(side_effect=TimeoutError('no result'))
    monkeypatch.setattr(aliyun,'text_agent',calls)
    for _ in range(4):
        execute_run('tenant-a',r['id'])
        with Session(engine()) as s:
            ids=[a.id for a in s.exec(select(AgentRun).where(AgentRun.status=='queued')).all()]
        for aid in ids:execute('agent','tenant-a',aid)
    assert calls.call_count==1
    with Session(engine()) as s:assert s.exec(select(AgentRun)).one().status=='unknown'
    response=client.patch('/api/v1/media-profiles/'+p['id'],json={'name':p['name'],'audience':'新的家长群体','knowledge_ids':[k['id']],'version':p['version']})
    assert response.status_code==200
    assert client.get('/api/v1/automation-plans').json()[0]['authorized_by']==''
    execute_run('tenant-a',r['id']);assert calls.call_count==1


def test_matrix_tables_rls_and_immutable_versions(client,monkeypatch):
    _,_,plan,_=setup_matrix(client,monkeypatch,count=1)
    assert set(m.TABLES)<=set(TENANT_TABLES)
    with Session(engine()) as s:
        with pytest.raises(Exception):s.exec(text('UPDATE automation_plan_versions SET version=10'))
        s.rollback()
        assert s.exec(select(AutomationPlanVersion)).one().version==1


def test_source_parsing_and_ssrf_block(client,monkeypatch):
    from app.matrix_sources import parse_feed,feed_url
    from app.config import settings
    raw=b'<rss><channel><item><title>Topic</title><link>https://example.com/1</link></item></channel></rss>'
    items=parse_feed(raw,'https://example.com/rss');assert items[0]['published_at'] is None
    monkeypatch.setattr(settings(),'matrix_source_hosts','example.com,localhost')
    for url in ('http://example.com','https://localhost/rss','https://127.0.0.1/rss','https://example.com@localhost/rss'):
        with pytest.raises(HTTPException):feed_url(url)
    with pytest.raises(Exception):parse_feed(b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///etc/passwd">]><rss>&x;</rss>','https://example.com')


def test_live_plan_requires_current_trial_and_does_not_pick_first_account(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    r=client.post('/api/v1/automation-plans/'+plan['id']+'/enabled',json={'enabled':True,'version':1})
    assert r.status_code==400 and r.json()['detail']['code']=='TRIAL_REQUIRED'
    with Session(engine()) as s:
        first=s.get(SocialAccount,accounts[0]['id']);first.profile_id=None;s.add(first);s.commit()
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'no-account-fallback'})
    assert r.status_code==400
    assert client.get('/api/v1/automation-runs').json()==[]


def test_matrix_publish_partial_success_unknown_no_replay(client,monkeypatch):
    from app.config import settings
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    calls=fake_models(monkeypatch,k['id'])
    plan=client.patch('/api/v1/automation-plans/'+plan['id'],json={'name':plan['name'],'profile_id':p['id'],'version':1,'spec':{**plan['spec'],'review':'auto'}}).json()
    trial=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'publish-trial-current'}).json()
    drive(trial['id'])
    enabled=client.post('/api/v1/automation-plans/'+plan['id']+'/enabled',json={'version':plan['version'],'enabled':True})
    assert enabled.status_code==200,enabled.text
    def check(tid,acc):
        identity=acc.identity_key.split(':')[-1]
        return {'status':'connected','external_user_id':identity,'identity_namespace':'public','identity_verified':True}
    monkeypatch.setattr(publishing,'check_login',check)
    monkeypatch.setattr(settings(),'allow_live_publish',True)
    attempts=[]
    def publish(tid,account,job,version,assets):
        attempts.append((account.id,job.id))
        return {'status':'unknown'} if account.id==accounts[0]['id'] else {'status':'succeeded','external_id':'fake-work-01','external_url':'https://www.xiaohongshu.com/explore/fake-work-01'}
    monkeypatch.setattr(publishing,'publish',publish)
    run=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'publish-two-accounts','trial':False}).json()
    for _ in range(25):
        execute_run('tenant-a',run['id'])
        with Session(engine()) as s:
            pending=[('agent',a.id) for a in s.exec(select(AgentRun).where(AgentRun.status=='queued')).all()]+[('media',a.id) for a in s.exec(select(MediaJob).where(MediaJob.status=='queued')).all()]+[('publish',a.id) for a in s.exec(select(PublishJob).where(PublishJob.status=='scheduled')).all()]
        for kind,jid in pending:execute(kind,'tenant-a',jid)
    assert len(attempts)==2
    assert len(set(aid for aid,_ in attempts))==2
    jobs=client.get('/api/v1/publish-jobs').json()
    assert {j['status'] for j in jobs}=={'unknown','succeeded'}
    tasks=client.get('/api/v1/automation-runs/'+run['id']).json()['tasks']
    assert any(t['status']=='waiting_metrics' for t in tasks)
    assert any(t['status']=='blocked' for t in tasks)


def test_director_rejects_unauthorized_render_mode_and_facts(client,monkeypatch):
    from app.matrix_execution import agent
    from app.matrix_agents import MatrixDraft, DirectorScene
    p,accounts,plan,k=setup_matrix(client,monkeypatch,count=1)
    run=AgentRun(tenant_id='tenant-a',kind='matrix_content',request_id='director-test',actor_id='user-a',input={'facts':[{'id':k['id']}],'spec':{**plan['spec'],'allowed_render_modes':['program']},'account':{'form':'video'},'profile':{'asset_ids':[]}})
    wrong=MatrixDraft(title='AI科普',body='这是一段给家长看的教育说明，观察工具并核对事实。',cards=['科普练习'],image_prompt='课堂插画',render_mode='aigc',decision_reason='用抽象动画来表现概念，帮助家长理解。',source_ids=[k['id']],scenes=[DirectorScene(kind='aigc',purpose='说明',text='认识概念',narration='和孩子一起观察生活中的问题。',seconds=15,prompt='抽象场景')]*3)
    monkeypatch.setattr('app.worker.agent_call',lambda *a,**kw:(wrong,100))
    with Session(engine()) as s:
        with pytest.raises(HTTPException) as e:agent(s,'tenant-a',run)
        assert e.value.detail['code']=='RENDER_MODE_FORBIDDEN'


def test_account_identity_change_and_blind_version_guard(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch,count=1)
    with Session(engine()) as s:
        a=s.get(SocialAccount,accounts[0]['id'])
        m.observed_identity(s,'tenant-a',a,{'status':'connected','external_user_id':'different-account','identity_namespace':'public','identity_verified':True})
        s.commit();assert a.paused and not a.identity_key
    plan_response=client.post('/api/v1/automation-plans/'+plan['id']+'/enabled',json={'enabled':True,'version':1})
    assert plan_response.status_code==400 and plan_response.json()['detail']['code']=='IDENTITY_REQUIRED'


def test_explicit_retry_is_account_local_idempotent_and_reserves_again(client,monkeypatch):
    from app.domain import release_reservations
    p,accounts,plan,k=setup_matrix(client,monkeypatch)
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'retry-known-rejection'}).json()
    task_id=r['tasks'][0]['id']
    with Session(engine()) as s:
        task=s.get(AutomationAccountTask,task_id)
        m.charge(s,'tenant-a',task,'known-key-rejection','text_tokens',20000,'platform')
        job=AgentRun(tenant_id='tenant-a',kind='matrix_content',request_id='known-key-rejection',actor_id='user-a',status='failed',input={'_matrix_task_id':task.id},error_code='MODEL_KEY_REJECTED')
        s.add(job);s.flush()
        st=AutomationStep(tenant_id='tenant-a',task_id=task.id,key='director',object_id=job.id,status='failed')
        s.add(st);s.flush();release_reservations(s,'tenant-a',job.request_id);s.commit()
        old_id=job.id
    path='/api/v1/automation-tasks/'+task_id+'/steps/director/retry'
    a=client.post(path,json={'request_id':'retry-client-0001'});assert a.status_code==200,a.text
    assert a.json()['object_id']!=old_id
    assert client.post(path,json={'request_id':'retry-client-0001'}).json()['object_id']==a.json()['object_id']
    with Session(engine()) as s:
        charges=s.exec(select(MatrixCharge)).all();assert len(charges)==2
        assert sum(c.state=='reserved' for c in charges)==1
        assert len({c.account_id for c in charges})==1
        old=s.get(AgentRun,old_id);assert old.status=='failed'
        latest=s.get(AgentRun,a.json()['object_id']);latest.status='unknown';s.add(latest);s.commit()
    blocked=client.post(path,json={'request_id':'retry-client-0002'});assert blocked.status_code==409


def test_paid_media_recovery_continues_when_run_paused(client,monkeypatch):
    p,accounts,plan,k=setup_matrix(client,monkeypatch,count=1)
    r=client.post('/api/v1/automation-runs',json={'plan_id':plan['id'],'request_id':'paused-paid-recovery'}).json()
    with Session(engine()) as s:
        task=s.get(AutomationAccountTask,r['tasks'][0]['id'])
        m.charge(s,'tenant-a',task,'paused-paid-video','video_seconds',10,'platform')
        job=MediaJob(tenant_id='tenant-a',kind='video',prompt='抽象场景',request_id='paused-paid-video',actor_id='user-a',status='polling',provider_task_id='existing-paid-task',parameters={'duration':10,'raw_only':True,'_matrix_task_id':task.id})
        s.add(job);s.commit();jid=job.id
    client.post('/api/v1/automation-runs/'+r['id']+'/pause')
    submitted=Mock();monkeypatch.setattr(aliyun,'submit_video',submitted)
    monkeypatch.setattr(aliyun,'video_status',lambda *a:{'output':{'task_status':'SUCCEEDED','video_url':'https://fake.invalid/result.mp4'}})
    monkeypatch.setattr('app.worker.download_result',lambda url:b'fake transport video bytes')
    execute('media','tenant-a',jid)
    assert not submitted.called
    with Session(engine()) as s:
        job=s.get(MediaJob,jid);assert job.status=='succeeded',job.error
        cost=s.exec(select(MatrixCharge).where(MatrixCharge.request_id=='paused-paid-video')).one();assert cost.state=='settled' and cost.actual_fen==600
