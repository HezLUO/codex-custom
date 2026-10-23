#!/usr/bin/env python3
"""Install/remove only an owned launcher shim; never replace an existing command."""
import argparse
import os
from pathlib import Path
import shlex
import sys

ROOT = Path(__file__).resolve().parents[1]


def shim():
    return '#!/bin/sh\n# codex-custom source launcher\nexport CODEX_CUSTOM_BUILD_FROM_SOURCE=1\nexec ' + shlex.quote(str(ROOT / 'codex-custom')) + ' "$@"\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--uninstall', action='store_true')
    args = parser.parse_args()
    destination = args.bin_dir.expanduser().absolute() / 'codex-custom'
    expected = shim()
    exists = os.path.lexists(destination)
    owned = exists and not destination.is_symlink() and destination.is_file() and destination.read_text() == expected
    if args.uninstall:
        if not exists:
            return
        if not owned:
            raise RuntimeError('Refusing to remove a launcher not owned by this checkout')
        destination.unlink()
        print('Removed launcher; local builds and caches retained.')
        return
    if exists:
        if owned:
            print('Launcher already installed.')
            return
        raise RuntimeError('Destination exists; choose another --bin-dir to preserve it')
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create also protects against a destination appearing after the check.
    with destination.open('x') as stream:
        stream.write(expected)
    destination.chmod(0o755)
    print('Launcher installed. Keep this checkout at its current location and add the bin directory to PATH.')


if __name__ == '__main__':
    try:
        main()
    except (OSError, RuntimeError, UnicodeError) as exc:
        print(f'Installation stopped: {exc}', file=sys.stderr)
        sys.exit(1)
