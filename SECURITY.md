# Security policy

Halverson Ridge Student Support is built to hold student records, so security
reports are taken seriously.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.** Report it privately
through GitHub's
[private vulnerability reporting](https://github.com/eddierzhang/School-Management-Dev/security/advisories/new)
for this repository.

Include:

- what the vulnerability is and what an attacker could do with it
- the version or commit affected
- steps to reproduce, or a proof of concept
- any suggested fix

You should receive an acknowledgement within five working days. Once a fix is
ready it will be released, and the report credited if you wish.

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | yes |
| < 1.0 | no |

## Scope

In scope: the backend API, the web interface, authentication and authorization,
the audit log, the data import, and the deployment configuration in this
repository.

Out of scope: the `demo/` registrar console prototype, which has no accounts by
design, and weaknesses that require an administrator to act against their own
school.

## Deploying securely

How access control, sign-in, auditing and data handling work, and what a
production deployment must configure, is described in
[docs/security.md](docs/security.md) and
[docs/deployment.md](docs/deployment.md#checklist).
