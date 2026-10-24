#!/usr/bin/env python3
"""Generate the PowerShell loader body from the reviewed shell loader."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    shell = (ROOT / 'bootstrap.sh').read_text(encoding='utf-8')
    body = shell.split("<<'PY'\n", 1)[1].rsplit('\nPY\n', 1)[0]
    path = ROOT / 'bootstrap.ps1'; powershell = path.read_text(encoding='utf-8')
    head, rest = powershell.split("$loader = @'\n", 1)
    _, tail = rest.split("\n'@\n", 1)
    expected = head + "$loader = @'\n" + body + "\n'@\n" + tail
    if args.check:
        if expected != powershell:
            print('PowerShell loader differs; run python scripts/sync-bootstraps.py', file=sys.stderr)
            return 1
        return 0
    path.write_text(expected, encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
