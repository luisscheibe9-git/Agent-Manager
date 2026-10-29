# Simple black inbox — verification report

Date: 2026-10-29. Branch: codex/simple-black. Base:1d95cfd.
Source: C:/Users/Luis/.codex/worktrees/simple-black/agent manager.
Preview: http://127.0.0.1:8878 (synthetic data only).

## Automated checks
- 26 distinct Python regression tests pass: `python -m unittest -q test_inbox test_dashboard test_black_launcher`.
- `node --check web/app.js` and `git diff --check` pass.
- Coverage includes durable catalog recovery, lifecycle/pending async questions, reminder delay/dedup/retry, read/pin/archive persistence, source metadata outage, hook observer preservation, concurrent requests, strict HTTP routes/origins and launcher data-directory selection.

## Actual computer-use checks
Used the in-app browser, real buttons/fields, and screenshots. Mutation tests used isolated8chat fixtures under ignored notes/qa-data, never Luis's production read marks.

| Feature | Observed result |
| --- | --- |
| Original black concept | Compact always-dark single list, source-color left borders, top controls; no dashboard sidebar or split inspector. |
| Live working/needs/completion | Appended realistic provider events. Same chat updated needs→working→unread completion without reload; working background green, needs-input red. |
| Live token usage | Expanded Details remained open while total changed29,200→40,000; context17,000/200,000 displayed. |
| Read/unread | Mark done changes finished chat toRead. Marking read on a pending question retains Needs your input. |
| Pins | Pin moves row toPinned; pin andRead state survive page reload and process restart. |
| Search | Search narrows titles; no-match state appears; Escape clears search. Unicode/HTML-looking titles remain text, with0injected inline script nodes. |
| Projects/grouping | Atlas filter returns4saved chats including collapsed settled row; unread filter narrows to2. Group preference saves and survives restart. |
| Mark all read | Finished unread chats disappear from unread filter; pending question remains and badge stays1. |
| Inline previews/details | Details shows pending-input explanation, token breakdown and on-demand Git context. No separate dashboard panel. |
| Git context | Current branch andREADME.md +1/−0 verified. Found/fixed frontend bug treating Git count strings as unavailable numbers. |
| PR context | Disposable QA project temporarily referenced public pingdotgg/t3code PR27030. UI displayed title,OPEN state and exact verified URL. No PR created or changed. Fixture restored tomaster/no remote. |
| Settings | Reminder enable,60second delay and14day settled age saved and reopened with the same values. Dialog focus and390px fit verified. |
| Notification request | Test notification button succeeded. Timed reminder persisted notified=1 after delay, including after restart. Windows toast visibility was not independently observed. |
| Settled | Collapsed saved chat expands and remains accessible. |
| Responsive layout |390x844 page and dialog have no horizontal overflow. |

## Process/API checks
- Graceful restart changed QA server PID25028→7248 and retained8chats,2pins,60second reminder,14day settled threshold and grouping preference.
- Graceful quit produced visible offline banner with all8loaded rows retained; relaunch reconnected automatically without page reload.
- Launcher resolves primary data toD:/agent manager from the separate branch checkout. Explicit QA data override wins. Separate ignored browser profile prevents borrowing the blue app's browser state.

## Screenshot evidence
- black-overview.jpg
- black-working.jpg
- black-needs-input.jpg
- black-live-completed.jpg
- black-context-pr.jpg
- black-settings.jpg
- black-mobile.jpg
- black-offline.jpg

## Verification limits / pending user approval
- Source-specific deep-link URL targets were inspected. Launching real chats/new chats in Claude/Codex was not automated, because that would leave the isolated fixture and operate the agent apps. A user smoke check remains for installed-app handoff.
- OS tray/taskbar badge pixels and Windows toast visibility were not independently screenshot-verified. Backend unread counts, running QA tray, notification requests and persisted reminder markers were verified.
- A real Windows reboot remains untested.
- Production8765still runs blue. Automatic approval review rejected the attempted switch toblack with only 'blocked by policy'; the command did not execute. Explicit activation/startup and commit approval are pending.
- No parent-project code commit/push was made. Blue/cloud work remains preserved and paused inD:/agent manager onmain.
