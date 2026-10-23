#!/usr/bin/env python3
"""Download an exact compatible release and invoke its verified installer."""
import sys
sys.dont_write_bytecode = True
if sys.version_info < (3, 9):
    sys.exit('Installation stopped: Python 3.9+ is required; use official codex')
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_SOURCE = 'https://github.com/HezLUO/codex-custom/releases/download'
MAX_ARCHIVE = 256 * 1024 * 1024
MAX_UNPACKED = 768 * 1024 * 1024
RUNTIME = {'runtime/precompiled.py', 'runtime/release_artifact.py', 'runtime/update-codex-custom.py'}
MEMBERS = RUNTIME | {'bin/codex', 'LICENSE', 'NOTICE', 'DEPENDENCY-NOTICES.txt', 'release.json', 'bootstrap.sh', 'bootstrap.py'}


def preflight():
    # Bootstrap is standalone; the installed runtime repeats the authoritative
    # package inventory and stability checks before activation.
    if platform.system() != 'Darwin' or platform.machine() != 'arm64':
        raise ValueError('Requires macOS Apple Silicon (arm64)')
    if not shutil.which('codesign'):
        raise ValueError('Requires the macOS codesign tool')
    binary = Path(os.environ.get('CODEX_OFFICIAL_BIN', str(Path.home() / '.local/bin/codex'))).expanduser().resolve(strict=True)
    version_result = subprocess.run([str(binary), '--version'], capture_output=True, text=True, timeout=30, check=True)
    match = re.fullmatch(r'codex-cli ([0-9]+\.[0-9]+\.[0-9]+)', version_result.stdout.strip())
    if not match:
        raise ValueError('Cannot identify the official Codex version')
    version = match.group(1)
    root = binary.parent.parent
    releases = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser().resolve() / 'packages/standalone/releases'
    metadata = json.loads((root / 'codex-package.json').read_text())
    expected = dict(layoutVersion=1, version=version, target='aarch64-apple-darwin', variant='codex', entrypoint='bin/codex', resourcesDir='codex-resources', pathDir='codex-path')
    if root.parent != releases or binary != root / 'bin/codex' or any(metadata.get(k) != v for k, v in expected.items()):
        raise ValueError('Requires a matching complete official standalone package in CODEX_HOME')
    for name in ('bin/codex-code-mode-host', 'codex-path/rg'):
        if not os.access(root / name, os.X_OK):
            raise ValueError('Official package is missing executable helpers')
    if not (root / 'codex-resources/voice').is_dir():
        raise ValueError('Official package is missing voice resources')
    for item in root.rglob('*'):
        if item.is_symlink() and root not in item.resolve(strict=True).parents:
            raise ValueError('Official package contains an external resource link')
    return version


def checked_url(url, allow_query=False):
    parsed = urllib.parse.urlsplit(url)
    if (parsed.username or parsed.password or (parsed.query and not allow_query) or parsed.fragment
            or not parsed.hostname or parsed.scheme not in ('http', 'https')):
        raise ValueError('Release source must be HTTPS or a loopback HTTP test service')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise ValueError('HTTP is allowed only for a loopback test service')
    return url


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        checked_url(newurl, allow_query=True)
        if urllib.parse.urlsplit(request.full_url).scheme == 'https' and urllib.parse.urlsplit(newurl).scheme != 'https':
            raise ValueError('HTTPS download redirect cannot downgrade transport')
        return super().redirect_request(request, fp, code, message, headers, newurl)


def fetch(url, destination, limit):
    checked_url(url)
    opener = urllib.request.build_opener(SafeRedirect())
    count = 0
    with opener.open(url, timeout=30) as response, destination.open('wb') as output:
        size = response.headers.get('Content-Length')
        if size is not None and (not size.isdigit() or int(size) > limit):
            raise ValueError('Download exceeds size limit or has an invalid length')
        while True:
            chunk = response.read(min(1024 * 1024, limit + 1 - count))
            if not chunk:
                break
            count += len(chunk)
            if count > limit:
                raise ValueError('Download exceeds size limit')
            output.write(chunk)
        if size is not None and count != int(size):
            raise ValueError('Download was interrupted')


