#!/usr/bin/env python3
"""Verified precompiled installation and launch. Never invokes a source build."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import shlex
import signal
import subprocess
import sys
import tempfile
import uuid

sys.dont_write_bytecode = True
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
    selected = Path(os.environ.get('CODEX_CUSTOM_STATE_DIR', str(Path.home() / '.local/share/codex-custom/precompiled'))).expanduser().absolute()
    return selected.parent.resolve() / selected.name


def preflight():
    if sys.version_info < (3, 9):
        raise RuntimeError('Python 3.9+ is required')
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise RuntimeError('Requires macOS Apple Silicon (arm64)')
    version = package.official_version()
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
    if marker.is_symlink():
        raise RuntimeError('Untrusted ownership receipt')
    if not marker.exists():
        return None
    value = json.loads(marker.read_text())
    if (not isinstance(value, dict) or value.get('owner') != OWNER
            or not isinstance(value.get('installation_id'), str) or len(value['installation_id']) != 32
            or not isinstance(value.get('launcher'), str) or not isinstance(value.get('package_parent'), str)):
        raise RuntimeError('Unknown installation ownership')
    return value


def checked_release(state, release, owner):
    if (release.parent != state / 'releases' or release.is_symlink()
            or (release / 'receipt.json').is_symlink()):
        raise RuntimeError('Untrusted current release')
    receipt = json.loads((release / 'receipt.json').read_text())
    if (receipt.get('owner') != OWNER or receipt.get('installation_id') != owner.get('installation_id')
            or receipt.get('state') != str(state)):
        raise RuntimeError('Installed receipt ownership changed')
    root = Path(receipt['official_root'])
    target = (release / 'package').resolve(strict=True)
    expected = root.parent / 'codex-custom' / release.name / 'package'
    if (target != expected or root.parent / 'codex-custom' != Path(owner['package_parent'])
            or any(item.is_symlink() for item in (expected.parent, expected.parent.parent))):
        raise RuntimeError('Installed package ownership mismatch')
    if receipt.get('package_inventory') != package.package_inventory(target):
        raise RuntimeError('Installed receipt or official resources changed; reinstall; use official codex')
    manifest = receipt['manifest']
    expected_files = set(manifest['members']) | {'receipt.json', 'package', 'codex', 'run.lock'}
    for item in release.rglob('*'):
        name = item.relative_to(release).as_posix()
        if item.is_dir() and not item.is_symlink():
            if not any(member.startswith(name + '/') for member in manifest['members']):
                raise RuntimeError('Unexpected installed directory; refusing managed operation')
        elif name not in expected_files:
            raise RuntimeError('Unexpected installed member; refusing managed operation')
    if not (release / 'codex').is_symlink() or (release / 'codex').readlink() != Path('package/bin/codex'):
        raise RuntimeError('Installed frontend link ownership mismatch')
    for name, info in manifest['members'].items():
        # The archive reader already enforced this closed set at installation.
        if name not in artifact.BASE_MEMBERS | artifact.RUNTIME_MEMBERS:
            raise RuntimeError('Installed member manifest rejected')
        item = release / name
        if any(parent.is_symlink() for parent in (item, *list(item.parents)[:len(Path(name).parts)-1])) or artifact.digest(item.read_bytes()) != info['sha256'] or item.stat().st_mode & 0o777 != info['mode']:
            raise RuntimeError('Installed runtime integrity check failed')
    if receipt['package_inventory']['bin/codex']['sha256'] != manifest['members']['bin/codex']['sha256']:
        raise RuntimeError('Installed frontend digest mismatch')
    artifact.verify_binary(target / 'bin/codex', manifest['official_version'],
                           privacy_verified_sha256=manifest['members']['bin/codex']['sha256'])
    return receipt


def checked_current(state, official=None):
    owner = owner_receipt(state)
    current = state / 'current'
    if not owner or not current.is_symlink():
        raise RuntimeError('No managed installation; install a precompiled release first')
    release = current.resolve(strict=True)
    receipt = checked_release(state, release, owner)
    if official is not None and (receipt['official_root'], receipt['official_metadata'], receipt['official_inventory']) != (str(official[0]), official[1], official[2]):
        raise RuntimeError('Official package changed; matching precompiled release required')
    return release, receipt


def install(archive, checksum, bin_dir, state, lock_held=False):
    official = preflight()
    root, metadata, inventory = official
    if archive.stat().st_size > artifact.MAX_ARCHIVE:
        raise RuntimeError('Release archive size limit exceeded')
    if not checksum or artifact.digest(archive.read_bytes()) != checksum:
        raise RuntimeError('Release archive SHA-256 mismatch')
    manifest, payload = artifact.read_archive(archive, metadata['version'])
    required = {'runtime/precompiled.py', 'runtime/release_artifact.py', 'runtime/update-codex-custom.py'}
    if not required <= payload.keys():
        raise RuntimeError('Release is missing standalone runtime components')
    destination = bin_dir.expanduser().absolute() / 'codex-custom'
    expected = shim(state)
    with nullcontext() if lock_held else locked(state, create=True):
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
            if Path(owner['package_parent']) != root.parent / 'codex-custom':
                raise RuntimeError('Official package ownership location changed')
            if os.path.lexists(state / 'current'):
                checked_current(state)
        installation_id = owner['installation_id'] if owner else uuid.uuid4().hex
        releases = state / 'releases'
        releases.mkdir(exist_ok=True)
        if releases.is_symlink():
            raise RuntimeError('Untrusted releases directory')
        release = Path(tempfile.mkdtemp(prefix=manifest['release_id'] + '-', dir=releases))
        if (root.parent / 'codex-custom').is_symlink():
            shutil.rmtree(release)
            raise RuntimeError('Untrusted native custom package parent')
        package_path = root.parent / 'codex-custom' / release.name
        activated = False
        created_package = False
        created_shim = False
        link = None
        try:
            for name, data in payload.items():
                item = release / name
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_bytes(data)
                item.chmod(manifest['members'][name]['mode'])
            artifact.verify_binary(release / 'bin/codex', metadata['version'])
            copied = package.stage_package(root, release / 'bin/codex', release)
            created_package = True
            receipt = dict(owner=OWNER, installation_id=installation_id, state=str(state), manifest=manifest, official_root=str(root), official_metadata=metadata,
                           official_inventory=inventory, package_inventory=copied)
            (release / 'receipt.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
            if preflight() != official:
                raise RuntimeError('Official package changed during installation; retry')
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not exists:
                with destination.open('x') as stream:
                    created_shim = True
                    stream.write(expected)
                destination.chmod(0o755)
            if not owner:
                (state / 'owner.json').write_text(json.dumps(dict(owner=OWNER, launcher=str(destination), installation_id=installation_id, package_parent=str(root.parent / 'codex-custom'))) + '\n')
            link = state / ('activate-' + uuid.uuid4().hex)
            link.symlink_to(release.relative_to(state))
            os.replace(link, state / 'current')
            activated = True
            print('Precompiled release installed: ' + manifest['release_id'])
        finally:
            if not activated:
                if link is not None:
                    link.unlink(missing_ok=True)
                if created_shim:
                    destination.unlink(missing_ok=True)
                if not owner:
                    (state / 'owner.json').unlink(missing_ok=True)
                shutil.rmtree(release, ignore_errors=True)
                if created_package:
                    shutil.rmtree(package_path, ignore_errors=True)
                if not owner:
                    # Only remove our now-empty container; never sweep unknown state.
                    try:
                        releases.rmdir()
                    except OSError:
                        pass


def uninstall(state, bin_dir, purge=False):
    with locked(state):
        owner = owner_receipt(state)
        destination = bin_dir.expanduser().absolute() / 'codex-custom'
        if not owner or owner.get('launcher') != str(destination):
            raise RuntimeError('Unknown installation ownership')
        if os.path.lexists(destination) and (destination.is_symlink() or not destination.is_file() or destination.read_text() != shim(state)):
            raise RuntimeError('Launcher is not owned; refusing uninstall')
        if os.path.lexists(state / 'current'):
            checked_current(state)
        leases, releases = [], []
        try:
            if purge:
                if (state / 'releases').is_symlink():
                    raise RuntimeError('Untrusted releases directory')
                for release in sorted((state / 'releases').iterdir()):
                    marker = release / 'receipt.json'
                    if release.is_symlink() or marker.is_symlink():
                        raise RuntimeError('Untrusted cleanup receipt')
                    if not marker.is_file():
                        continue  # Unknown directories belong to their owner.
                    receipt = json.loads(marker.read_text())
                    if receipt.get('installation_id') != owner['installation_id']:
                        continue
                    checked_release(state, release, owner)
                    leasepath = release / 'run.lock'
                    if leasepath.is_symlink():
                        raise RuntimeError('Untrusted run lease')
                    stream = leasepath.open('a')
                    leases.append(stream)
                    try:
                        fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        raise RuntimeError('A custom session is running; exit it before cleanup')
                    releases.append(release)
                current = state / 'current'
                if os.path.lexists(current):
                    if not current.is_symlink() or current.resolve(strict=True) not in releases:
                        raise RuntimeError('Untrusted current release; refusing cleanup')
            if os.path.lexists(destination):
                destination.unlink()
            if purge:
                (state / 'current').unlink(missing_ok=True)
                for release in releases:
                    target = (release / 'package').resolve(strict=True)
                    shutil.rmtree(target)
                    try:
                        target.parent.rmdir()
                    except OSError:
                        pass  # Unreceipted siblings remain owned by their creator.
                    shutil.rmtree(release)
                print('Owned releases removed; ownership marker and lock retained; other data preserved')
            else:
                print('Managed launcher removed; releases and diagnostics retained')
        finally:
            for stream in leases:
                stream.close()


def update(state, bin_dir, source):
    # Keep the same lock across network fetch and activation: an uninstall cannot
    # be undone by a pending download. The downloaded installer reuses this lock.
    with locked(state):
        owner = owner_receipt(state)
        destination = bin_dir.expanduser().absolute() / 'codex-custom'
        if not owner or owner.get('launcher') != str(destination) or destination.is_symlink() or not destination.is_file() or destination.read_text() != shim(state):
            raise RuntimeError('Launcher is not owned; refusing update')
        release, receipt = checked_current(state)
        if 'bootstrap.py' not in receipt['manifest']['members']:
            raise RuntimeError('Installed release has no verified downloader; reinstall from a reviewed source')
        spec = importlib.util.spec_from_file_location('verified_release_downloader', release / 'bootstrap.py')
        downloader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(downloader)
        downloader.download_and_install(source or os.environ.get('CODEX_CUSTOM_RELEASE_SOURCE', downloader.DEFAULT_SOURCE), bin_dir, lock_held=True)


def supervise(binary, arguments, environment, lease):
    child = None
    pending = []
    previous = {}

    def forward(signum, frame):
        if child is None:
            pending.append(signum)
            return
        if child.poll() is not None:
            return
        if signum in (signal.SIGINT, signal.SIGQUIT) and os.isatty(0):
            try:
                if os.tcgetpgrp(0) == os.getpgrp() == os.getpgid(child.pid):
                    # The terminal already delivered this signal to the frontend.
                    return
            except OSError:
                pass
        try:
            child.send_signal(signum)
        except ProcessLookupError:
            pass

    try:
        for signum in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT, signal.SIGQUIT):
            previous[signum] = signal.signal(signum, forward)
        # Only the supervisor owns the lease. A frontend-started official daemon
        # must remain independent and must never inherit a release lock.
        child = subprocess.Popen([str(binary), *arguments], env=environment, close_fds=True)
        for signum in pending:
            forward(signum, None)
        result = child.wait()
        return result if result >= 0 else 128 - result
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            child.wait()
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        lease.close()


def launch(state, arguments):
    # Management commands remain available after the official package changes.
    if arguments[:1] in (['--update'], ['--uninstall']):
        owner = owner_receipt(state)
        if not owner:
            raise RuntimeError('No managed installation')
        return main(['--bin-dir', str(Path(owner['launcher']).parent), *arguments])
    official = preflight()
    for attempt in range(2):
        with locked(state):
            release, receipt = checked_current(state)
            matches = (receipt['official_root'], receipt['official_metadata'], receipt['official_inventory']) == (str(official[0]), official[1], official[2])
            if matches:
                if preflight() != official:
                    raise RuntimeError('Official package changed before launch; retry')
                binary = release / 'package/bin/codex'
                environment = dict(os.environ)
                environment.setdefault('CODEX_CUSTOM_STATUS_LINE', STATUS)
                if (release / 'run.lock').is_symlink():
                    raise RuntimeError('Untrusted run lease')
                lease = (release / 'run.lock').open('a')
                fcntl.flock(lease, fcntl.LOCK_SH)
                break
            owner = owner_receipt(state)
        if attempt:
            raise RuntimeError('Official package changed; matching precompiled release required')
        update(state, Path(owner['launcher']).parent, None)
        official = preflight()
    return supervise(binary, arguments, environment, lease)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path)
    parser.add_argument('--sha256')
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--uninstall', action='store_true')
    parser.add_argument('--update', action='store_true')
    parser.add_argument('--purge', action='store_true')
    parser.add_argument('--release-source')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.purge and not args.uninstall:
            raise RuntimeError('--purge requires --uninstall')
        if args.uninstall:
            uninstall(state_dir(), args.bin_dir, args.purge)
        elif args.update:
            update(state_dir(), args.bin_dir, args.release_source)
        elif args.launch:
            arguments = args.arguments[1:] if args.arguments[:1] == ['--'] else args.arguments
            return launch(state_dir(), arguments) or 0
        elif args.archive:
            install(args.archive, args.sha256, args.bin_dir, state_dir())
        else:
            raise RuntimeError('Provide --archive FILE --sha256 SHA256; source build is explicit via update-codex-custom.py')
        return 0
    except (OSError, RuntimeError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as error:
        # Package validation errors describe categories, not contents or private data.
        detail = str(error) if isinstance(error, (RuntimeError, artifact.ReleaseError)) else 'I/O or metadata failure; inspect installation and retry'
        print('Installation stopped: ' + detail + '; use official codex for recovery', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
