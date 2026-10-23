# Responses, Privacy and Abuse Protection

## Stored per response
- Client UUID (idempotency key) and the questionnaire id.
- Location as a PostGIS `geography(Point, 4326)` plus `accuracy_m` (adr-08).
- `captured_at` (client time) and `received_at` (server time).
- Per answer: the question id, the scrubbed text or the selected option ids, and a `via_voice` flag.

**Not stored:** any identity, IP address, user agent, device id, audio, or unscrubbed text. IPs are held transiently in memory for rate limiting only.

## Privacy (arch-04)
- **PII in this module** means names, email addresses, phone numbers, IBANs, URLs and postal addresses (street plus house number, or street plus postal code) appearing in free text.
- **Separation:** responses contain tracking data (location, answers) and no identifiers. Nothing links a response to a person or device.
- **Coordinate precision:** latitude and longitude are rounded server-side to 4 decimals (about 10 m) before storage. Exact coordinates never reach the database.
- **Scrubbing:** a deterministic server-side regex scrubber runs on all free text before storage and replaces matches with placeholders such as `[E-Mail]`, `[Telefon]`, `[Adresse]`.
  - It handles `+49`, `0049` and `0xx` phone formats and German street suffixes (`-str.`, `-straße`, `-weg`, `-platz`, ...).
  - **Known limitation:** person names are not detected. The start screen and the text input tell respondents not to give names. See adr-07.
- **Privacy notice**, shown before the first answer and not skippable: answers are anonymous, the location is saved with the answer, and voice input (when available) is sent to OpenAI for transcription. Audio is not stored by this application; OpenAI may retain it for up to 30 days for abuse monitoring. Final German wording is to be reviewed by the data-protection owner.
- **Retention and legal basis** are deferred, consistent with canv-02. Until specified, no automatic deletion exists.

## Validation on ingest
- The server validates every answer against the questionnaire definition: question ids, option ids, types, required questions, max lengths and the 2-8 option rules.
- A duplicate client UUID returns the original result (idempotent).
- A response is accepted while the questionnaire is `Active`. After it transitions to `Closed`, delayed offline sync is accepted only if `captured_at` falls between `collection_started_at` and `collection_stopped_at` (inclusive). This supports buffered responses without accepting submissions captured after collection ended.
- A response for a questionnaire that no longer exists, is still a Draft, or was captured outside its collection window is rejected with 410. The client then discards it.

## Abuse protection (prototype scale)
- In-memory per-IP rate limits, using the IP from the trusted proxy header: responses 30 per minute, transcription 10 per minute.
- Request body limit: 32 KB for responses.
- Spoofed GPS and bot submissions cannot be fully prevented. The token is a weak secret and closing a questionnaire is the remedy. This is a known limitation.

## Events
`crowd.response_received` carries the questionnaire id and the new total count. It carries no location or content (arch-03).
