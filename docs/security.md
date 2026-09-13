# Security and privacy

The platform holds student records. This page describes how access is
controlled, what is recorded, and what the deployment does to keep data where it
belongs. To report a vulnerability, see [SECURITY.md](../SECURITY.md).

- [Roles and permissions](#roles-and-permissions)
- [Signing in](#signing-in)
- [The audit log](#the-audit-log)
- [Data handling](#data-handling)
- [Production safeguards](#production-safeguards)

## Roles and permissions

Everything except `/api/health`, `/api/ready` and sign-in requires a signed-in
person. Every route checks its own permission on the server; the interface only
hides what the API would refuse.

| Role | Sees | Can do |
|---|---|---|
| Administrator | everything | everything, plus accounts, the audit log, data import and the general manager |
| Counselor | every student | open and close plans, upload documents, request AI drafts, approve plan proposals, overrule the index |
| Teacher | only students in their own sections | record scores and upload documents for them, request drafts; approves nothing |
| Registrar | students, classes, timetable | open classes and sections; approve those proposals |
| Business office | stockroom and budget; no student records | change stock and budget; approve those proposals |

The full map is `backend/app/auth/permissions.py`. Notes:

- **Teacher scoping.** A teacher account is linked to its sections by
  `teacher_name`, which must match the timetable exactly. A teacher account
  without one sees no students. Requests for students outside scope return
  `404`, so IDs cannot be probed.
- **Modules.** Turning off an optional module (`HR_MODULES`) removes its
  permissions from every role, so its routes, screens, agents and proposals
  close together.
- **Approvals.** Approving an agent's proposal needs the same permission as
  making the change by hand.

## Signing in

**Passwords** are hashed with scrypt and must be at least 12 characters. Five
failed attempts for an email lock it for 15 minutes
(`HR_LOGIN_MAX_FAILURES`, `HR_LOGIN_LOCKOUT_MINUTES`).

**Sessions** are server-side rows behind an `HttpOnly`, `SameSite=Lax` cookie,
marked `Secure` in production. Only a SHA-256 hash of the token is stored.
Sessions expire after `HR_SESSION_HOURS`. Changing a person's role, deactivating
their account or resetting their password ends all their sessions immediately.

**CSRF.** Every state-changing request must carry an `X-Requested-With` header. A
page on another site cannot set one without a CORS preflight, which the API does
not grant. This is a second layer behind the SameSite cookie.

**The school's identity provider.** Set `HR_OIDC_ISSUER`, `HR_OIDC_CLIENT_ID`,
`HR_OIDC_CLIENT_SECRET` and `HR_OIDC_REDIRECT_URI` to use Google Workspace,
Microsoft Entra or any OpenID Connect provider. The backend runs the
authorization-code flow with PKCE, so the browser never handles a token. It
verifies the ID token's signature against the provider's published keys, along
with its issuer, audience, expiry and nonce.
**Signing in never creates an account:** the email must already belong to an
active account. Set `HR_PASSWORD_LOGIN=false` once everyone uses the provider.

**The first administrator** is created on the server, and the rest on the
Admin tab:

```bash
python -m app.cli create-user head@school.edu "Head of School" admin --password
```

## The audit log

The audit log (Admin tab, `GET /api/admin/audit`) records:

- **every change** made through the API, including refused attempts (a `403` is as
  worth knowing about as a `200`)
- **every view of an individual student's** record, documents, study plans, class
  work, timetable or history
- **every sign-in, sign-out and failed sign-in**, with the email tried
- **every data import** that was applied, with its counts

Each entry has the actor's email and role, the action, the record, the result,
the client IP and a request ID. Every API response carries the matching
`X-Request-ID` header. Rows are only ever inserted. **Request bodies are never
logged:** they contain the very records the log protects. Anonymous `401`
requests are not logged, so nobody can fill the table without an account.

Most entries are written by middleware rather than by each route, so a new route
cannot forget to log.

## Data handling

- **Local inference.** The AI features call Ollama on the school's own machine or
  network. No student data is sent to an external AI service.
- **Documents.** Only the extracted text is stored, never the uploaded file.
  Deleting a document deletes everything read from it.
- **Logs.** Application logs name routes by template (`/api/students/{sid}`),
  never the filled-in path, and Caddy's access log drops request URIs, so
  student IDs stay in the audit log and out of log systems.
- **Error reporting.** `HR_SENTRY_DSN` is optional. When set, personal data and
  request bodies are not sent.
- **Caching.** Every API response is `Cache-Control: no-store`, so records do not
  linger in shared browser or proxy caches.
- **Fonts.** The interface loads fonts from Google Fonts. A school that wants no
  third-party requests at all should self-host them and remove those origins
  from the Content Security Policy in `frontend/Caddyfile`.
- **Retention.** Snapshots, audit events and agent transcripts are kept
  indefinitely by default. Set a retention period that fits your school's policy
  and local regulations (for example FERPA in the United States).

## Production safeguards

With `HR_APP_ENV=production`, the API and the worker **refuse to start** if:

- `HR_SECRET_KEY` is the development value or shorter than 32 characters
- the database is SQLite
- `HR_TODAY` pins the clock
- cookies are not secure
- OIDC is half-configured, or password sign-in is off with no OIDC

In production the interactive API docs (`/docs`, `/openapi.json`) are not
served. Caddy adds HSTS, a strict Content Security Policy,
`X-Frame-Options: DENY`, `nosniff`, a same-origin referrer policy and a
permissions policy. The API is reachable only through Caddy.

CI runs `pip-audit` and `npm audit` on every pull request, and Dependabot opens
weekly dependency updates.
