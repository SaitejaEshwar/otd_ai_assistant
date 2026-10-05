"""Bounded local WAV transcription; audio is deleted after processing."""
import asyncio
from array import array
import io
import os
from pathlib import Path
import subprocess
import tempfile
import wave

from fastapi import APIRouter, HTTPException, Request
from .config import PROJECT_ROOT

MAX_BYTES = 16000 * 2 * 30 + 4096


def validate_audio(data: bytes) -> None:
    try:
        with wave.open(io.BytesIO(data), 'rb') as audio:
            frames = audio.getnframes()
            if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getcomptype()) != (1, 2, 16000, 'NONE'):
                raise ValueError()
            if not 4000 <= frames <= 480000:
                raise ValueError()
            raw = audio.readframes(frames)
            if len(raw) != frames * 2:
                raise ValueError()
    except (wave.Error, EOFError, ValueError):
        raise HTTPException(422, 'Record 0.25–30 seconds of mono 16 kHz PCM audio.')
    samples = array('h', raw)
    if max(abs(s) for s in samples) < 100:
        raise HTTPException(422, 'No speech detected. Check your microphone and try again.')


class Whisper:
    def __init__(self, root: Path = PROJECT_ROOT):
        self.root = root

    def executable(self):
        name = 'whisper-cli.exe' if os.name == 'nt' else 'whisper-cli'
        return next((path for path in sorted((self.root / 'runtime' / 'whisper').rglob(name))
                     if path.is_file() and (os.name == 'nt' or os.access(path, os.X_OK))), None)

    def available(self):
        return self.executable() is not None and (self.root / 'models' / 'ggml-base.en.bin').is_file()

    def transcribe(self, data: bytes):
        if not self.available():
            raise HTTPException(503, 'Voice is not installed. Follow the voice setup instructions for your operating system and restart the service.')
        with tempfile.TemporaryDirectory(prefix='otd-voice-') as directory:
            source = Path(directory) / 'speech.wav'
            output = Path(directory) / 'transcript'
            source.write_bytes(data)
            try:
                result = subprocess.run([str(self.executable()), '-m', str(self.root / 'models' / 'ggml-base.en.bin'),
                    '-f', str(source), '-l', 'en', '-otxt', '-of', str(output), '-nt', '-ng', '-t', '4'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode != 0 or not output.with_suffix('.txt').is_file():
                    raise HTTPException(503, 'Local transcription failed. Try again or type your request.')
                text = output.with_suffix('.txt').read_text(encoding='utf-8').strip()
            except subprocess.TimeoutExpired:
                raise HTTPException(504, 'Transcription timed out. Try a shorter recording.')
            except OSError:
                raise HTTPException(503, 'Cannot start the local voice runtime. Check the voice installation.')
        if not text or text.startswith('[') or text.startswith('('):
            raise HTTPException(422, 'No clear speech detected. Please try again.')
        if len(text) > 1000:
            raise HTTPException(422, 'Transcript is too long. Please record a shorter request.')
        return text


def voice_router(engine=None):
    engine = engine or Whisper()
    lock = asyncio.Lock()
    router = APIRouter(prefix='/api/voice', tags=['voice'])

    @router.get('/status')
    def status():
        return {'available': engine.available(), 'local': True, 'max_seconds': 30}

    @router.post('/transcribe')
    async def transcribe(request: Request):
        if request.headers.get('content-type', '').split(';')[0] != 'audio/wav':
            raise HTTPException(415, 'Send audio/wav.')
        if lock.locked():
            raise HTTPException(429, 'Voice is busy. Please try again shortly.')
        async with lock:
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > MAX_BYTES:
                    raise HTTPException(413, 'Recording exceeds the 30-second limit.')
            validate_audio(bytes(data))
            job = asyncio.create_task(asyncio.to_thread(engine.transcribe, bytes(data)))
            try:
                text = await asyncio.shield(job)
            except asyncio.CancelledError:
                # Keep ownership until the native worker exits and removes its files.
                try:
                    await job
                finally:
                    raise
            return {'text': text}
    return router
