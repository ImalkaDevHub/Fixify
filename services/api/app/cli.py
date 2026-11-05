"""Administrative commands.

python -m app.cli assign-orphans --email you@example.com
    Give every project that has no owner (created before authentication existed) to the
    account with that email address. Nothing is deleted.
"""

import argparse
import asyncio
import sys

from app.db.session import SessionFactory
from app.repositories import project as project_repository
from app.repositories import user as user_repository
from app.services.auth import normalize_email


async def assign_orphans(email: str) -> int:
    async with SessionFactory() as session:
        user = await user_repository.get_user_by_email(session, normalize_email(email))
        if user is None:
            print(f"No account with email {email!r}. Register it first.", file=sys.stderr)
            return 1
        count = await project_repository.assign_orphans(session, user.id)
    print(f"Assigned {count} project(s) to {user.email}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    orphans = commands.add_parser("assign-orphans", help="Assign ownerless projects to a user.")
    orphans.add_argument("--email", required=True)
    args = parser.parse_args(argv)
    if args.command == "assign-orphans":
        return asyncio.run(assign_orphans(args.email), loop_factory=asyncio.SelectorEventLoop)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
