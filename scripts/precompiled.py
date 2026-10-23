#!/usr/bin/env python3
"""Verified precompiled installation and launch. Never invokes a source build."""
import argparse
from contextlib import contextmanager
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import subprocess
import sys
import tempfile
import uuid

import release_artifact as artifact

HERE = Path(__file__).resolve().parent
updater_path = HERE / 'update-codex-custom.py'
if not updater_path.exists():
    updater_path = HERE.parent / 'update-codex-custom.py'
spec = importlib.util.spec_from_file_location('source_package_tools', updater_path)
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)
STATUS = '["model-with-reasoning","approval-mode","context-details","weekly-limit","git-branch","task-progress"]'
OWNER = 'codex-custom-precompiled-v1'


def state_dir():
    return Path(os.environ.get('CODEX_CUSTOM_STATE_DIR', str(Path.home() / '.local/share/codex-custom/precompiled'))).expanduser().resolve()


def preflight():
    if sys.version_info < (3, 9):
        raise RuntimeError('Python 3.9+ is required')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Requires macOS Apple Silicon (arm64)')
    version = package.official_version()
    if version != '0.164.0':
        raise RuntimeError('No supported precompiled release for official ' + version + '; use official codex')
    root, metadata = package.official_package(version)
    native_releases = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))) / 'packages/standalone/releases'
    if root.parent != native_releases.resolve():
        raise RuntimeError('Official package must be below CODEX_HOME/packages/standalone/releases for native service mode')
    for item in root.rglob('*'):
        if item.is_symlink() and root not in item.resolve(strict=True).parents:
            raise RuntimeError('Official package contains an external resource link')
    return root, metadata, package.package_inventory(root)


@contextmanager
def locked(state, create=False):
    if state.is_symlink():
        raise RuntimeError('State directory must not be a symlink')
    if create:
        state.mkdir(parents=True, exist_ok=True)
    if not state.is_dir():
        raise RuntimeError('No managed installation; install a precompiled release first')
    lockpath = state / 'update.lock'
    if lockpath.is_symlink():
        raise RuntimeError('Untrusted state lock')
    with lockpath.open('a') as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another installation or update is active; retry later')
        yield


def shim(state):
    # Freeze this installation's state location, independent of shell environment/checkout.
    return '#!/bin/sh\n# ' + OWNER + '\nexport CODEX_CUSTOM_STATE_DIR=' + shlex.quote(str(state)) + '\nexec python3 ' + shlex.quote(str(state / 'current/runtime/precompiled.py')) + ' --launch -- "$@"\n'


def owner_receipt(state):
    marker = state / 'owner.json'
    if not marker.exists():
        return None
    if marker.is_symlink():
        raise RuntimeError('Untrusted ownership receipt')
    value = json.loads(marker.read_text())
    if value.get('owner') != OWNER:
        raise RuntimeError('Unknown installation ownership')
    return value


def checked_current(state, official):
    owner = owner_receipt(state)
    current = state / 'current'
    if not owner or not current.is_symlink():
        raise RuntimeError('No managed installation; install a precompiled release first')
    release = current.resolve(strict=True)
    if release.parent != state / 'releases' or release.is_symlink():
        raise RuntimeError('Untrusted current release')
    receipt = json.loads((release / 'receipt.json').read_text())
    root, metadata, inventory = official
    if (receipt.get('owner') != OWNER or receipt.get('official_root') != str(root)
            or receipt.get('official_metadata') != metadata or receipt.get('official_inventory') != inventory
            or receipt.get('package_inventory') != package.package_inventory(release / 'package')):
        raise RuntimeError('Installed receipt or official resources changed; reinstall; use official codex')
    manifest = receipt['manifest']
    for name, info in manifest['members'].items():
        if name.startswith('runtime/'):
            item = release / name
            if item.is_symlink() or artifact.digest(item.read_bytes()) != info['sha256'] or item.stat().st_mode & 0o777 != info['mode']:
                raise RuntimeError('Installed runtime integrity check failed')
    target = (release / 'package').resolve()
    if target.parent.parent != root.parent / 'codex-custom' or target.parent.name != release.name:
        raise RuntimeError('Installed package ownership mismatch')
    if receipt['package_inventory']['bin/codex']['sha256'] != manifest['members']['bin/codex']['sha256']:
        raise RuntimeError('Installed frontend digest mismatch')
    artifact.verify_binary(target / 'bin/codex')
    return release, receipt


