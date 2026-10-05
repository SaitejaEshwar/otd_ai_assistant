# Windows acceptance testing — October 4, 2026

## Result

Automated and local-model checks passed. The user confirmed successful physical microphone transcription and microphone shutdown. No new functional defect was reproduced in the checks below. Hardware/environment checks listed as pending are not covered by that result.

| Check | Result and evidence |
| --- | --- |
| Backend regression suite | PASS: 91 tests, including two new cross-component acceptance tests. One existing Starlette/httpx deprecation warning. |
| Frontend build | PASS: TypeScript validation and Vite production build. |
| Voice UI lifecycle | PASS: eight Node tests using mocked browser/audio APIs: permission denial, cancellation while permission is pending, capture cancellation, tab hiding, page exit, transcript review, silence errors, automatic 30-second stop. These are not physical-device tests. |
| Restart recovery | PASS: dispose and recreate the application against the same temporary SQLite file; task data, pending reminder ID, snooze wake time, dismiss and completion state survive. Snoozed record becomes visible after an advanced test clock. No ten-minute wall-clock wait was required. |
| Concurrent operation | PASS: reminder generated and completed through HTTP while both model inference and voice transcription were deliberately held busy. Uses controlled model/voice doubles and the real scheduler/database. |
| Real local Qwen | PASS: create call Sam, move to Monday at 10 AM, list upcoming, complete, delete, ask for a missing time, and resolve “At 9 AM.” All proposed writes confirmed only in a temporary database. Requests took approximately 1.4–2.6 seconds on this machine. |
| External-network dependency | PASS (limited scope): the Python live-model test rejected external socket connections; none were attempted. Local model HTTP remained available. This does not prove the browser/native processes under a machine-wide internet disconnection. |
| Browser transcript ? proposal | PASS: preserved transcript through an expired-session error; retry produced call Sam for October 5 at 3 PM Chicago time. Cancelled without saving and restored the original transcript. |
| Physical permission denial | PASS, user-reported October 4: blocking microphone access displayed the permission-denied message; typed input worked while blocked; recording worked again after permission was restored. |
| Quiet comparison | PARTIAL, user-reported October 4 after the requested quiet comparison: two of three transcripts preserved call Sam / tomorrow / 3 p.m.; one changed Sam to channel. Exact phrasing was preserved only in the third attempt. Repeated quiet recognition is not yet reliable. |
| Bose Bluetooth microphone comparison | PASS for key details in this three-attempt sample, user-reported: all transcripts retained call Sam, tomorrow, and 3 PM; two retained the request wording and the third changed the opening to "You mind me". The user confirmed quiet conditions; speaking distance was not specified. This is not acceptance of the project USB microphone or proof of general recognition reliability. |
| Bose background-music comparison | FAIL for this sample, user-reported following the requested music test: only one of three transcripts preserved both Sam and 3 PM. One changed Sam to Stamps; another changed 3 PM to 3K. Quiet Bose sample preserved key details in three of three attempts. |
| Background-noise recognition | FAIL for the tested background-music condition, user-reported October 4: while a Telugu song played on a phone, the English request "Remind me to call Sam tomorrow at 3 p.m." produced materially incorrect transcripts in three attempts. See details below. |
| Bose Bluetooth disconnect/reconnect | PASS, user-reported: disconnecting during capture displayed "Microphone off. Recording discarded." After reconnecting and trying again, the transcript was "Remind me to call Sam tomorrow at 3pm." Whether a page reload was used was not explicitly stated. |
| Full offline workflow | PASS, user-reported October 4 after the dot-time fix: internet was disconnected, the reminder appeared, and Done completed the task. This confirms the reported offline workflow retry beyond the earlier process-scoped socket test. |
| Windows sleep/resume | PASS, user-reported October 4 following the sleep/resume procedure: the reminder appeared once and Done completed the task. Exact delivery latency was not reported. |
| Windows reboot recovery | PASS, user-reported October 4 following the reboot procedure: both tasks remained saved, the pending reminder appeared once, and the snoozed reminder appeared at its saved wake time. This verifies recovery; automatic startup remains outside this result. |
| Physical microphone | PASS, user-reported: “Remind me to call Sam tomorrow at 3 PM” transcribed correctly to an editable draft and the microphone turned off. |
| Real Whisper runtime | Prior milestone evidence: official sample successfully transcribed locally with the installed CPU runtime. Not repeated as a new physical-device test. |

