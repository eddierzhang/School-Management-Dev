"""Administrative commands, for the server's shell.

    python -m app.cli create-user EMAIL "NAME" ROLE [--teacher-name NAME] [--password]
    python -m app.cli set-password EMAIL
    python -m app.cli deactivate EMAIL

The first administrator of a new deployment is made here; after that, accounts
are managed from the Admin tab. `--password` prompts for one; without it the
account can only sign in through the school's identity provider.
"""
from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func, select

from .auth.passwords import hash_password, password_problem
from .auth.permissions import ROLES
from .auth.sessions import revoke_all
from .db import SessionLocal
from .models import User


def _ask_password() -> str:
    while True:
        pw = getpass.getpass("Password: ")
        if problem := password_problem(pw):
            print(problem)
            continue
        if getpass.getpass("Again: ") != pw:
            print("Those did not match.")
            continue
        return pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create-user")
    c.add_argument("email")
    c.add_argument("name")
    c.add_argument("role", choices=ROLES)
    c.add_argument("--teacher-name")
    c.add_argument("--password", action="store_true", help="prompt for a password")
    p = sub.add_parser("set-password")
    p.add_argument("email")
    d = sub.add_parser("deactivate")
    d.add_argument("email")
    args = ap.parse_args(argv)

    with SessionLocal() as db:
        email = args.email.strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if args.cmd == "create-user":
            if user is not None:
                print(f"{email} already has an account.", file=sys.stderr)
                return 1
            if args.role == "teacher" and not args.teacher_name:
                print("A teacher account needs --teacher-name, exactly as on the timetable.", file=sys.stderr)
                return 1
            db.add(User(email=email, name=args.name, role=args.role, active=True,
                        teacher_name=args.teacher_name if args.role == "teacher" else None,
                        password_hash=hash_password(_ask_password()) if args.password else None))
            db.commit()
            print(f"Created {args.role} account for {email}.")
            return 0
        if user is None:
            print(f"No account for {email}.", file=sys.stderr)
            return 1
        if args.cmd == "set-password":
            user.password_hash = hash_password(_ask_password())
        else:
            user.active = False
        revoke_all(db, user.id)
        db.commit()
        print("Done. Existing sessions for that account were ended.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