def install(archive, checksum, bin_dir, state):
    official = preflight()
    root, metadata, inventory = official
    if not checksum or artifact.digest(archive.read_bytes()) != checksum:
        raise RuntimeError('Release archive SHA-256 mismatch')
    manifest, payload = artifact.read_archive(archive)
    required = {'runtime/precompiled.py', 'runtime/release_artifact.py', 'runtime/update-codex-custom.py'}
    if not required <= payload.keys():
        raise RuntimeError('Release is missing standalone runtime components')
    destination = bin_dir.expanduser().absolute() / 'codex-custom'
    expected = shim(state)
    with locked(state, create=True):
        owner = owner_receipt(state)
        entries = set(item.name for item in state.iterdir())
        if not owner and entries - {'update.lock'}:
            raise RuntimeError('Refusing to adopt unknown existing state')
        if owner and owner.get('launcher') != str(destination):
            raise RuntimeError('Installation is owned by another launcher location')
        exists = os.path.lexists(destination)
        if exists and (not owner or destination.is_symlink() or not destination.is_file() or destination.read_text() != expected):
            raise RuntimeError('Destination exists and is not owned; choose another --bin-dir')
        if owner:
            checked_current(state, official)
        releases = state / 'releases'
        releases.mkdir(exist_ok=True)
        if releases.is_symlink():
            raise RuntimeError('Untrusted releases directory')
        release = Path(tempfile.mkdtemp(prefix=manifest['release_id'] + '-', dir=releases))
        package_path = root.parent / 'codex-custom' / release.name
        activated = False
        created_shim = False
        try:
            for name, data in payload.items():
                item = release / name
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_bytes(data)
                item.chmod(manifest['members'][name]['mode'])
            artifact.verify_binary(release / 'bin/codex', metadata['version'])
            copied = package.stage_package(root, release / 'bin/codex', release)
            receipt = dict(owner=OWNER, manifest=manifest, official_root=str(root), official_metadata=metadata,
                           official_inventory=inventory, package_inventory=copied)
            (release / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
            if preflight() != official:
                raise RuntimeError('Official package changed during installation; retry')
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not exists:
                with destination.open('x') as stream:
                    stream.write(expected)
                created_shim = True
                destination.chmod(0o755)
            if not owner:
                (state / 'owner.json').write_text(json.dumps(dict(owner=OWNER, launcher=str(destination))) + '\n')
            link = state / ('activate-' + uuid.uuid4().hex)
            link.symlink_to(release.relative_to(state))
            os.replace(link, state / 'current')
            activated = True
            print('Precompiled release installed: ' + manifest['release_id'])
        finally:
            if not activated:
                if created_shim:
                    destination.unlink(missing_ok=True)
                if not owner:
                    (state / 'owner.json').unlink(missing_ok=True)
                shutil.rmtree(release, ignore_errors=True)
                shutil.rmtree(package_path, ignore_errors=True)


def launch(state, arguments):
    official = preflight()
    with locked(state):
        release, receipt = checked_current(state, official)
        if preflight() != official:
            raise RuntimeError('Official package changed before launch; retry')
        binary = release / 'package/bin/codex'
        environment = dict(os.environ)
        environment.setdefault('CODEX_CUSTOM_STATUS_LINE', STATUS)
        # Release directories remain immutable; lock need not live across the session.
    os.execve(str(binary), [str(binary), *arguments], environment)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.launch:
            arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
            launch(state_dir(), arguments)
        elif args.archive:
            install(args.archive, args.sha256, args.bin_dir, state_dir())
        else:
            raise RuntimeError('Provide --archive FILE --sha256 SHA256; source build is explicit via update-codex-custom.py')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.SubprocessError) as error:
        # Package validation errors describe categories, not contents or private data.
        print('Installation stopped: ' + str(error) + '; use official codex for recovery', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
