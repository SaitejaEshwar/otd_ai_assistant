"""Cross-component Windows acceptance checks with isolated task databases."""
import asyncio
from datetime import UTC, datetime, timedelta
import io
import math
import struct
import threading
import time
import wave
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient
from otd_assistant.ai.model import Intent
from otd_assistant.config import Settings
from otd_assistant.main import create_app
from otd_assistant.tasks.api import utc_now
from otd_assistant.voice import Whisper


def wait_reminders(client, count):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        rows = client.get('/api/reminders').json()
        if len(rows) == count: return rows
        time.sleep(.05)
    raise AssertionError(f'Expected {count} reminders, got {rows}')


def test_restart_recovers_tasks_pending_snooze_and_acknowledgments(tmp_path):
    now = datetime.now(UTC)
    settings = Settings(_env_file=None, database_path=tmp_path/'acceptance.db')
    def app():
        application = create_app(settings)
        application.dependency_overrides[utc_now] = lambda: now
        return application
    with TestClient(app()) as c:
        for title in ['Pending', 'Snoozed', 'Dismissed', 'Done']:
            assert c.post('/api/tasks',json={'title':title,'schedule':{'kind':'once','starts_at':(now-timedelta(minutes=1)).isoformat()}}).status_code == 201
        reminders = {r['title']:r for r in wait_reminders(c,4)}
        for title, action in [('Snoozed','snooze'),('Dismissed','dismiss'),('Done','done')]:
            r=reminders[title]
            assert c.post('/api/reminders/'+r['id']+'/action',json={'action':action,'expected_version':r['version']}).status_code==200
    with TestClient(app()) as c:
        assert len(c.get('/api/tasks?view=all').json())==4
        assert [r['id'] for r in wait_reminders(c,1)]==[reminders['Pending']['id']]
        history=c.get('/api/reminders?history=true').json()
        assert len(history)==4
        assert {r['title']:r['state'] for r in history}=={'Pending':'pending','Snoozed':'pending','Dismissed':'dismissed','Done':'done'}
        now += timedelta(minutes=11)
        assert {r['id'] for r in wait_reminders(c,2)}=={reminders['Pending']['id'],reminders['Snoozed']['id']}


def test_reminders_and_manual_tasks_during_ai_and_voice(tmp_path,monkeypatch):
    entered_ai=threading.Event();entered_voice=threading.Event();release=threading.Event()
    class Model:
        async def available(self): return True
        async def interpret(self,messages):
            entered_ai.set()
            while not release.is_set(): await asyncio.sleep(.01)
            return Intent(action='list',target=None,title=None,notes=None,date=None,time=None,recurrence=None,view='open',question=None)
    def transcribe(self,data):
        entered_voice.set();assert release.wait(10);return 'Read a book'
    monkeypatch.setattr(Whisper,'transcribe',transcribe)
    stream=io.BytesIO()
    with wave.open(stream,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
        w.writeframes(b''.join(struct.pack('<h',int(1000*math.sin(i/10))) for i in range(16000)))
    with TestClient(create_app(Settings(_env_file=None,database_path=tmp_path/'busy.db'),language_model=Model())) as c, ThreadPoolExecutor(2) as pool:
        ai=pool.submit(c.post,'/api/assistant/chat',json={'message':'Show my tasks'})
        voice=pool.submit(c.post,'/api/voice/transcribe',content=stream.getvalue(),headers={'content-type':'audio/wav'})
        try:
            assert entered_ai.wait(2) and entered_voice.wait(2)
            assert c.post('/api/tasks',json={'title':'Due during inference','schedule':{'kind':'once','starts_at':datetime.now(UTC).isoformat()}}).status_code==201
            r=wait_reminders(c,1)[0]
            assert c.post('/api/reminders/'+r['id']+'/action',json={'action':'done','expected_version':r['version']}).status_code==200
            assert c.get('/api/tasks?view=completed').json()[0]['title']=='Due during inference'
        finally:
            release.set()
        assert ai.result().status_code==200 and voice.result().status_code==200
