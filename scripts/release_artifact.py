#!/usr/bin/env python3
"""Build and inspect strictly enumerated precompiled release archives."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import struct
import tempfile
import os
import tarfile
import platform

TARGETS = {
    'aarch64-apple-darwin': ('darwin', 'arm64'),
    'x86_64-apple-darwin': ('darwin', 'x86_64'),
    'x86_64-unknown-linux-musl': ('linux', 'x86_64'),
    'aarch64-unknown-linux-musl': ('linux', 'arm64'),
    'x86_64-pc-windows-msvc': ('windows', 'x86_64'),
}


def host_target():
    system, machine = platform.system().lower(), platform.machine().lower()
    machine = {'amd64': 'x86_64', 'aarch64': 'arm64'}.get(machine, machine)
    for target, pair in TARGETS.items():
        if pair == (system, machine):
            return target
    raise ValueError('Unsupported system/architecture; use official codex')


def windows(target=None):
    return TARGETS[target or host_target()][0] == 'windows'


def entrypoint(target=None):
    return 'bin/codex.exe' if windows(target) else 'bin/codex'


def signing(target):
    return ('ad-hoc; no publisher identity or notarization' if TARGETS[target][0] == 'darwin'
            else 'unsigned; no publisher identity or notarization')


def helpers(target):
    suffix = '.exe' if windows(target) else ''
    files = ['bin/codex-code-mode-host' + suffix, 'codex-path/rg' + suffix]
    if TARGETS[target][0] == 'windows':
        files += ['codex-resources/codex-command-runner.exe',
                  'codex-resources/codex-windows-sandbox-setup.exe']
    if TARGETS[target][0] == 'linux':
        files += ['codex-resources/bwrap']
    return files


def check_architecture(data, target):
    family, cpu = TARGETS[target]
    if family == 'darwin':
        expected = 'cffaedfe0c000001' if cpu == 'arm64' else 'cffaedfe07000001'
        valid = len(data) >= 32 and data[:8] == bytes.fromhex(expected)
    elif family == 'linux':
        valid = (len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01'
                 and struct.unpack_from('<H', data, 18)[0] == (183 if cpu == 'arm64' else 62))
    else:
        valid = False
        if len(data) >= 64 and data[:2] == b'MZ':
            offset = struct.unpack_from('<I', data, 60)[0]
            valid = (offset >= 64 and offset + 26 <= len(data)
                     and data[offset:offset + 6] == b'PE\0\0\x64\x86'
                     and data[offset + 24:offset + 26] == b'\x0b\x02')
    if not valid:
        raise ValueError('Frontend format/architecture does not match release target')


def mode_matches(path, expected):
    # Windows has no POSIX executable mode; archive modes remain strict and hashes
    # cover file content. Never weaken POSIX permission verification.
    return os.name == 'nt' or path.stat().st_mode & 0o777 == expected


def is_link(path):
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)
    except FileNotFoundError:
        return False


LOCK_EX, LOCK_SH, LOCK_NB = 2, 1, 4


def flock(stream, flags):
    if os.name != 'nt':
        import fcntl
        return fcntl.flock(stream, flags)
    import ctypes
    from ctypes import wintypes
    import msvcrt
    # CRT _locking's read modes are still exclusive. LockFileEx supplies actual
    # shared leases, so simultaneous frontend sessions remain possible.
    class Overlapped(ctypes.Structure):
        _fields_ = [('Internal', ctypes.c_size_t), ('InternalHigh', ctypes.c_size_t),
                    ('Offset', wintypes.DWORD), ('OffsetHigh', wintypes.DWORD), ('hEvent', wintypes.HANDLE)]
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    lock = kernel.LockFileEx
    lock.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.DWORD,
                     wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(Overlapped)]
    lock.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(stream.fileno())
    overlap = Overlapped()
    mode = 1 | (2 if flags & LOCK_EX else 0)
    while True:
        if lock(handle, mode, 0, 1, 0, ctypes.byref(overlap)):
            return
        error = ctypes.get_last_error()
        if error != 33:  # ERROR_LOCK_VIOLATION
            raise ctypes.WinError(error)
        if flags & LOCK_NB:
            raise BlockingIOError('Managed release is locked')
        import time
        time.sleep(0.05)


def default_official():
    if windows():
        base = os.environ.get('CODEX_INSTALL_DIR')
        return (Path(base) if base else Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Programs/OpenAI/Codex/bin') / 'codex.exe'
    return Path.home() / '.local/bin/codex'


ROOT = Path(__file__).resolve().parents[1]
RULES = {
    'personal-home-path': rb'/(?:Users|home)/[^\s/<>"\x27]+',
    'windows-home-path': rb'(?i)[a-z]:[\\/](?:Users|Documents and Settings)[\\/][^\s\\/\x00<>"\x27]+',
    'windows-home-path-utf16': rb'(?i)[a-z]\x00:\x00[\\/]\x00U\x00s\x00e\x00r\x00s\x00[\\/]\x00',
    'machine-temporary-path': rb'/(?:private/)?var/folders/[^\s\x00]+',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential': rb'(?i)(?:sk-[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,}|AKIA[A-Z0-9]{16}|Bearer\s+[a-z0-9._-]{20,})',
    'session-identifier': rb'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b',
}
# Static upstream literals can be reviewed by SHA-256, never raw sensitive values.
REVIEWED_LITERALS = {
    # Native Linux x64: public MCP authentication labels and enum metadata;
    # public status-line fields plus the context-details patch. Every byte was
    # matched to the fixed official frontend or published source before review.
    '19e1e9278dbaf5c4dd55e967721c8841efe2cab8102755d3a8c47a7adde8761a',
    'b11b05836e1d14e1a8e545ee9993775686a79664ef457b42b94250e56a9dbc2a',
    # Public websocket-auth CLI help merged with its clap argument metadata.
    # Pinned upstream codex-rs/websocket-auth/src/lib.rs:56-57; no secret value.
    '670faf85aaeed7e56aa3fe7a2fba71e4a98d328ffc2c83d56a2a000f788100c8',
    '846feea5ac25e23d05d7f23126d0f9cc1277920d1aaa9ec2ba72adf93b7970bd',
    '0ed6536aea536dae2f497b956167afe4979225ba93b487312ad23f308500fde8',
    # Pinned network-proxy credential_broker/providers/openai.rs contains public
    # detector prefixes/watermark, not complete keys. Rust merges adjacent text.
    '04ae2ad0094fd00723d8932b7df490fff1e6584f22afba63d7e23304e48754b0',
    '8028bd5239cae61a1ac91c401977eb1a24b3bc7c43b97945cef38ab7fa4846af',
    # Public mxc-sdk learning_mode_windows/network_extractors.rs constants:
    # provider, sublayer and Windows app-isolation identifiers, not sessions.
    '7072290eb10f53ac323515f5fc18c259e24dcabe48f877150b4c665f6f3ad244',
    'be1bef2417a938043e410c938f8a580690835810776f7437dab1799788515adc',
    '7f14466df9323c3c1ef44fdd7124a57ffa807b0c7d4ba6ec314cdd4c24eaed64',
    # Exact public reference variants: MP4 atom names, credential detector
    # prefixes, OAuth labels, and TUI/CLI field names merged by the linker.
    '21ae777849d09ed9ef838ffac0f264adb0973f4609b9a1597b6fc43fec0ecd8b',
    '2428cf32c11c25ee1de98e1c3b8522b9d9175e7f0a8941cdf4b00cd260edcce5',
    '287145c74c67db8cecb3158c3db3b65f7927e773600b7351e368bcdb39fc7983',
    '5565ead01c40fa13e95a45733a2c415869f10d3d2df23cde7b9c16e70ff3c2eb',
    '788489d19340c903b1b664a09f1da3f68af3ee98cc65c84bf12898afb1e0c3ef',
    '6f3aa50b505f2a38289110e7405ad26eef29fb31bea4fa6e9cb476e7351ab1ca',
    'afdeb5ee533885f2736323232d2b8e8ff1401a9e879ccbb87e770bcdd4d03159',
    '9ff908e3ff0c0e97aef211493198e8da655e548418d09067616458a90a091b5a',
    '77d6288dafb79edf8d8bb88a5d506d7794c173fed9fdfb7f9404e869a1af4209',
    '4ff87902041e3ce6d615e3c74440ff75f71e9f9e50da029de858a54bbf63fa24',
    'c33212249bacb786cca590defb38233451981ff8cf406fa0383a64fe500fa638',
    'fb620f9139a4e9601aa8cd42c97342b4330642ae99767873a5444665e4614d02',
    '071e4202f3c4620e8a37b3476604d5e4e28be3f221f7dcb9acbbb1c2e6055421',
    'd0e13603b8294e32868268516f499f74852369f6a1ced7b85702b892fe8e2902',
    'e64f78d93f85c6a835d106ab4856a63deabb65f53ecd37d8039d66ef4698881b',
    '258d725ab8373ab7c7d2eceab74ed9e5bcee79666df641eb312299b1abcace9e',
    '9f331d8a638bfce01deea0645a267059bb197130b2e3793b6b3f4ad975f19e3f',
    '6222772ac11915cdeb09e6b17941510324c64266f66c2c14fc0a53d77189a54e',
    'af18a948b5308f09db3e310544841b5e11efa0c0c1f618882cd96a0c05944b9c',
    '00bce46225b668d670f4ae8a3d3cc4e3279c07d75aefaad5837811a45b8aba02',
    '197d1ddc4ccb013d0e9948f5093f179fd0ff7d26158ba8a01cf3aff3b2097eb9',
    '2b4b584391bdaafc432e211fdc2b09498be570753795cf88d7cf36f0ea6bdf81',
    '30c89fa3ab0bca0065b9f4b823bcf006a146efcf29dec304827d023db92a954f',
    '320159ebe3219112484baaa0aa1164dd93b25e98f4a1c7bee7fd602bc2a614c0',
    '6f2dd0c185e98bc52ac52bdd24710bed460d7160c2ec0afd501b565f38620d65',
    '7f44193a6edea087f5c0811306efae871c412b46ebee9a179fb3acf0cb5144a3',
    '83ad6844825f533cad46e9f2d007ef8cd808b9019438ef6c9b99e5c29e7d2aa4',
    '97d2b53289c74dbce6da0b49438060319bdfed20c4a4fb3a81d0a9b0d1dcb085',
    'a6d3541a478a4faafdbc4c19c95349aceeff7e4f36e499ef219bc863074ee947',
    'b5763688815b9b9dd18772e235bcf8324269b938dc0fd8e50b6341101a95702e',
}
BASE_MEMBERS = {'bin/codex', 'LICENSE', 'NOTICE', 'DEPENDENCY-NOTICES.txt'}
RUNTIME_MEMBERS = {'runtime/precompiled.py', 'runtime/release_artifact.py', 'runtime/update-codex-custom.py', 'bootstrap.sh', 'bootstrap.py', 'bootstrap.ps1'}

MAX_ARCHIVE = 256 * 1024 * 1024
MAX_UNPACKED = 768 * 1024 * 1024

class ReleaseError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def privacy_check(data):
    for label, pattern in RULES.items():
        for match in re.finditer(pattern, data):
            if digest(match.group()) not in REVIEWED_LITERALS:
                raise ReleaseError('privacy: ' + label)

def read_archive(path, expected_version='0.164.0', expected_target=None):
    """Return (validated manifest, payload bytes); never extract untrusted paths."""
    if Path(path).stat().st_size > MAX_ARCHIVE:
        raise ReleaseError('Release archive size limit exceeded')
    payload = {}
    modes = {}
    total = 0
    try:
        with tarfile.open(path, 'r:gz') as archive:
            for item in archive:
                total += item.size
                if (not item.isfile() or item.name not in BASE_MEMBERS | RUNTIME_MEMBERS | {'release.json', 'bin/codex.exe'}
                        or item.name in payload or item.size > 512 * 1024 * 1024 or total > MAX_UNPACKED
                        or item.mode not in (0o644, 0o755) or item.pax_headers):
                    raise ReleaseError('archive member rejected')
                payload[item.name] = archive.extractfile(item).read()
                modes[item.name] = item.mode
                privacy_check(payload[item.name])
        manifest = json.loads(payload.pop('release.json'))
        target = manifest.get('target')
        if (manifest.get('schema') != 1 or manifest.get('official_version') != expected_version
                or target not in TARGETS or (expected_target is not None and target != expected_target) or manifest.get('layout_version') != 1
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', manifest.get('release_id', ''))
                or not re.fullmatch(r'[0-9a-f]{40}', manifest.get('source_commit', ''))
                or not re.fullmatch(r'[0-9a-f]{64}', manifest.get('patch_sha256', ''))
                or not isinstance(manifest.get('provenance'), dict)
                or manifest.get('signing') != signing(target)):
            raise ReleaseError('release metadata rejected')
        members = manifest['members']
        base = (BASE_MEMBERS - {'bin/codex'}) | {entrypoint(target)}
        if (set(members) != set(payload) or not base <= set(payload)
                or (('bin/codex' if windows(target) else 'bin/codex.exe') in payload)):
            raise ReleaseError('archive member manifest mismatch')
        for name, data in payload.items():
            if members[name] != {'sha256': digest(data), 'mode': modes[name]}:
                raise ReleaseError('archive member digest or mode mismatch')
        if modes[entrypoint(target)] != 0o755:
            raise ReleaseError('frontend must be executable')
        return manifest, payload
    except (tarfile.TarError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReleaseError('invalid release archive') from error

def verify_binary(path, expected_version='0.164.0', privacy_verified_sha256=None, target=None):
    target = target or host_target()
    if target != host_target():
        raise ReleaseError('Binary execution verification requires a matching host target')
    data = Path(path).read_bytes()
    checksum = digest(data)
    # Cached admission verdict is valid only for these exact bytes. Callers must
    # first verify the receipt and all installed members; no CLI bypass exists.
    if privacy_verified_sha256 is None:
        privacy_check(data)
    elif checksum != privacy_verified_sha256:
        raise ReleaseError('frontend privacy verdict digest mismatch')
    try:
        check_architecture(data, target)
    except ValueError as error:
        raise ReleaseError(str(error)) from error
    commands = [[str(Path(path).resolve()), '--version']]
    if TARGETS[target][0] == 'darwin':
        commands.insert(0, ['codesign', '--verify', '--strict', str(path)])
    for command in commands:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if result.returncode:
            raise ReleaseError('frontend signature or version verification failed')
        if command[-1] == '--version' and result.stdout.strip() != ('codex-cli ' + expected_version).encode():
            raise ReleaseError('frontend version mismatch')
    if TARGETS[target][0] == 'darwin':
        info = subprocess.run(['codesign', '-dv', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if info.returncode or b'Signature=adhoc' not in info.stderr:
            raise ReleaseError('frontend signing policy mismatch')
    return checksum

def constant_data_ranges(data, target):
    """Validated non-executable constant sections shared by both sanitizers."""
    check_architecture(data, target)
    regions = []
    if 'linux' in target:
        table = struct.unpack_from('<Q', data, 40)[0]
        size, count = struct.unpack_from('<HH', data, 58)
        if size != 64 or table + size * count > len(data):
            raise ReleaseError('Invalid ELF section table')
        for i in range(count):
            _, kind, flags, _, offset, length = struct.unpack_from('<IIQQQQ', data, table + i * size)
            if kind == 1 and flags & 2 and not flags & 5:
                regions.append((offset, offset + length))
    elif target.endswith('apple-darwin'):
        count = struct.unpack_from('<I', data, 16)[0]; cursor = 32
        for _ in range(count):
            command, size = struct.unpack_from('<II', data, cursor)
            if size < 8 or cursor + size > len(data):
                raise ReleaseError('Invalid Mach-O load command')
            if command == 0x19:
                sections = struct.unpack_from('<I', data, cursor + 64)[0]
                if 72 + 80 * sections > size: raise ReleaseError('Invalid Mach-O sections')
                for i in range(sections):
                    section = cursor + 72 + i * 80
                    name = bytes(data[section:section + 16]).rstrip(b'\0')
                    segment = bytes(data[section + 16:section + 32]).rstrip(b'\0')
                    length = struct.unpack_from('<Q', data, section + 40)[0]
                    offset = struct.unpack_from('<I', data, section + 48)[0]
                    if segment == b'__TEXT' and name in (b'__cstring', b'__const'):
                        regions.append((offset, offset + length))
            cursor += size
    else:
        pe = struct.unpack_from('<I', data, 60)[0]
        count = struct.unpack_from('<H', data, pe + 6)[0]
        optional = struct.unpack_from('<H', data, pe + 20)[0]
        table = pe + 24 + optional
        if table + count * 40 > len(data): raise ReleaseError('Invalid PE sections')
        for i in range(count):
            section = table + i * 40
            length, offset = struct.unpack_from('<II', data, section + 16)
            flags = struct.unpack_from('<I', data, section + 36)[0]
            if flags & 0x40000040 == 0x40000040 and not flags & 0xa0000000:
                regions.append((offset, offset + length))
    if any(start < 0 or end > len(data) for start, end in regions):
        raise ReleaseError('Invalid constant-section bounds')
    return regions

def sanitize_binary(source, output):
    """Redact home-prefix literals only in Mach-O constant data, then re-sign copy."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or output.exists():
        raise ReleaseError('sanitized output must be a new separate file')
    data = source.read_bytes()
    verify_data = data
    if data[:8] != bytes.fromhex('cffaedfe0c000001'):
        raise ReleaseError('frontend architecture must be thin Mach-O arm64')
    ranges = constant_data_ranges(data, 'aarch64-apple-darwin')
    replacements = 0
    result = bytearray(data)
    for match in re.finditer(rb'/(?:Users|home)/[^/\s\x00<>"\x27]+', data):
        start, end = match.span()
        if not any(low <= start and end <= high for low, high in ranges):
            raise ReleaseError('home-prefix outside constant sections; rebuild required')
        # Preserve byte length and Rust string offsets. Redaction changes diagnostics only.
        prefix = b'/build/'
        if end - start < len(prefix):
            raise ReleaseError('home-prefix cannot be safely redacted')
        result[start:end] = prefix + b'_' * (end - start - len(prefix))
        replacements += 1
    privacy_check(bytes(result))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(result)
    output.chmod(0o755)
    signed = subprocess.run(['codesign', '--force', '--sign', '-', str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if signed.returncode:
        output.unlink()
        raise ReleaseError('ad-hoc signing failed')
    final_digest = verify_binary(output)
    return {'original_binary_sha256': digest(verify_data), 'binary_sha256': final_digest,
            'transformation': 'fixed-length home-prefix redaction in __TEXT __cstring/__const; ad-hoc re-sign',
            'redacted_prefix_count': replacements}

def package(args):
    target = getattr(args, 'target', None) or host_target()
    binary_hash = verify_binary(args.binary, target=target)
    if not args.provenance or not args.dependency_notices:
        raise ReleaseError('provenance and dependency notices required')
    provenance = json.loads(args.provenance.read_text())
    if provenance.get('binary_sha256') != binary_hash:
        raise ReleaseError('provenance binary digest mismatch')
    payload = {entrypoint(target): args.binary.read_bytes(), 'LICENSE': (ROOT / 'LICENSE').read_bytes(),
               'NOTICE': (ROOT / 'NOTICE').read_bytes(), 'DEPENDENCY-NOTICES.txt': args.dependency_notices.read_bytes()}
    for component in args.runtime:
        name, filename = component.split('=', 1)
        if name not in RUNTIME_MEMBERS or name in payload:
            raise ReleaseError('runtime member rejected')
        payload[name] = Path(filename).read_bytes()
    manifest = {'schema': 1, 'release_id': args.release_id, 'official_version': '0.164.0',
                'target': target, 'layout_version': 1,
                'source_commit': '6aaac694803004a63c6f393d153c96d22521a6b9',
                'patch_sha256': digest((ROOT / 'patches/codex-0.164.0-context-details.patch').read_bytes()),
                'signing': signing(target), 'provenance': provenance,
                'members': {name: {'sha256': digest(data), 'mode': 0o755 if name in ('bin/codex', 'bin/codex.exe', 'bootstrap.sh') else 0o644} for name, data in payload.items()}}
    payload['release.json'] = (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode()
    for data in payload.values():
        privacy_check(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ReleaseError('output already exists')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=args.output.parent, delete=False) as stream:
            temporary = Path(stream.name)
        with tarfile.open(temporary, 'w:gz', format=tarfile.USTAR_FORMAT) as archive:
            for name, data in sorted(payload.items()):
                item = tarfile.TarInfo(name)
                item.size = len(data)
                item.mode = manifest['members'].get(name, {'mode': 0o644})['mode']
                archive.addfile(item, io.BytesIO(data))
        read_archive(temporary)
        os.link(temporary, args.output)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    checksum = digest(args.output.read_bytes())
    args.output.with_suffix(args.output.suffix + '.sha256').write_text(checksum + '  ' + args.output.name + '\n')
    return {'status': 'candidate packaged', 'sha256': checksum, 'members': len(payload)}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('package')
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--release-id', required=True)
    p.add_argument('--target', choices=sorted(TARGETS))
    p.add_argument('--provenance', type=Path)
    p.add_argument('--dependency-notices', type=Path)
    p.add_argument('--runtime', action='append', default=[])
    p = sub.add_parser('sanitize')
    p.add_argument('--binary', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('inspect')
    p.add_argument('archive', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'inspect':
            manifest, payload = read_archive(args.archive)
            print(json.dumps({'release_id': manifest['release_id'], 'members': len(payload), 'status': 'archive verified; binary execution not checked'}))
            return 0
        if args.command == 'sanitize':
            print(json.dumps(sanitize_binary(args.binary, args.output), indent=2))
            return 0
        print(json.dumps(package(args)))
        return 0
    except (OSError, ReleaseError, subprocess.SubprocessError, ValueError, struct.error) as error:
        print(str(error) if isinstance(error, ReleaseError) else 'release: I/O failure', file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())
