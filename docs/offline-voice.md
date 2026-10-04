# Offline voice input (Windows)

## Setup

From the repository root, after normal project setup:

```powershell
.\.venv\Scripts\python.exe scripts\setup_voice.py
```

This downloads the official [whisper.cpp v1.8.2 Windows CPU runtime](https://github.com/ggml-org/whisper.cpp/releases/tag/v1.8.2) and [base.en model](https://huggingface.co/ggerganov/whisper.cpp). Both downloads are SHA-256 verified against pinned hashes. Model size is about 148 MB. Internet is required only for installation. Files are stored in ignored runtime/ and models/ directories. Keep the extracted DLLs beside whisper-cli.exe. No separate speech server is needed.

Rebuild the frontend with `pnpm --dir frontend build` and restart `.\.venv\Scripts\python.exe -m otd_assistant`. The local Qwen server is needed for task interpretation after Send, but transcription itself does not depend on Qwen.

## Use

1. Open http://127.0.0.1:8000 in a browser supporting microphone capture and AudioWorklet. Select your intended microphone as the Windows/browser default.
2. Tap Talk and allow microphone access when prompted. Capture starts only after this action.
3. Speak English and tap Stop. Recording stops automatically after 30 seconds. Cancel recording discards it. Switching away from the tab cancels capture.
4. Wait for local transcription. The microphone is off while Whisper runs.
5. Review and edit the transcript in the input box, then Send. It appends to any existing draft. The assistant's normal confirmation still applies to changes.

Microphone permission denied, missing/disconnected devices, unsupported browsers, silence, unavailable runtime, and transcription timeouts display an error while typed input remains available. If this app's embedded browser does not expose a microphone, open the same localhost URL in a supported desktop browser. For precise schedules, correct transcription to explicit times such as `3 PM` before sending. Whisper can mishear speech or produce words from background noise; transcription is never automatically submitted.

## Limits and privacy

Capture is mono 16 kHz PCM, 0.25–30 seconds. The API rejects oversized, malformed, unsupported and silent audio. One transcription runs at a time, with a 90-second native-process timeout and four CPU threads. API/reminder processing remains independent. The browser stops tracks on Stop, Cancel, tab hiding during capture, and page exit. Cancel during transcription aborts the browser request; native work may finish within its timeout before cleanup.

Audio is sent only to the local desk service. Temporary WAV and transcript files are removed after completion/error/timeout; they are not task records or logs. An abrupt process/OS crash can leave an `otd-voice-*` directory in the OS temporary directory. No wake word, background listening, cloud recognition, spoken responses, or Pi microphone configuration is included.

## Verification

Automated backend tests cover validation, upload size, missing runtime, temporary-file cleanup, timeout and busy handling. A real CPU transcription was verified with whisper.cpp's public JFK sample. Actual microphone quality and permission behavior must still be checked with your microphone/browser; sample-file transcription is not a physical microphone test.
