# Local milestone verification — 2026-10-28

23 distinct Python regression tests pass (`python -m unittest -q test_inbox test_dashboard`).
JavaScript syntax check passes (`node --check web/app.js`).

## Automated coverage
- Persist catalog, pins and read marks into a fresh process with source logs unavailable; retain old pinned chats and recover corrupt JSON from backup.
- Current Codex text, titles/folder metadata, canonical IDs, final vs progress text, async questions, long-running turns, prior-boot interrupted work.
- Claude legacy/Store metadata and saved deep links; tolerate incomplete sources without erasing previews.
- Archive/restore; respect source archives during metadata outages, then recognize explicit unarchive.
- Persist validated preferences; reject invalid settings and missing IDs.
- Reminder delays, once-per-activity deduplication, disabled/archive/read exclusions and retry after notification failure.
- Out-of-order hook queue; idempotent installer preserving other settings/observers, including mixed hook groups.
- 60 concurrent state/pin/read operations; 300 saved chats and unavailable project folders.
- HTTP routes/assets, origin restrictions, malformed request types and traversal rejection.

## Computer-use checks actually performed
Used the Windows computer-use skill (`@oai/sky`) on the native QA Chrome app and browser controls on an isolated instance at localhost:8877. Data is synthetic under ignored `notes/qa-data`; real read marks were not used for destructive tests.

- Green Working and red Needs input rows; Needs filter returns one waiting chat.
- Selected chat shows token breakdown and preview; marking read does not dismiss a pending question.
- Git context reads the fixture repository's actual `master` branch and README +1 change; reports absent PR without inventing one.
- Unread filter changes after marking done; pin/unpin, archive, restore and project counts update.
- Search: empty result, Unicode, and HTML-looking title rendered as text with zero injected script nodes.
- Command palette opens via button and F2; filtering and Enter select a different chat. Arrow-key navigation works.
- Grouping toggle and settled section; preferences save and reload.
- Mobile 390×844 layout has no horizontal overflow; back-to-list and projects drawer work. Temporary viewport override reset afterwards.
- Test notification API succeeds. Actual timed reminders sent once for both eligible fixture activities; persisted notified markers remain unchanged after restart.
- Settings Restart app produces a new server PID (33188 → 29068), preserving 8 chats, 2 pins, 60-second delay and notification history.
- Settings Quit app stops its server. Browser retains the last list, displays a reconnect warning. Relaunch restores the service.
- Export downloads `agent-manager-backup.json` (8 synthetic chats) to Downloads.

Screenshots: `notes/screenshots/local-dashboard.png`, `notes/screenshots/offline-retained-list.png`.

## Limits / remaining checks
- A real Windows reboot has not been performed. Startup shortcut and target were inspected and launched; process restart persistence was tested.
- Single-letter key injection through the automation tools did not emit DOM keydown events. j/k/e/p/a are implemented and case-normalized, but physical single-letter keyboard checks remain manual; Arrow keys/F2/Enter were verified through actual control input.
- Source-app deep-link IDs were checked. No new agent prompts were sent; Codex desktop UI automation is excluded by the computer-use skill.
- OS Focus Assist/notification suppression was not changed. Notification delivery requests succeed; visibility depends on Windows notification settings.
- Live Claude hooks will be exercised as new Claude turns run. Installer/queue/bridge logic tested with fixtures; no synthetic prompts were sent to real agents.
- The older production Chat Inbox process at port8765 must be quit by Luis before the new build takes over. It lacks a graceful control endpoint; direct stop was blocked by automatic approval review. QA app remains separate at8877.
- Cloud implementation is the next milestone and is not covered by this report yet.
