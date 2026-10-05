from datetime import UTC, datetime
from fastapi.testclient import TestClient
import pytest
from otd_assistant.ai.model import Intent, ModelUnavailable
from otd_assistant.config import Settings
from otd_assistant.main import create_app
from otd_assistant.tasks.api import utc_now

class FakeModel:
    value = None
    async def available(self): return True
    async def interpret(self, messages):
        if isinstance(self.value, Exception): raise self.value
        return self.value.model_copy()

def intent(action='create', **kwargs):
    return Intent.model_validate(dict(action=action, **{k: kwargs.get(k) for k in ('target','title','notes','date','time','recurrence','view','question')}))

@pytest.fixture
def setup(tmp_path):
    model = FakeModel()
    app = create_app(Settings(_env_file=None, database_path=tmp_path/'tasks.db', reminders_enabled=False), language_model=model)
    app.dependency_overrides[utc_now] = lambda: datetime(2026,10,1,17,tzinfo=UTC)
    with TestClient(app) as client: yield client, model

def chat(c, message, sid=None):
    r=c.post('/api/assistant/chat', json={'message':message,'session_id':sid})
    assert r.status_code == 200, r.text
    return r.json()

def confirm(c,r):
    return c.post('/api/assistant/confirm',json={'session_id':r['session_id'],'proposal_id':r['proposal_id']})

def test_review_and_idempotent_confirm(setup):
    c,m=setup; m.value=intent(title='Call Sam',date='2026-10-09',time='15:00')
    r=chat(c,'Remind me to call Sam tomorrow at 3 PM')
    assert c.get('/api/tasks').json()==[]
    assert confirm(c,r).status_code==200
    assert confirm(c,r).status_code==200
    tasks=c.get('/api/tasks').json()
    assert len(tasks)==1
    assert tasks[0]['next_due_at'].startswith('2026-10-02T20:00')

def test_invented_time_requires_clarification(setup):
    c,m=setup; m.value=intent(title='Walk tomorrow at 3 PM',date='2026-10-02',time='15:00')
    r=chat(c,'Remind me to walk tomorrow')
    assert r['kind']=='clarification'
    m.value=intent('update',time='09:00')
    r=chat(c,'At 9 AM',r['session_id'])
    assert r['kind']=='proposal'
    assert confirm(c,r).status_code==200
    t=c.get('/api/tasks').json()[0]
    assert t['title']=='Walk'
    assert t['next_due_at'].startswith('2026-10-02T14:00')

@pytest.mark.parametrize('action',['update','delete','complete'])
def test_stale_proposals_rejected(setup,action):
    c,m=setup
    t=c.post('/api/tasks',json={'title':'Walk'}).json()
    m.value=intent(action,target='Walk',title='Walk outside')
    r=chat(c,'Rename Walk to Walk outside' if action=='update' else action+' Walk')
    c.patch('/api/tasks/'+t['id'],json={'notes':'Changed elsewhere'})
    assert confirm(c,r).status_code==409
    assert c.get('/api/tasks/'+t['id']).json()['status']=='open'

def test_new_message_invalidates_proposal(setup):
    c,m=setup;m.value=intent(title='Walk')
    first=chat(c,'Add Walk')
    chat(c,'Add Read',first['session_id'])
    assert confirm(c,first).status_code==409

def test_duplicate_targets_do_not_mutate(setup):
    c,m=setup
    for _ in range(2): c.post('/api/tasks',json={'title':'Walk'})
    m.value=intent('delete',target='Walk')
    assert chat(c,'Delete Walk')['kind']=='clarification'
    assert len(c.get('/api/tasks').json())==2

def test_model_failure_leaves_manual_tasks_available(setup):
    c,m=setup;m.value=ModelUnavailable('Model offline')
    assert c.post('/api/assistant/chat',json={'message':'Add Walk'}).status_code==503
    assert c.post('/api/tasks',json={'title':'Manual task'}).status_code==201
    assert c.get('/api/reminders').status_code==200

def test_unknown_session(setup):
    c,_=setup
    assert c.post('/api/assistant/chat',json={'message':'Hi','session_id':'expired'}).status_code==410

@pytest.mark.parametrize('url',['https://127.0.0.1:8081','http://example.com','http://127.0.0.1/path'])
def test_model_must_be_local(url):
    with pytest.raises(ValueError): Settings(_env_file=None,ai_url=url)

def test_slow_inference_does_not_block_manual_api(tmp_path):
    import asyncio
    import httpx
    class SlowModel(FakeModel):
        async def interpret(self, messages):
            started.set()
            await release.wait()
            return intent(title='AI draft')
    async def run():
        nonlocal started, release
        started, release = asyncio.Event(), asyncio.Event()
        app=create_app(Settings(_env_file=None,database_path=tmp_path/'slow.db',reminders_enabled=False),language_model=SlowModel())
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://test') as c:
                pending=asyncio.create_task(c.post('/api/assistant/chat',json={'message':'Add AI draft'}))
                await asyncio.wait_for(started.wait(),1)
                try:
                    manual=await asyncio.wait_for(c.post('/api/tasks',json={'title':'Manual'}),1)
                    assert manual.status_code==201
                    assert (await asyncio.wait_for(c.get('/api/reminders/status'),1)).status_code==200
                    assert (await c.post('/api/assistant/chat',json={'message':'Another'})).status_code==429
                finally:
                    release.set()
                    await pending
    started=release=None
    asyncio.run(run())

