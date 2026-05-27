"""CLI to bootstrap a user. Use this once to create the initial admin —
or any time the app needs a new user before SSO/registration ships.

Usage
-----
    cd app/backend
    TM_DATABASE_URL_SYNC=postgresql+psycopg2://tm:tm@localhost:5435/tm \\
    ../.venv/bin/python -m scripts.create_user \\
        --email admin@example.com \\
        --name "Francis L" \\
        --role admin \\
        --password 'sup3rsekret!password'

If --password is omitted you'll be prompted interactively (preferred —
the password doesn't end up in shell history).

Re-running with an existing email updates the user (rotates password,
changes role). Always bumps `token_version` so any outstanding sessions
are invalidated.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.auth import hash_password
from api.db.models import User, UserRole
from api.settings import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update a user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument(
        "--role",
        choices=[r.value for r in UserRole],
        default=UserRole.viewer.value,
        help="One of admin / editor / viewer (default: viewer)",
    )
    parser.add_argument(
        "--password",
        default=None,
        help="Plaintext password. Omit to be prompted interactively.",
    )
    args = parser.parse_args()

    email = args.email.strip().lower()
    if args.password is None:
        pw = getpass.getpass(f"Password for {email}: ")
        pw2 = getpass.getpass("Confirm: ")
        if pw != pw2:
            sys.exit("Passwords don't match")
    else:
        pw = args.password

    if len(pw) < 12:
        sys.exit("Password must be at least 12 characters")

    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    with Session() as s:
        existing = s.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if existing is not None:
            existing.password_hash = hash_password(pw)
            existing.name = args.name
            existing.role = UserRole(args.role)
            existing.is_active = True
            existing.token_version += 1  # invalidate any outstanding sessions
            s.add(existing)
            action = "updated"
            uid = existing.id
        else:
            user = User(
                email=email,
                password_hash=hash_password(pw),
                name=args.name,
                role=UserRole(args.role),
                is_active=True,
                token_version=0,
            )
            s.add(user)
            s.flush()
            action = "created"
            uid = user.id
        s.commit()

    print(f"{action} user {email} (role={args.role}) id={uid}")


if __name__ == "__main__":
    main()
