#!/usr/bin/env python3
"""Audit the candidate index and every object reachable from local refs; redact matches."""
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_FILES = {
    '.github/workflows/verify-windows.yml', 'scripts/reuse-windows-candidate.py',
    '.gitattributes',
    'scripts/native-license-sources.json', 'docs/NATIVE-LICENSE-SOURCES.md',
    'scripts/privacy-diagnostic-cert.pem',
    'scripts/sync-bootstraps.py', 'tests/test_platform_build.py',
    '.github/workflows/build-platforms.yml', 'bootstrap.ps1', 'scripts/build-platform.py',
    'scripts/accept-platform.py', 'tests/test_platform_support.py', 'tests/test_platform_commands.py',
    'docs/adr/0002-native-platform-candidates.md',
    'bootstrap.sh', 'bootstrap.py', 'tests/test_download.py', '.gitignore', 'LICENSE', 'NOTICE', 'README.md', 'codex-custom',
    'update-codex-custom.py', 'patches/codex-0.164.0-context-details.patch',
    'scripts/install.py', 'scripts/install-source.py', 'scripts/precompiled.py', 'tests/test_precompiled.py', 'scripts/audit-release.py', 'scripts/release_artifact.py',
    'tests/test_release_artifact.py', 'docs/PRECOMPILED-FORMAT.md',
    'tests/test_updater.py', 'tests/test_install.py',
    'docs/MAINTENANCE.md', 'docs/VALIDATION.md', 'docs/RELEASE.md',
    'docs/INSTALLATION-RESEARCH.md', 'docs/adr/0001-precompiled-installation.md',
    'AGENTS.md', 'docs/agents/issue-tracker.md',
    'docs/agents/triage-labels.md', 'docs/agents/domain.md',
}
# Report only rule labels and object IDs, never matching content.
RULES = {
    'personal-home-path': rb'/(?:Users|home)/[^\s/<>"\x27]+',
    'windows-home-path': rb'(?i)[a-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\\/\x00<>"\x27]+',
    'machine-temporary-path': rb'/(?:private/)?var/folders/[^\s]+',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential': rb'(?i)(?:sk-[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,}|AKIA[A-Z0-9]{16}|Bearer\s+[a-z0-9._-]{20,})',
    'session-identifier': rb'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b',
}
IDENTITY = re.compile(rb'^(?:author|committer|tagger) Codex Custom contributors <contributors@example.invalid> \d+ [+-]\d{4}$')


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def inspect(data, label):
    issues = []
    for rule, pattern in RULES.items():
        if re.search(pattern, data):
            issues.append(f'{label}: {rule}')
    if b'\x00' in data:
        issues.append(f'{label}: unexpected binary content')
    return issues


def main():
    issues = []
    entries = git('ls-files', '--stage', '-z').split(b'\0')
    names = set()
    for entry in filter(None, entries):
        metadata, name = entry.split(b'\t', 1)
        mode, oid, stage = metadata.split()
        relative = name.decode()
        names.add(relative)
        if relative not in PUBLIC_FILES or mode not in (b'100644', b'100755') or stage != b'0':
            issues.append('index: unexpected path, mode or conflict')
        issues += inspect(git('cat-file', 'blob', oid.decode()), 'index blob ' + oid.decode())
        disk = ROOT / relative
        if disk.is_symlink() or not disk.is_file() or disk.read_bytes() != git('cat-file', 'blob', oid.decode()):
            issues.append('worktree differs from candidate index')
    if names != PUBLIC_FILES:
        issues.append('index: candidate file set differs from allowlist')
    if git('ls-files', '--others', '--exclude-standard', '-z'):
        issues.append('worktree: untracked files need review')
    objects = git('rev-list', '--objects', '--all').splitlines()
    for record in objects:
        oid = record.split(b' ', 1)[0].decode()
        kind = git('cat-file', '-t', oid).strip()
        if kind in (b'blob', b'commit', b'tag'):
            data = git('cat-file', kind.decode(), oid)
            issues += inspect(data, 'history object ' + oid)
            if kind in (b'commit', b'tag'):
                for line in data.split(b'\n\n', 1)[0].splitlines():
                    if line.startswith((b'author ', b'committer ', b'tagger ')) and not IDENTITY.fullmatch(line):
                        issues.append('history object ' + oid + ': identity requires review')
        if kind == b'commit':
            for entry in filter(None, git('ls-tree', '-rz', oid).split(b'\0')):
                metadata, name = entry.split(b'\t', 1)
                if name.decode() not in PUBLIC_FILES or metadata.split()[0] not in (b'100644', b'100755'):
                    issues.append('history tree ' + oid + ': unexpected path or mode')
    if issues:
        print('\n'.join(sorted(set(issues))), file=sys.stderr)
        return 1
    print(f'PASS: {len(names)} allowlisted files; {len(objects)} reachable Git objects; no rule matches.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
