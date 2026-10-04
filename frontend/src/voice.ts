function wav(chunks: Float32Array[]): Blob {
  const count = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const buffer = new ArrayBuffer(44 + count * 2), view = new DataView(buffer);
  const word = (offset: number, value: string) => [...value].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  word(0, 'RIFF'); view.setUint32(4, 36 + count * 2, true); word(8, 'WAVE'); word(12, 'fmt ');
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  word(36, 'data'); view.setUint32(40, count * 2, true);
  let offset = 44;
  for (const chunk of chunks) for (const sample of chunk) { view.setInt16(offset, Math.max(-1, Math.min(1, sample)) * 32767, true); offset += 2; }
  return new Blob([buffer], {type: 'audio/wav'});
}

export function startVoice(isBusy: () => boolean): () => boolean {
  const button = document.getElementById('talk') as HTMLButtonElement;
  const status = document.getElementById('voice-state')!;
  const cancel = document.getElementById('cancel-voice') as HTMLButtonElement;
  const draft = document.getElementById('draft') as HTMLInputElement;
  let phase: 'idle' | 'starting' | 'recording' | 'transcribing' = 'idle';
  let stream: MediaStream | null = null, context: AudioContext | null = null, recorder: AudioWorkletNode | null = null;
  let timer = 0, count = 0, generation = 0;
  let chunks: Float32Array[] = [];
  let controller: AbortController | null = null;
  function release(): void {
    clearTimeout(timer); recorder?.disconnect(); recorder = null;
    stream?.getTracks().forEach(track => track.stop()); stream = null;
    if (context) void context.close(); context = null;
  }
  function idle(message: string): void {
    phase = 'idle'; button.disabled = false; button.textContent = 'Talk'; button.setAttribute('aria-pressed', 'false');
    cancel.hidden = true; draft.readOnly = false; status.textContent = message;
  }
  function abort(): void {
    generation++; controller?.abort(); release(); chunks = []; idle('Microphone off. Recording discarded.');
  }
  async function stop(): Promise<void> {
    if (phase !== 'recording') return;
    phase = 'transcribing'; release(); button.disabled = true; button.textContent = 'Transcribing';
    status.textContent = 'Microphone off. Transcribing locally…';
    const audio = wav(chunks); chunks = []; const current = generation;
    controller = new AbortController(); timer = window.setTimeout(() => controller?.abort(), 100000);
    try {
      const response = await fetch('/api/voice/transcribe', {method: 'POST', headers: {'Content-Type': 'audio/wav'}, body: audio, signal: controller.signal});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Transcription failed. Try again.');
      if (current !== generation) return;
      const combined = [draft.value.trim(), data.text].filter(Boolean).join(' ');
      if (combined.length > 1000) throw new Error('The draft and recording exceed 1000 characters. Shorten the draft and record again.');
      draft.value = combined;
      idle('Microphone off. Review your transcript, then tap Send.'); draft.focus();
    } catch (error) {
      if (current === generation) idle(error instanceof Error && error.name !== 'AbortError' ? error.message : 'Transcription cancelled or timed out. Please try again.');
    } finally { if (current === generation) clearTimeout(timer); }
  }
  button.addEventListener('click', async () => {
    if (phase === 'recording') { await stop(); return; }
    if (phase !== 'idle' || isBusy()) return;
    if (!navigator.mediaDevices?.getUserMedia || !window.AudioWorkletNode) { idle('Voice needs a browser with microphone support on localhost. You can still type.'); return; }
    const current = ++generation;
    phase = 'starting'; button.disabled = true; cancel.hidden = false;
    status.textContent = 'Waiting for microphone permission…';
    try {
      const acquired = await navigator.mediaDevices.getUserMedia({audio: {channelCount: 1, echoCancellation: true, noiseSuppression: true}, video: false});
      if (current !== generation) { acquired.getTracks().forEach(t => t.stop()); return; }
      stream = acquired; context = new AudioContext({sampleRate: 16000});
      await context.audioWorklet.addModule('/recorder.js');
      if (current !== generation) return;
      await context.resume();
      if (current !== generation) return;
      recorder = new AudioWorkletNode(context, 'desk-recorder'); chunks = []; count = 0;
      recorder.port.onmessage = event => {
        if (phase !== 'recording') return;
        const chunk = (event.data as Float32Array).slice(0, 480000 - count);
        chunks.push(chunk); count += chunk.length;
        if (count >= 480000) void stop();
      };
      context.createMediaStreamSource(stream).connect(recorder);
      const mute = context.createGain(); mute.gain.value = 0; recorder.connect(mute).connect(context.destination);
      stream.getAudioTracks()[0].addEventListener('ended', () => { if (phase === 'recording') abort(); });
      phase = 'recording'; draft.readOnly = true; button.disabled = false; button.textContent = 'Stop'; button.setAttribute('aria-pressed', 'true');
      status.textContent = 'Recording · tap Stop when finished (30 seconds maximum).';
      timer = window.setTimeout(() => void stop(), 30000);
    } catch (error) {
      if (current === generation) { release(); idle(error instanceof DOMException && error.name === 'NotAllowedError' ? 'Microphone permission denied. Allow it in your browser, or type instead.' : 'Could not open the microphone. Check your input device and try again.'); }
    }
  });
  cancel.addEventListener('click', abort);
  window.addEventListener('pagehide', abort);
  document.addEventListener('visibilitychange', () => { if (document.hidden && (phase === 'recording' || phase === 'starting')) abort(); });
  fetch('/api/voice/status').then(r => r.json()).then(data => { if (phase === 'idle') status.textContent = data.available ? 'Microphone off · local voice ready' : 'Voice not installed · run scripts/setup_voice.py'; }).catch(() => { status.textContent = 'Voice service unavailable. You can still type.'; });
  return () => phase !== 'idle';
}