## Reproduce automated checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
pnpm --dir frontend test
pnpm --dir frontend build
```

The acceptance tests use temporary databases. They never edit the normal task database. Frontend tests simulate browser/audio resources and check that microphone tracks close and draft text is preserved.

## Remaining hardware/environment acceptance

- Disconnect the machine from the internet and repeat microphone → transcript → proposal → confirmation and reminder delivery. The scoped socket test above is not a substitute for this.
- Background music caused meaning-changing transcription errors in three reported attempts. Repeat in quiet, then with music at the intended operating volume and microphone distance; noisy-environment voice acceptance remains open.
- Project USB microphone testing remains pending. Bose Bluetooth interruption/reconnection and browser permission denial/restoration passed the reported tests (see above).
- Physical Windows sleep/resume and full OS reboot recovery passed by user report; automatic startup is not configured.

Automatic service startup, Raspberry Pi hardware, Hailo acceleration, kiosk/on-screen keyboard, and speaker output belong to subsequent milestones.

## Physical test procedure

Results must be reported from the real device; leave unperformed checks pending.

1. **Noise:** record a task with its time at normal desk distance with usual background noise. Inspect the transcript without saving. Record whether a retry/edit was necessary.
2. **Reconnect:** start recording, unplug the USB microphone, reconnect, and try another recording. Check interruption feedback, recovery, and microphone shutdown. A built-in microphone cannot establish USB hot-plug behavior.
3. **Permission:** block microphone permission for localhost, tap Talk, verify the error and usable typed input, then restore permission.
4. **Offline:** keep both services running; disable Wi-Fi and unplug Ethernet. Use the local app to record a task named Windows hardware test with an explicit time a few minutes ahead. Review the transcript and proposed schedule, confirm, and wait for the visual reminder. Complete it. Reconnect before reporting results here; the chat itself may require internet.
5. **Sleep:** create a uniquely named test reminder a few minutes ahead, then sleep Windows until after its due time. Resume and return to the dashboard. Expect one pending alert within about six seconds of active polling; complete it. The app cannot display alerts during sleep.
6. **Reboot:** create two uniquely named test tasks with reminders due shortly. Once their alerts appear, snooze one. Record both titles and the snooze wake time. Save other work and reboot. Manually restart both services using the commands below, then open localhost. Verify both tasks survive, the unsnoozed alert appears once, and the snoozed alert stays hidden until its saved wake time (or appears once if already past). Delete only your test tasks after checking.

Automatic Windows startup has not been configured. Needing the manual restart below is expected for this milestone.

After a reboot, open two PowerShell terminals in `D:\Projects\OTD_AI_ASSISTANT`:

```powershell
# Terminal 1: desk service
.\.venv\Scripts\python.exe -m otd_assistant
```

```powershell
# Terminal 2: local AI
.\runtime\llama\llama-server.exe -m models\qwen2.5-1.5b-instruct-q4_k_m.gguf --host 127.0.0.1 --port 8081 -c 8192 -np 1 -ngl 0 --alias otd-qwen
```

Whisper starts on demand; it needs no separate terminal. Open http://127.0.0.1:8000/ after both services are ready.

## Background-music failure details

User-reported October 4: a Telugu song was playing on a phone while the user spoke the English request "Remind me to call Sam tomorrow at 3 p.m." Reported transcripts:

- "Remind me to call sound tomorrow at 3 p.m"
- "Good luck, Sam. Good luck, thank you."
- "Turn me the bell time tomorrow at 3 p.m."

These errors change the intended task, not merely punctuation. The cause has not been isolated: competing vocals, microphone placement/input selection, and recognition-model limitations are possible contributors. This does not establish that the song language itself caused the errors. Transcript editing and task confirmation remain necessary safeguards. Quiet-versus-music comparison under otherwise matched conditions is the next diagnostic check.

## Quiet comparison details

Following the request to pause music and keep microphone placement unchanged, the user reported:

- "I'm going to call Sam tomorrow at 3 p.m."
- "call channel tomorrow at 3 p.m."
- "remind me to call Sam tomorrow at 3 p.m."

Two attempts preserved the key task details; the second changed the intended contact. The first changed the request wording, although the action, contact and schedule were retained. This indicates errors are not confined to the background-music condition; it does not isolate their cause. Next establish the actual input device and placement before changing the speech model.

## Microphone comparison

The user identified the earlier comparison device as the laptop microphone. A subsequent test used a Bose Bluetooth speaker/microphone and produced:

- "Remind me to call Sam tomorrow at 3 p.m."
- "Remind me to call Sam tomorrow at 3 p.m."
- "You mind me to call Sam tomorrow at 3pm?"

All three Bose transcripts retained the intended action, contact, date and time; the third altered the request wording. The user confirmed this Bose test was performed in quiet. This is an improvement over the reported quiet laptop sample, but speaking distance was not supplied, so microphone choice cannot yet be isolated as the cause. The USB microphone remains unverified. Bose Bluetooth disconnect/reconnect passed the user-reported test (see results table). The subsequent Bose background-music sample failed (see below).

## Bose background-music comparison

Following the instruction to repeat the Bose test with the Telugu song playing, the user reported:

- "Remind me to call Stamps tomorrow at 3pm."
- "Remind me to call Sam tomorrow at 3pm."
- "Remind me to call Sam tomorrow at 3K"

Only the second attempt preserved both the intended contact and time. This sample fails recognition acceptance under the tested music condition. The quiet Bose sample retained those details in all three attempts. These small samples do not establish a general accuracy rate or isolate a root cause. Do not silently normalize unknown contact names or ambiguous times to the expected test phrase. Transcript review remains required; use quiet conditions for now.

## Offline workflow defect: dot-separated spoken time

User screenshots showed transcription as "today at 6.50 pm" followed by a missing-time clarification. The parser accepted colon-separated minutes but not dot-separated minutes. Fixed to accept dot-separated minutes with explicit AM/PM and to reject partial matches inside invalid times. Ten regression cases pass; full backend suite now has 101 passing tests. A live Qwen test of the exact sentence returned an October 4, 18:50 Chicago proposal in a temporary database, without saving. Desk service restarted with the fix. Offline reminder delivery remains pending user retest; screenshots alone do not establish machine-wide disconnection or reminder success.

## Dot-time fix retest

After the fix and request to retry the offline workflow, the user reported "it worked now." Record the retry as successful by user report. The response does not explicitly distinguish successful scheduling from the complete internet-disconnected reminder/Done flow; confirm those details before marking machine-wide offline acceptance passed.

## Full offline retest confirmation

The user explicitly confirmed: "internet disconnected. reminder appeared. done completed the task". The full offline workflow is now recorded as PASS by user report, superseding the pending clarification above. Sleep/resume and Windows reboot recovery remain pending.

## Sleep/resume confirmation

Following the physical sleep/resume instructions, the user confirmed "reminder appeared once and done completed the task". Record PASS for reminder recovery and completion, without claiming a measured delivery latency. Full Windows reboot recovery remains pending.

## Windows hardware acceptance status after reboot test

The user confirmed all three reboot checks: both tasks persisted, the pending alert appeared once, and the snoozed alert appeared at its saved wake time. Recovery, fully offline operation, physical microphone permission denial/restoration, and Bose disconnect/reconnect have passed the reported checks. Background-music recognition remains a known failed acceptance condition; quiet Bose recognition preserved key task details in the small three-attempt sample. The project USB microphone remains untested. Do not describe overall noisy-environment voice acceptance as passed.
