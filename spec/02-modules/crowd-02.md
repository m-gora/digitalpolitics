# Respondent App (User Mode)
A fullscreen, kiosk-style app for citizens. Its only function is answering one questionnaire.

## Access
- Route: `/crowd/r/{token}`. The token is random and unguessable (at least 16 characters), created together with the questionnaire.
- The routes under `/crowd/r/` and the response and transcription endpoints are **public**. They never read `X-User-Id` (see adr-07, arch-01).
- The respondent app has its own minimal base template: no navigation, no logo link, no dev bar.
- If the questionnaire is not collectable (crowd-01), the app shows a neutral "Diese Umfrage ist derzeit nicht aktiv" screen.

## Flow
1. **Start screen**: title, intro, privacy notice (crowd-03) and one "Start" button. On tap the app requests fullscreen (needs a user gesture) and the geolocation permission, so both prompts happen before the first answer.
2. **Question screens**: one question per screen with a progress indicator ("2 von 4"), large touch targets and back/next controls. Required questions block "Weiter" until answered.
3. **Submit**: the response is stored locally first (arch-05) and then synced. The app shows a short thank-you screen.
4. **Auto-reset**: after about 5 seconds the app returns to the start screen with all state cleared, so the device can be handed to the next person.

## Fullscreen
The page has no links or controls other than answering and moving between questions. Leaving the app is done via the browser or OS. The manifest sets `display: fullscreen`.

## GPS
- A location is required for submission. Without one, no response can be submitted: denied permission, timeout and unusable fixes all block.
- If permission is denied or no fix is available, the app shows a blocking screen explaining what to enable, with a retry button and no skip.
- The fix is refreshed at submit time. If that fails, the last fix is used if it is at most 5 minutes old.
- A fix with accuracy worse than 100 m is rejected and retried.
- The location sent is `{lat, lon, accuracy_m}` (stored per crowd-03).

## Offline (arch-05)
- The questionnaire page is cached by a service worker, so a questionnaire opened once online works without a connection. GPS and answering work offline.
- The service worker is served from `/crowd/r/sw.js` with scope `/crowd/r/`.
- Completed responses are written to **IndexedDB**, each with a client-generated UUID that makes sync idempotent.
- Sync is attempted after each submit, on the `online` event, at app start, and via Background Sync where available.
- Voice input needs a connection. Offline, the microphone button is disabled; typing still works.
- A small, non-interactive indicator shows the number of unsent responses.

## Accessibility (pragmatic baseline)
- Touch targets are at least 48x48 px.
- All controls are labelled and keyboard and screen-reader operable.
- Contrast and typography come from arch-07 (Public Sans, brand colors).
- No formal WCAG audit in v1. Whether BFSG applies is an open legal question (arch-06).
