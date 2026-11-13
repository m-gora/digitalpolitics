# ADR 07: Voice Transcription and the Anonymous Public Surface

> Re-recorded during the transcription migration: voice transcription now uses
> **Gemini** (via `google-genai`) with `GOOGLE_API_KEY` and
> `GOOGLE_TRANSCRIBE_MODEL` (default `gemini-3.5-flash-lite`) instead of OpenAI
> `gpt-4o-transcribe`. The privacy reasoning — transcription only, audio never
> stored, narrow exception to adr-04 — is unchanged.

## Context
The respondent app (crowd-02) must be reachable without authentication, and voice input (crowd-04) sends citizen audio to an external provider. adr-04 states that no citizen data is submitted to external AI services, and arch-01 assumes all requests carry forward-auth headers.

## Decision
- A small, explicit allow-list of public paths (`/crowd/r/*`, `/crowd/api/r/*`) bypasses forward-auth at the proxy and never reads identity headers. All other paths keep requiring authentication.
- Voice audio is sent to Gemini through the backend only, and is never stored.
- This is a **narrow exception to adr-04**: audio of citizen answers may be sent for transcription only. Questionnaire answers, transcripts and locations are never sent to any AI provider.
- PII scrubbing of stored text (crowd-03) is a deterministic regex scrubber. Person names are not detected; this is an accepted v1 limitation, mitigated by on-screen hints.

## Consequences
- Google's API-side handling of the audio (retention, possible training use per the applicable Google terms) must be reviewed by the data-protection owner; the privacy notice must reflect it.
- Spoken names and addresses reach Gemini before scrubbing. Scrubbing protects only what is stored.
- The anonymous endpoints are an abuse and cost surface, mitigated only by prototype-scale rate limits (crowd-03).
- The deployment must configure the proxy allow-list. Locally, the app requires no headers on these routes.