def unpack_runtime(archive, root, descriptor):
    payload, modes = {}, {}
    total = 0
    with tarfile.open(archive, 'r:gz') as stream:
        for member in stream:
            total += member.size
            if (not member.isfile() or member.name not in MEMBERS or member.name in payload
                    or member.mode not in (0o644, 0o755) or member.pax_headers
                    or member.size > 512 * 1024 * 1024 or total > MAX_UNPACKED):
                raise ValueError('Archive member rejected')
            payload[member.name] = stream.extractfile(member).read()
            modes[member.name] = member.mode
    manifest = json.loads(payload.get('release.json', b'{}'))
    if any(manifest.get(key) != descriptor[key] for key in ('release_id', 'official_version', 'target', 'layout_version')):
        raise ValueError('Release descriptor does not match archive metadata')
    contents = set(payload) - {'release.json'}
    if (manifest.get('schema') != 1 or not RUNTIME <= contents or set(manifest.get('members', {})) != contents):
        raise ValueError('Release runtime or member manifest mismatch')
    for name in contents:
        if manifest['members'][name] != dict(sha256=hashlib.sha256(payload[name]).hexdigest(), mode=modes[name]):
            raise ValueError('Release member digest or mode mismatch')
    # No downloaded Python is imported until archive and every member are checked.
    for name in RUNTIME:
        (root / Path(name).name).write_bytes(payload[name])


def download_and_install(source, bin_dir, lock_held=False):
    version = preflight()
    source = checked_url(source.rstrip('/'))
    tag = 'official-' + version + '-aarch64-apple-darwin'
    with tempfile.TemporaryDirectory(prefix='codex-custom-download-') as temporary:
        root = Path(temporary)
        fetch(source + '/' + tag + '/release.json', root / 'descriptor.json', 64 * 1024)
        descriptor = json.loads((root / 'descriptor.json').read_text())
        if (descriptor.get('schema') != 1 or descriptor.get('official_version') != version
                or descriptor.get('target') != 'aarch64-apple-darwin' or descriptor.get('layout_version') != 1
                or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', descriptor.get('release_id', ''))
                or descriptor.get('archive') != 'codex-custom.tar.gz'
                or not re.fullmatch(r'[0-9a-f]{64}', descriptor.get('sha256', ''))):
            raise ValueError('No matching release descriptor for installed official version and platform')
        archive = root / 'codex-custom.tar.gz'
        fetch(source + '/' + tag + '/' + descriptor['archive'], archive, MAX_ARCHIVE)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != descriptor['sha256']:
            raise ValueError('Release archive SHA-256 mismatch')
        unpack_runtime(archive, root, descriptor)
        # Running an installed updater already imported its own validator. Bind
        # the freshly verified module only while loading this release's runtime;
        # restore the caller's bindings afterward so versions cannot mix.
        old_path = list(sys.path)
        previous = sys.modules.get('release_artifact')
        try:
            sys.path.insert(0, str(root))
            validator_spec = importlib.util.spec_from_file_location('release_artifact', root / 'release_artifact.py')
            validator = importlib.util.module_from_spec(validator_spec)
            validator_spec.loader.exec_module(validator)
            sys.modules['release_artifact'] = validator
            spec = importlib.util.spec_from_file_location('downloaded_precompiled', root / 'precompiled.py')
            installer = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(installer)
            try:
                installer.install(archive, descriptor['sha256'], bin_dir, installer.state_dir(), lock_held=lock_held)
            except validator.ReleaseError as error:
                raise RuntimeError(str(error)) from error
        finally:
            sys.path[:] = old_path
            if previous is None:
                sys.modules.pop('release_artifact', None)
            else:
                sys.modules['release_artifact'] = previous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-source', default=os.environ.get('CODEX_CUSTOM_RELEASE_SOURCE', DEFAULT_SOURCE))
    parser.add_argument('--bin-dir', type=Path, default=Path.home() / '.local/bin')
    args = parser.parse_args(argv)
    try:
        download_and_install(args.release_source, args.bin_dir)
        print('Run codex-custom from your selected bin directory (add it to PATH if needed).')
        return 0
    except Exception as error:
        # Network/OS exceptions can embed user paths, remote payloads or URLs.
        message = str(error) if isinstance(error, ValueError) else 'Download or installation failed; check official installation and release availability'
        print('Installation stopped: ' + message + '; use official codex for recovery', file=sys.stderr)
        return 1

if __name__ == '__main__':
    raise SystemExit(main())
