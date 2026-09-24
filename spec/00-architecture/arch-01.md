# Forward Auth
The application shall use the forward auth proxy pattern.
The following headers shall be used to send auth information to the backend:
- X-User-Id
- X-User-Roles
- X-District-Scopes

These headers are only trustworthy when received from the trusted forward-auth proxy network. The application shall be deployed so that clients can never reach it directly and set these headers themselves.

See adr-03 for the exact format and resolution rules of `X-District-Scopes`.