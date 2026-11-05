"""Local operator commands. Run with: python -m server.manage."""
import argparse
import getpass
import os
import sqlite3
from pathlib import Path
from .app import ROLES, audit, connect, initialize, set_member


def main():
    p = argparse.ArgumentParser(description='Family Ops local operator tools; never pass passwords as arguments')
    p.add_argument('--db', default=os.environ.get('FAMILYOPS_DB', 'data/familyops.sqlite'))
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('init')
    user = sub.add_parser('user-set', help='Create/update a person; profile disabled unless --enable is explicit')
    user.add_argument('id')
    user.add_argument('--role', choices=sorted(ROLES), required=True)
    user.add_argument('--enable', action='store_true')
    disable = sub.add_parser('disable')
    disable.add_argument('id')
    backup = sub.add_parser('backup')
    backup.add_argument('destination')
    args = p.parse_args()
    os.umask(0o077)
    initialize(args.db)
    if args.command == 'user-set':
        pw = getpass.getpass('New password (12-256 characters): ')
        if pw != getpass.getpass('Confirm password: '):
            p.error('Passwords do not match')
        try:
            set_member(args.db, args.id, args.role, pw, args.enable)
        except ValueError as e:
            p.error(str(e))
        print('Member saved; existing sessions revoked. Enabled:', args.enable)
    elif args.command == 'disable':
        db = connect(args.db)
        try:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM members WHERE id=?', (args.id,)).fetchone():
                p.error('Unknown member')
            db.execute('UPDATE members SET enabled=0 WHERE id=?', (args.id,))
            db.execute('DELETE FROM sessions WHERE member=?', (args.id,))
            audit(db, 'operator', 'disableMember', args.id)
            db.commit()
        finally:
            db.close()
        print('Member disabled and sessions revoked')
    elif args.command == 'backup':
        target = Path(args.destination)
        # Exclusive creation prevents accidental replacement of a previous backup.
        with target.open('xb'):
            pass
        src, dst = connect(args.db), sqlite3.connect(target)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        print('Consistent SQLite backup created:', target)
    else:
        print('Database initialized; no users or default passwords created')


if __name__ == '__main__':
    main()
