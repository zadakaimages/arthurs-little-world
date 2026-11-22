"""Import an existing Arthur SQLite save without overwriting either world.

Usage: python3 import_save.py /path/to/old/arthur.sqlite3
The destination is arthur.sqlite3 beside this script. Start server.py afterwards
so its migration can update positions and movement fields on the imported copy.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sqlite3
import tempfile

ROOT = Path(__file__).resolve().parent


def import_save(source_path, destination=None):
    """Copy a consistent SQLite snapshot, refusing an existing destination.

    The optional destination is for isolated tests. The command-line interface
    always imports into this game's folder. No source row is modified, and all
    tables—not just the currently recognized state fields—are preserved.
    """
    source = Path(source_path).expanduser().resolve(strict=True)
    target = Path(destination) if destination is not None else ROOT / 'arthur.sqlite3'
    target = target.expanduser().absolute()
    if target.exists() or target.is_symlink():
        raise FileExistsError(f'Destination already exists: {target}. Use a fresh game folder; no file was overwritten.')
    if not source.is_file():
        raise ValueError(f'Source is not a file: {source}')
    if not target.parent.is_dir():
        raise ValueError(f'Destination folder does not exist: {target.parent}')
    # The temporary database is on the destination filesystem. A hard link
    # publishes it atomically and fails if another process creates the save first.
    descriptor, temporary_name = tempfile.mkstemp(prefix='.arthur-import-', suffix='.sqlite3', dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    reader = writer = None
    try:
        reader = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True, timeout=15)
        writer = sqlite3.connect(temporary, timeout=15)
        reader.backup(writer)
        if writer.execute('PRAGMA quick_check').fetchone() != ('ok',):
            raise ValueError('The source database failed its SQLite integrity check.')
        try:
            row = writer.execute("SELECT value FROM kv WHERE key='state'").fetchone()
            state = json.loads(row[0]) if row else None
        except (sqlite3.DatabaseError, ValueError, TypeError) as error:
            raise ValueError('The source does not contain a readable Arthur world state.') from error
        if not isinstance(state, dict) or 'x' not in state or 'y' not in state:
            raise ValueError('The source does not contain an Arthur world state.')
        # Finish with a single, self-contained save; source WAL data was included
        # by backup(), unlike copying just a live main database file.
        writer.execute('PRAGMA journal_mode=DELETE')
        writer.close(); writer = None
        reader.close(); reader = None
        os.link(temporary, target)
        return target
    finally:
        if writer is not None:writer.close()
        if reader is not None:reader.close()
        temporary.unlink(missing_ok=True)
        for suffix in ('-wal', '-shm', '-journal'):
            temporary.with_name(temporary.name + suffix).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='Import an existing Arthur save into this game folder without overwriting a save.')
    parser.add_argument('source', help='Path to the previous arthur.sqlite3 file')
    args = parser.parse_args()
    try:
        destination = import_save(args.source)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f'Import failed: {error}\nThe source save was not changed.\n')
    print(f'Imported to {destination}')
    print('The source save was not changed. Start this version with: python3 server.py')


if __name__ == '__main__':
    main()
