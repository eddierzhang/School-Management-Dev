"""Accounts, sessions, roles and what each role may see and do.

    passwords.py    hashing (scrypt, from the standard library)
    permissions.py  roles → permissions, and which permission each agent and proposal needs
    sessions.py     the session cookie and the rows behind it
    deps.py         FastAPI dependencies: the signed-in person, and permission checks
    scope.py        which students and classes a teacher may see
    oidc.py         sign-in through the school's identity provider
"""
