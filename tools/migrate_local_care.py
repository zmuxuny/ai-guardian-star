"""Create/upgrade a local care DB, backing up an existing old schema first.

    python tools/migrate_local_care.py .tmp/care.db

The backup is placed next to the supplied DB, never overwriting another file.
Ship src/migrations/local_care/*.sql together with the Python modules.
"""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.local_care_migrations import migrate_database


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--target-version', type=int, choices=(1, 2))
    args = parser.parse_args(argv)
    try:
        result = migrate_database(args.database, target_version=args.target_version)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(json.dumps({'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({'from_version': result['from_version'], 'to_version': result['to_version'],
                      'backup_file': Path(result['backup_path']).name if result['backup_path'] else None}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
