"""Administrative commands that must not be reachable over HTTP.

python -m bookshelf.manage promote <username>
python -m bookshelf.manage demote <username>
"""

import argparse
import sys

from bookshelf.auth import service as auth_service
from bookshelf.database import get_connection, init_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bookshelf.manage")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("promote", "demote"):
        cmd = sub.add_parser(name, help=f"{name} a user to/from admin")
        cmd.add_argument("username")
    args = parser.parse_args(argv)

    role = "admin" if args.command == "promote" else "user"
    init_db()
    with get_connection() as conn:
        if not auth_service.set_role(conn, args.username, role):
            print(f"error: no user named {args.username!r}", file=sys.stderr)
            return 1
    print(f"{args.username} is now {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