def test_explicit_title_with_pronoun_is_not_previous_task(setup):
    c,m=setup
    m.value=intent(title='Previous task')
    first=chat(c,'Add Previous task'); assert confirm(c,first).status_code==200
    target=c.post('/api/tasks',json={'title':'Fix it'}).json()
    m.value=intent('delete',target='Fix it')
    proposal=chat(c,'Delete Fix it',first['session_id'])
    assert proposal['summary'][0]=='Delete: Fix it'
    assert confirm(c,proposal).status_code==200
    assert c.get('/api/tasks/'+target['id']).status_code==404
    assert c.get('/api/tasks').json()[0]['title']=='Previous task'


def test_unsaved_draft_corrections_override_old_values(setup):
    c,m=setup
    m.value=intent(title='Call Sam',date='2026-10-02',time='15:00')
    first=chat(c,'Remind me to call Sam tomorrow at 3 PM')
    m.value=intent('update',date='2026-10-05')
    changed=chat(c,'Actually Monday',first['session_id'])
    assert '2026-10-05T15:00' in changed['summary'][-1]
    m.value=intent('update',title='Call Alex')
    changed=chat(c,'Actually call Alex instead',first['session_id'])
    assert changed['summary'][0]=='Create: Call Alex'
    assert '2026-10-05T15:00' in changed['summary'][-1]
    assert confirm(c,changed).status_code==200
    assert c.get('/api/tasks').json()[0]['title']=='Call Alex'


def test_time_only_update_preserves_existing_date(setup):
    c,m=setup
    task=c.post('/api/tasks',json={'title':'Future task','schedule':{'kind':'once','starts_at':'2026-10-12T15:00:00-05:00','timezone':'America/Chicago'}}).json()
    m.value=intent('update',target='Future task',time='10:00')
    changed=chat(c,'Move Future task to 10 AM')
    assert '2026-10-12T10:00' in changed['summary'][-1]
    assert confirm(c,changed).status_code==200
    assert c.get('/api/tasks/'+task['id']).json()['next_due_at'].startswith('2026-10-12T15:00')


@pytest.mark.parametrize('clock,expected',[('15:00','2026-10-01'),('09:00','2026-10-08')])
def test_weekly_today_uses_next_available_time(setup,clock,expected):
    c,m=setup
    m.value=intent(title='Call Sam',date='2026-10-08',time=clock,recurrence='weekly')
    r=chat(c,f'Remind me to call Sam every Thursday at {clock}')
    assert f'{expected}T{clock}' in r['summary'][-1]


@pytest.mark.parametrize('action',['patch','delete'])
def test_manual_stale_version_cannot_change_task(setup,action):
    c,_=setup
    task=c.post('/api/tasks',json={'title':'Original','notes':'Original notes'}).json()
    url='/api/tasks/'+task['id']
    current=c.patch(url,params={'expected_updated_at':task['updated_at']},json={'notes':'New notes'}).json()
    if action=='patch':
        result=c.patch(url,params={'expected_updated_at':task['updated_at']},json={'notes':'Old notes'})
    else:
        result=c.delete(url,params={'expected_updated_at':task['updated_at']})
    assert result.status_code==409
    assert c.get(url).json()['notes']=='New notes'
    if action=='delete': assert c.delete(url,params={'expected_updated_at':current['updated_at']}).status_code==204


def test_manual_version_requires_timezone(setup):
    c,_=setup
    t=c.post('/api/tasks',json={'title':'Test'}).json()
    assert c.patch('/api/tasks/'+t['id'],params={'expected_updated_at':'2026-10-01T12:00'},json={'notes':'No'}).status_code==422

@pytest.mark.parametrize('spoken,expected', [('6.50 pm','18:50'),('6.05 p.m.','18:05'),('6:50 PM','18:50'),('12.00 am','00:00'),('12.00 pm','12:00')])
def test_transcribed_dot_times(setup,spoken,expected):
    c,m=setup;m.value=intent(title='Windows hardware test',date='2026-10-01',time=None)
    r=chat(c,f'Remind me to do the Windows hardware test today at {spoken}.')
    assert r['kind']=='proposal'
    assert f'T{expected}:00' in r['summary'][-1]
    assert c.get('/api/tasks').json()==[]

@pytest.mark.parametrize('spoken',['6.75 pm','16.50 pm','6.50','3K','6.5 pm'])
def test_invalid_dot_times_do_not_match_partial_hour(setup,spoken):
    c,m=setup;m.value=intent(title='Windows hardware test',date='2026-10-01',time='18:50')
    r=chat(c,f'Remind me today at {spoken}')
    assert r['kind']=='clarification'
