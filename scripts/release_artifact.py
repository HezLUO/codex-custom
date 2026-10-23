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

ROOT = Path(__file__).resolve().parents[1]
RULES = {
    'personal-home-path': rb'/(?:Users|home)/[^\s/<>"\x27]+',
    'machine-temporary-path': rb'/(?:private/)?var/folders/[^\s\x00]+',
    'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
    'credential': rb'(?i)(?:sk-[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{20,}|AKIA[A-Z0-9]{16}|Bearer\s+[a-z0-9._-]{20,})',
    'session-identifier': rb'(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b',
}
# Static upstream literals can be reviewed by SHA-256, never raw sensitive values.
REVIEWED_LITERALS = {
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
RUNTIME_MEMBERS = {'runtime/precompiled.py', 'runtime/release_artifact.py', 'runtime/update-codex-custom.py', 'bootstrap.sh'}

class ReleaseError(ValueError):
    pass

def digest(data):
    return hashlib.sha256(data).hexdigest()

def privacy_check(data):
    for label, pattern in RULES.items():
        for match in re.finditer(pattern, data):
            if digest(match.group()) not in REVIEWED_LITERALS:
                raise ReleaseError('privacy: ' + label)

def read_archive(path):
    """Return (validated manifest, payload bytes); never extract untrusted paths."""
    payload = {}
    modes = {}
    try:
        with tarfile.open(path, 'r:gz') as archive:
            for item in archive:
                if (not item.isfile() or item.name not in BASE_MEMBERS | RUNTIME_MEMBERS | {'release.json'}
                        or item.name in payload or item.size > 512 * 1024 * 1024
                        or item.mode not in (0o644, 0o755) or item.pax_headers):
                    raise ReleaseError('archive member rejected')
                payload[item.name] = archive.extractfile(item).read()
                modes[item.name] = item.mode
                privacy_check(payload[item.name])
        manifest = json.loads(payload.pop('release.json'))
        if (manifest.get('schema') != 1 or manifest.get('official_version') != '0.164.0'
                or manifest.get('target') != 'aarch64-apple-darwin' or manifest.get('layout_version') != 1
                or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}', manifest.get('release_id', ''))
                or not re.fullmatch(r'[0-9a-f]{40}', manifest.get('source_commit', ''))
                or not re.fullmatch(r'[0-9a-f]{64}', manifest.get('patch_sha256', ''))
                or not isinstance(manifest.get('provenance'), dict)
                or manifest.get('signing') != 'ad-hoc; no publisher identity or notarization'):
            raise ReleaseError('release metadata rejected')
        members = manifest['members']
        if set(members) != set(payload) or not BASE_MEMBERS <= set(payload):
            raise ReleaseError('archive member manifest mismatch')
        for name, data in payload.items():
            if members[name] != {'sha256': digest(data), 'mode': modes[name]}:
                raise ReleaseError('archive member digest or mode mismatch')
        if modes['bin/codex'] != 0o755:
            raise ReleaseError('frontend must be executable')
        return manifest, payload
    except (tarfile.TarError, KeyError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ReleaseError('invalid release archive') from error

def verify_binary(path, expected_version='0.164.0'):
    data = Path(path).read_bytes()
    privacy_check(data)
    if len(data) < 32 or data[:8] != bytes.fromhex('cffaedfe0c000001'):
        raise ReleaseError('frontend architecture must be thin Mach-O arm64')
    for command in (['codesign', '--verify', '--strict', str(path)], [str(Path(path).resolve()), '--version']):
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if result.returncode:
            raise ReleaseError('frontend signature or version verification failed')
        if command[-1] == '--version' and result.stdout.strip() != ('codex-cli ' + expected_version).encode():
            raise ReleaseError('frontend version mismatch')
    info = subprocess.run(['codesign', '-dv', str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if info.returncode or b'Signature=adhoc' not in info.stderr:
        raise ReleaseError('frontend signing policy mismatch')
    return digest(data)

def sanitize_binary(source, output):
    """Redact home-prefix literals only in Mach-O constant data, then re-sign copy."""
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve() or output.exists():
        raise ReleaseError('sanitized output must be a new separate file')
    data = source.read_bytes()
    verify_data = data
    if data[:8] != bytes.fromhex('cffaedfe0c000001'):
        raise ReleaseError('frontend architecture must be thin Mach-O arm64')
    ranges = []
    offset = 32
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, offset)
        if command == 0x19:
            for index in range(struct.unpack_from('<I', data, offset + 64)[0]):
                section = struct.unpack_from('<16s16sQQIIIIIIII', data, offset + 72 + index * 80)
                if section[0].rstrip(b'\0') in (b'__cstring', b'__const') and section[1].rstrip(b'\0') == b'__TEXT':
                    ranges.append((section[4], section[4] + section[3]))
        offset += size
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
    binary_hash = verify_binary(args.binary)
    if not args.provenance or not args.dependency_notices:
        raise ReleaseError('provenance and dependency notices required')
    provenance = json.loads(args.provenance.read_text())
    if provenance.get('binary_sha256') != binary_hash:
        raise ReleaseError('provenance binary digest mismatch')
    payload = {'bin/codex': args.binary.read_bytes(), 'LICENSE': (ROOT / 'LICENSE').read_bytes(),
               'NOTICE': (ROOT / 'NOTICE').read_bytes(), 'DEPENDENCY-NOTICES.txt': args.dependency_notices.read_bytes()}
    for component in args.runtime:
        name, filename = component.split('=', 1)
        if name not in RUNTIME_MEMBERS or name in payload:
            raise ReleaseError('runtime member rejected')
        payload[name] = Path(filename).read_bytes()
    manifest = {'schema': 1, 'release_id': args.release_id, 'official_version': '0.164.0',
                'target': 'aarch64-apple-darwin', 'layout_version': 1,
                'source_commit': '6aaac694803004a63c6f393d153c96d22521a6b9',
                'patch_sha256': digest((ROOT / 'patches/codex-0.164.0-context-details.patch').read_bytes()),
                'signing': 'ad-hoc; no publisher identity or notarization', 'provenance': provenance,
                'members': {name: {'sha256': digest(data), 'mode': 0o755 if name in ('bin/codex', 'bootstrap.sh') else 0o644} for name, data in payload.items()}}
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
