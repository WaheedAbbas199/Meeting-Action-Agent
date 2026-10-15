# Troubleshooting

| Symptom | Cause / fix |
|---|---|
| App exits: “JWT_SECRET must be set…” | Production needs a 32+ char secret. `openssl rand -hex 32` |
| Meeting stays “Queued” | The worker is not running (`RUN_WORKER=false`, or `APP_ENV=test`). Start the app normally |
| Meeting “Failed: …” | Read the message; fix the cause (e.g. empty transcript, provider key) and press *Retry processing* |
| Audio upload says speech-to-text isn’t configured | Set `STT_PROVIDER=gemini` + `GEMINI_API_KEY`, or paste/upload a text transcript |
| Cannot enable Email/WhatsApp in Settings | Provider is `disabled` or credentials incomplete; the message states what is missing |
| Follow-up stays “Scheduled” | Quiet hours or the hourly limit; it is sent automatically afterwards |
| Follow-up “Failed: not authorized/opted in” | The contact lacks consent; fix it in *Settings → Contacts* and re-submit |
| “This approval has expired” | Approvals expire (default 24 h). Submit the follow-up again |
| Every extraction looks shallow | The default extractor is rule-based. Use `LLM_PROVIDER=gemini` |
| Memory search finds nothing | Retrieval is lexical; use words that appear in the meeting |
| Playwright can’t find a browser | `python -m playwright install chromium` (or set `PLAYWRIGHT_BROWSERS_PATH`) |
| Console shows CSP errors after you edit the UI | Inline `style=` attributes and inline scripts are blocked by design; use classes / `data-*` + `hydrate()` |
