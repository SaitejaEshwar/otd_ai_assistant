import io
import math
import struct
import subprocess
import threading
import wave
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from otd_assistant.voice import MAX_BYTES, Whisper, voice_router


def audio(seconds=1, rate=16000, silent=False):
    target=io.BytesIO()
    with wave.open(target,'wb') as w:
        w.setnchannels(1);w.setsampwidth(2);w.setframerate(rate)
        w.writeframes(b''.join(struct.pack('<h',0 if silent else int(1000*math.sin(i/10))) for i in range(int(seconds*rate))))
    return target.getvalue()

class Engine:
    calls=0
    def available(self): return True
    def transcribe(self,data): self.calls+=1;return 'Call Sam tomorrow at 3 PM'

@pytest.fixture
def setup():
    engine=Engine();app=FastAPI();app.include_router(voice_router(engine))
    with TestClient(app) as c: yield c,engine


def test_transcript_only(setup):
    c,e=setup
    assert c.get('/api/voice/status').json()['available']
    r=c.post('/api/voice/transcribe',content=audio(),headers={'content-type':'audio/wav'})
    assert r.json()=={'text':'Call Sam tomorrow at 3 PM'}
    assert e.calls==1

@pytest.mark.parametrize('data,status',[(b'broken',422),(audio(silent=True),422),(audio(.1),422),(audio(rate=8000),422),(b'x'*(MAX_BYTES+1),413),(audio()[:-10],422)], ids=["malformed","silence","short","rate","oversized","truncated"])
def test_invalid_recording_never_reaches_engine(setup,data,status):
    c,e=setup
    assert c.post('/api/voice/transcribe',content=data,headers={'content-type':'audio/wav'}).status_code==status
    assert e.calls==0


def test_wrong_content_type(setup):
    c,e=setup
    assert c.post('/api/voice/transcribe',content=audio()).status_code==415
    assert e.calls==0

@pytest.mark.parametrize('failure',[False,True])
def test_native_timeout_and_cleanup(tmp_path,monkeypatch,failure):
    runtime=tmp_path/'runtime'/'whisper';runtime.mkdir(parents=True)
    (runtime/'whisper-cli.exe').touch();(tmp_path/'models').mkdir();(tmp_path/'models'/'ggml-base.en.bin').touch()
    recorded=[]
    def run(args,**kwargs):
        source=Path(args[args.index('-f')+1]);recorded.append(source)
        assert source.exists() and kwargs['timeout']==90
        if failure: raise subprocess.TimeoutExpired(args,90)
        Path(args[args.index('-of')+1]+'.txt').write_text('Call Sam',encoding='utf-8')
        return subprocess.CompletedProcess(args,0)
    monkeypatch.setattr(subprocess,'run',run)
    if failure:
        with pytest.raises(HTTPException) as exc: Whisper(tmp_path).transcribe(audio())
        assert exc.value.status_code==504
    else: assert Whisper(tmp_path).transcribe(audio())=='Call Sam'
    assert not recorded[0].parent.exists()


def test_missing_installation(tmp_path):
    with pytest.raises(HTTPException) as exc: Whisper(tmp_path).transcribe(audio())
    assert exc.value.status_code==503


def test_busy_transcription_does_not_block_status(setup):
    c,e=setup;entered=threading.Event();release=threading.Event()
    def transcribe(data): entered.set();release.wait(5);return 'Test'
    e.transcribe=transcribe
    worker=threading.Thread(target=lambda:c.post('/api/voice/transcribe',content=audio(),headers={'content-type':'audio/wav'}))
    worker.start();assert entered.wait(2)
    try:
        assert c.get('/api/voice/status').status_code==200
        assert c.post('/api/voice/transcribe',content=audio(),headers={'content-type':'audio/wav'}).status_code==429
    finally: release.set();worker.join()

@pytest.mark.parametrize('platform,filename', [('nt','whisper-cli.exe'),('posix','whisper-cli')])
def test_voice_runtime_platform_selection(tmp_path,monkeypatch,platform,filename):
    from types import SimpleNamespace
    from otd_assistant import voice
    runtime=tmp_path/'runtime'/'whisper'/'build'/'bin';runtime.mkdir(parents=True)
    (runtime/'whisper-cli.exe').touch();(runtime/'whisper-cli').touch()
    monkeypatch.setattr(voice,'os',SimpleNamespace(name=platform,X_OK=1,access=lambda path,mode:True))
    assert Whisper(tmp_path).executable()==runtime/filename


def test_linux_voice_requires_executable_file(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from otd_assistant import voice
    runtime=tmp_path/'runtime'/'whisper';runtime.mkdir(parents=True)
    (runtime/'whisper-cli').touch()
    monkeypatch.setattr(voice,'os',SimpleNamespace(name='posix',X_OK=1,access=lambda path,mode:False))
    assert Whisper(tmp_path).executable() is None
