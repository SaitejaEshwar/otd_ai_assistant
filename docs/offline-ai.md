# Offline AI on Windows

The typed assistant runs Qwen2.5-Instruct 1.5B (Q4_K_M GGUF) in llama.cpp on the CPU. Task data stays on this computer. Internet is needed for the initial download, then neither chat nor reminders requires it. Microphone input is available through [offline voice](offline-voice.md).

## Install and start

From the repository root after normal project setup:

```powershell
.\.venv\Scripts\python.exe scripts\setup_ai.py
.\scripts\start-ai.ps1
```

The installer downloads the pinned official Windows x64 CPU runtime and approximately 1.1 GB model, verifies SHA-256 hashes, and puts them in ignored `runtime/` and `models/` directories. Allow additional disk space for extraction. Read the upstream Qwen model license before redistributing the model. Download URLs, revision and checksums are recorded in `scripts/setup_ai.py`.

If PowerShell blocks scripts, run the executable directly without changing execution policy:

```powershell
.\runtime\llama\llama-server.exe -m models\qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 8192 -np 1 -ngl 0 --alias otd-qwen
```

Keep that terminal open. In another terminal start the desk service:

```powershell
.\.venv\Scripts\python.exe -m otd_assistant
```

Open http://127.0.0.1:8000. Restart the backend and rebuild the frontend after upgrading source. Both servers bind to loopback. `OTD_AI_URL`, `OTD_AI_MODEL`, and `OTD_AI_TIMEOUT_SECONDS` are optional settings in `.env`. HTTP proxy environment variables are ignored for model calls.

## Try it

- “Remind me to call Sam tomorrow at 3 PM.” Review, then Confirm.
- “Move that to Saturday at 10 AM.” Review the revised schedule.
- “What do I have coming up?” Reads actual stored tasks.
- “Remind me to take a walk tomorrow.” Answer the time question with “At 9 AM.”
- “Complete call Sam” or “Delete call Sam.” Both require confirmation.

Use explicit AM/PM, HH:MM, noon or midnight. Relative calendar dates use the configured local time zone. The small model can misunderstand complex language; always inspect the proposal. Use Add task for unsupported phrasing, ambiguous task names, complex edits, or when the model is unavailable. One task action per message is supported. Lists show up to 100 matches. General knowledge chat, automatic model startup and Pi/Hailo acceleration are outside this milestone.

## Reliability

Chat never writes tasks. The server stores a short-lived proposal and confirmation token; confirming twice does not duplicate the action. A changed/deleted target rejects an old proposal. Sending another message invalidates the previous proposal. Cancel closes the review without saving; a follow-up can revise the unsaved draft. New conversation clears the UI conversation reference. Conversations/proposals expire after 30 minutes idle and are lost on backend restart; tasks and reminders persist in SQLite. The interface recovers from an expired conversation on the next request.

The model cannot run commands or access arbitrary files. Structured output is validated before a proposal is built. Explicit clock times are grounded in user text so the model cannot silently fill a missing reminder time. Task matching asks for clarification when multiple titles match. Inference uses asynchronous HTTP with a timeout; reminders and manual task endpoints remain independent. Only one AI request is processed at a time.

## Verification

Run `.\.venv\Scripts\python.exe -m pytest -q` and `pnpm --dir frontend build`. Automated tests use an injected model and temporary databases. Live Windows CPU checks also exercised the five-message sequence above with the downloaded Qwen model and a temporary database. Performance and interpretation vary with hardware and phrasing.
