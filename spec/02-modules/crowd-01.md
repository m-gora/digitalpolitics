# Questionnaires (Admin Mode)
A questionnaire is a short, ordered set of questions that citizens answer anonymously in the respondent app (crowd-02).

## Structure
- A questionnaire has a title, an optional intro text, 1 to 5 questions, an optional campaign link, a status and a creator (`X-User-Id`).
- **There shall be no more than 5 questions per questionnaire.** The service layer, the UI and a DB constraint (`position BETWEEN 1 AND 5`, unique per questionnaire) all enforce this.
- Question types:
  - `text`: free text, max 500 characters. Voice input is available (crowd-04).
  - `single_choice`: 2 to 8 options.
  - `multiple_choice`: 2 to 8 options.
- Each question has a prompt (max 200 characters) and a `required` flag.
- Limits: title max 100 characters, intro max 500, option label max 80.

## Lifecycle
```
Draft -> Active <-> Closed
```
- **Draft**: fully editable (questions, options, order, campaign link). The admin can open a preview of the respondent app; a preview stores nothing.
- **Active**: questions, options and the campaign link are frozen so that stored answers stay comparable. Title and intro may still change. An Active questionnaire is always collecting (see Campaign link).
- **Closed**: collection stopped. Title, intro and campaign link may be changed; questions and options stay frozen. It can be re-activated if its campaign is Running or it is standalone.
- To change the questions of an Active or Closed questionnaire, the admin duplicates it into a new Draft (same idea as forking in canv-03). Responses are not copied.
- Deletion is only possible while there are no responses. Otherwise the questionnaire is closed.

## Campaign link
- A questionnaire may be linked to at most one campaign. A campaign may have several questionnaires. Standalone questionnaires are allowed.
- Only campaigns in `Draft`, `Review` or `Running` may be linked. Finished, Aborted and Archived campaigns are not offered by the UI and are rejected by the server. The dropdown shows each campaign's status.
- **Activation:** a standalone questionnaire may be activated at any time. A linked questionnaire may only be activated while its campaign is `Running` (canv-05). Starting a campaign does not activate its Draft or Closed questionnaires; a person explicitly activates each questionnaire.
- **Collection window:** `Active` is the sole collection state: an Active questionnaire always accepts responses. When a linked campaign transitions from `Running` to `Finished` or `Aborted`, its Active questionnaires automatically transition to `Closed` and publish `crowd.questionnaire_status_changed`. This is an explicit status change, not a hidden campaign predicate. Archiving also closes any unexpectedly Active questionnaires.
- The campaign link can be changed only while a questionnaire is Draft or Closed, never while Active.
- The campaign detail page lists its linked questionnaires with their response counts.
- The campaign's Data Harvest text is shown read-only in the questionnaire editor as orientation, reminding admins of the legal-basis and retention obligation from canv-02.

## Permissions
- Any authenticated user can create a questionnaire. Read access, including analysis (crowd-05), is global (arch-02).
- Only the creator can edit, activate, close or delete a questionnaire.
- Linking to a campaign requires write access to that campaign's district (arch-02, adr-03).

## Admin UI
- Standard layout (arch-07), German (arch-06).
- The list shows title, status, campaign, response count and creator.
- The detail page shows whether the questionnaire is collecting, the public respondent link and a QR code for it. Activation/reactivation is disabled with an explanation and campaign link when a linked campaign is not Running.

## Events
Status transitions push `crowd.questionnaire_status_changed` (arch-03).
