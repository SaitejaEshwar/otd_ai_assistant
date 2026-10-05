# Raspberry Pi 5 deployment

Status (2026-10-05): user confirmed touchscreen buttons/text entry, task persistence after reload, reminder delivery and completion through Done on the Pi. Deployment is user-guided, with no SSH access. Background-music recognition limitations remain deferred.

Hardware: Pi 5 (16 GB), aarch64 Debian 13 trixie, Hailo-10H runtime/firmware 5.1.1. Standalone Hailo-Ollama chat succeeded with `qwen2.5-instruct:1.5b` on port 8000. The app runs on port 8001 from `~/Projects/otd_ai_assistant`. Node 22.23.3 and pnpm 11.28.4 are installed.

## Hailo app configuration (after deploying adapter changes)

Merge into the Pi `.env`, preserving other settings:

```dotenv
OTD_PORT=8001
OTD_AI_BACKEND=hailo_ollama
OTD_AI_URL=http://127.0.0.1:8000
OTD_AI_MODEL=qwen2.5-instruct:1.5b
OTD_TIMEZONE=America/Chicago
```

Restart the app, leaving Hailo-Ollama running. Check `/api/assistant/status`, then submit a typed task request. Verify the proposal's title/date/time, no save before confirmation, and exactly one save afterward. The adapter prompts for JSON and validates it locally; schema-constrained generation is not assumed. Invalid/incomplete output leaves manual task entry available. Actual structured task interpretation on this model still needs hardware validation.

Pending: AI integration check, native voice installation, services and kiosk startup, reboot/snooze recovery, disconnected operation, performance and thermals. Screenshots show limited dialog space with the keyboard and a clipped native date picker; revisit in kiosk mode.

## Original installation checklist (hardware and OS now confirmed)

- Pi hostname/IP and SSH username (no passwords or private keys in chat).
- Installed OS, version and architecture; whether a desktop session is available.
- Whether AI HAT+ 2, touchscreen and USB microphone are physically connected.
- Whether Windows task data should be migrated; do not copy or replace databases without deciding this.

Read-only commands to run on the Pi:

```sh
cat /etc/os-release
uname -m
cat /proc/device-tree/model
hostname -I
df -h /
free -h
lsusb
lspci
```

## Deployment order

1. Inspect the actual Pi OS, storage, hardware detection and SSH access.
2. Install a native Python virtual environment and build the frontend. Never copy Windows .venv, node_modules or executable runtimes to Linux.
3. Bring up the local task API/dashboard and verify SQLite persistence before enabling AI.
4. Build/install the Linux whisper.cpp runtime and verified English model. The app now discovers executable `whisper-cli` under `runtime/whisper/` on Linux; Windows retains `whisper-cli.exe`. Validate real USB capture in the Pi browser.
5. Install the AI HAT+ 2 software matching the OS, verify hardware detection, and test model-server requests. Implement/test the server adapter before selecting it for task interpretation.
6. Configure systemd startup/recovery for backend services and desktop-session browser startup. Preserve loopback-only access, task data, existing OS configuration and microphone permission prompts.
7. Verify touchscreen orientation, scaling, on-screen keyboard and kiosk usability on the physical display.
8. Run offline task/voice/reminder, restart, snooze, performance and thermal acceptance checks on the Pi.

## AI HAT+ 2 integration notes

The [official Raspberry Pi AI software guide](https://www.raspberrypi.com/documentation/computers/ai.html) describes Hailo-10H with hailo-ollama. Its documented API uses `/api/chat`, and its default port is 8000, which conflicts with the desk app default. Select distinct ports after inspecting the installed runtime. The current Windows adapter uses llama.cpp's `/v1/chat/completions`; changing only its URL is not sufficient. Structured intent validation and confirmation must remain enforced regardless of the inference backend.

Do not assume the Windows GGUF model can run on the Hailo NPU. Select an available Hailo-compatible model and validate its output on the actual device. Exact driver/package installation and kiosk configuration depend on the confirmed OS.

## Current verification

Windows regression suite: 117 tests passed after adding Linux Whisper discovery and the Hailo adapter. Hailo transport is tested with mocked HTTP responses; native voice and end-to-end Hailo task interpretation remain untested. Pi manual task checks above are user-reported hardware results, not automated tests.
