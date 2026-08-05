"""Account administration from the command line.

    python -m app.manage list
    python -m app.manage promote you@example.com
    python -m app.manage promote them@example.com --role instructor
    python -m app.manage set-password you@example.com
    python -m app.manage create-admin you@example.com

Why this exists: there is no default administrator and no recoverable
password. The first account registered on an empty instance is promoted to
admin (`BOOTSTRAP_FIRST_USER_AS_ADMIN`), and passwords are Argon2id hashes —
by design, nobody can read one back, including whoever runs the server.

So when the admin password is lost, or the bootstrap window has closed, the
only honest routes are to reset the password or promote another account. Doing
that by hand means writing an Argon2 hash into the database with `sqlite3`,
which is exactly the sort of thing that goes wrong quietly. This is the
supported way.

**This is not a privilege bypass.** It requires shell access to the machine and
its database — anyone with that could already do it. It is the same tool every
comparable framework ships (`createsuperuser`, `changepassword`).

Changing a password here revokes every existing session, exactly as the
in-app change does: `tokens_valid_from` moves forward, so outstanding access
tokens are rejected rather than left to expire.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.datetime_utils import utcnow
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import RefreshToken, User


def _session_factory() -> tuple[object, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(settings.DATABASE_URL)
    return engine, async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _find(session: AsyncSession, identifier: str) -> User | None:
    """Look a user up by email or username, so either works."""
    needle = identifier.strip().lower()
    result = await session.execute(
        select(User).where((User.email == needle) | (User.username == needle))
    )
    return result.scalar_one_or_none()


async def _revoke_sessions(session: AsyncSession, user: User) -> None:
    """Sign the account out everywhere, as an in-app password change does."""
    user.tokens_valid_from = utcnow()
    tokens = (
        (await session.execute(select(RefreshToken).where(RefreshToken.user_id == user.id)))
        .scalars()
        .all()
    )
    for token in tokens:
        token.revoked_at = utcnow()


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
async def cmd_list() -> int:
    engine, factory = _session_factory()
    async with factory() as session:
        users = (await session.execute(select(User).order_by(User.created_at))).scalars().all()

        if not users:
            print("No accounts yet.")
            print("The first account you register becomes the administrator.")
        else:
            print(f"{'ROLE':<11} {'EMAIL':<32} {'USERNAME':<18} ACTIVE")
            print("-" * 74)
            for user in users:
                flag = "yes" if user.is_active else "no"
                print(f"{user.role.value:<11} {user.email:<32} {user.username:<18} {flag}")
            admins = [item for item in users if item.role is UserRole.ADMIN]
            if not admins:
                print("\nNo administrator. Promote one:")
                print("  python -m app.manage promote <email>")
    await engine.dispose()  # type: ignore[attr-defined]
    return 0


async def cmd_promote(identifier: str, role_name: str) -> int:
    engine, factory = _session_factory()
    code = 0
    async with factory() as session:
        user = await _find(session, identifier)
        if user is None:
            print(f"No account matches '{identifier}'.", file=sys.stderr)
            code = 1
        else:
            previous = user.role.value
            user.role = UserRole(role_name)
            await session.commit()
            print(f"{user.email}: {previous} → {user.role.value}")
            # The role rides in the database, not the token, so this takes
            # effect on the next request without signing anyone out.
            print("Takes effect immediately; no need to sign in again.")
    await engine.dispose()  # type: ignore[attr-defined]
    return code


async def cmd_set_password(identifier: str, password: str | None) -> int:
    engine, factory = _session_factory()
    code = 0
    async with factory() as session:
        user = await _find(session, identifier)
        if user is None:
            print(f"No account matches '{identifier}'.", file=sys.stderr)
            await engine.dispose()  # type: ignore[attr-defined]
            return 1

        secret = password or _prompt_password()
        if secret is None:
            await engine.dispose()  # type: ignore[attr-defined]
            return 1
        if len(secret) < settings.PASSWORD_MIN_LENGTH:
            print(
                f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.",
                file=sys.stderr,
            )
            await engine.dispose()  # type: ignore[attr-defined]
            return 1

        user.hashed_password = hash_password(secret)
        await _revoke_sessions(session, user)
        await session.commit()
        print(f"Password updated for {user.email}.")
        print("Every existing session for that account has been signed out.")
    await engine.dispose()  # type: ignore[attr-defined]
    return code


async def cmd_create_admin(email: str, username: str | None, password: str | None) -> int:
    engine, factory = _session_factory()
    async with factory() as session:
        existing = await _find(session, email)
        if existing is not None:
            print(f"{existing.email} already exists — promoting instead.", file=sys.stderr)
            await engine.dispose()  # type: ignore[attr-defined]
            return await cmd_promote(email, "admin")

        secret = password or _prompt_password()
        if secret is None:
            await engine.dispose()  # type: ignore[attr-defined]
            return 1
        if len(secret) < settings.PASSWORD_MIN_LENGTH:
            print(
                f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters.",
                file=sys.stderr,
            )
            await engine.dispose()  # type: ignore[attr-defined]
            return 1

        user = User(
            email=email.strip().lower(),
            username=(username or email.split("@")[0]).strip().lower(),
            hashed_password=hash_password(secret),
            full_name="Administrator",
            role=UserRole.ADMIN,
            is_active=True,
            # Created out of band by someone with server access, so there is
            # nobody to send a verification mail to and nothing to prove.
            is_email_verified=True,
        )
        session.add(user)
        await session.commit()
        print(f"Administrator created: {user.email} (username {user.username})")
    await engine.dispose()  # type: ignore[attr-defined]
    return 0


def _prompt_password() -> str | None:
    """Read a password twice, without echoing it."""
    if not sys.stdin.isatty():
        print("No terminal for a password prompt — pass --password.", file=sys.stderr)
        return None
    first = getpass.getpass("New password: ")
    second = getpass.getpass("Repeat: ")
    if first != second:
        print("Passwords do not match.", file=sys.stderr)
        return None
    return first


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.manage",
        description="Account administration.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python -m app.manage list\n"
            "  python -m app.manage promote you@example.com\n"
            "  python -m app.manage promote them@example.com --role instructor\n"
            "  python -m app.manage set-password you@example.com\n"
            "  python -m app.manage create-admin you@example.com\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show every account and its role")

    promote = sub.add_parser("promote", help="change an account's role")
    promote.add_argument("identifier", help="email or username")
    promote.add_argument(
        "--role", default="admin", choices=[role.value for role in UserRole], help="target role"
    )

    reset = sub.add_parser("set-password", help="set an account's password")
    reset.add_argument("identifier", help="email or username")
    reset.add_argument(
        "--password",
        help="the new password (omit to be prompted, which keeps it out of your shell history)",
    )

    create = sub.add_parser("create-admin", help="create a new administrator account")
    create.add_argument("email")
    create.add_argument("--username", help="defaults to the part before the @")
    create.add_argument("--password", help="omit to be prompted")

    args = parser.parse_args(argv)

    if args.command == "list":
        return asyncio.run(cmd_list())
    if args.command == "promote":
        return asyncio.run(cmd_promote(args.identifier, args.role))
    if args.command == "set-password":
        return asyncio.run(cmd_set_password(args.identifier, args.password))
    if args.command == "create-admin":
        return asyncio.run(cmd_create_admin(args.email, args.username, args.password))
    return 1  # pragma: no cover - argparse rejects anything else


if __name__ == "__main__":
    raise SystemExit(main())
