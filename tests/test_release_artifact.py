"""Release archive command behavior; fixtures carry no real credentials."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/release_artifact.py'

class ReleaseArchiveTests(unittest.TestCase):
    def test_rejects_private_binary_strings_without_printing_them(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary = root / 'frontend'
            secret = b'/' + b'Users' + b'/fixture-private-name/source/file.rs'
            binary.write_bytes(secret)
            result = subprocess.run([sys.executable, str(SCRIPT), 'package', '--binary', str(binary), '--output', str(root / 'candidate.tar.gz'), '--release-id', 'test'], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'personal-home-path', result.stderr)
            self.assertNotIn(secret, result.stderr)
            self.assertFalse((root / 'candidate.tar.gz').exists())

    def test_inspect_accepts_exact_manifest_and_rejects_extra_member(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'candidate.tar.gz'
            payload = {'bin/codex': b'fixture executable', 'LICENSE': b'license', 'NOTICE': b'notice', 'DEPENDENCY-NOTICES.txt': b'dependency notices'}
            metadata = {'schema': 1, 'release_id': 'test', 'official_version': '0.164.0', 'target': 'aarch64-apple-darwin', 'layout_version': 1, 'source_commit': '6aaac694803004a63c6f393d153c96d22521a6b9', 'patch_sha256': 'a' * 64, 'signing': 'ad-hoc; no publisher identity or notarization', 'provenance': {'binary_sha256': 'b' * 64}, 'members': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': 493 if name == 'bin/codex' else 420} for name, data in payload.items()}}
            payload['release.json'] = json.dumps(metadata).encode()
            def write(extra=False):
                with tarfile.open(archive, 'w:gz') as tar:
                    for name, data in payload.items():
                        item = tarfile.TarInfo(name)
                        item.size = len(data)
                        item.mode = 493 if name == 'bin/codex' else 420
                        tar.addfile(item, io.BytesIO(data))
                    if extra:
                        tar.addfile(tarfile.TarInfo('../escape'))
            write()
            command = [sys.executable, str(SCRIPT), 'inspect', str(archive)]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            write(True)
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'archive member', result.stderr)

    def test_inspect_rejects_metadata_version_and_changed_contents(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'candidate.tar.gz'
            payload = {'bin/codex': b'frontend', 'LICENSE': b'license', 'NOTICE': b'notice', 'DEPENDENCY-NOTICES.txt': b'notices'}
            manifest = {'schema': 1, 'release_id': 'test', 'official_version': '0.164.0', 'target': 'aarch64-apple-darwin', 'layout_version': 1, 'source_commit': '6aaac694803004a63c6f393d153c96d22521a6b9', 'patch_sha256': 'a' * 64, 'signing': 'ad-hoc; no publisher identity or notarization', 'provenance': {}, 'members': {name: {'sha256': hashlib.sha256(data).hexdigest(), 'mode': 493 if name == 'bin/codex' else 420} for name, data in payload.items()}}
            for mutation, message in [('version', b'metadata rejected'), ('content', b'digest or mode mismatch')]:
                metadata = dict(manifest)
                contents = dict(payload)
                if mutation == 'version':
                    metadata['official_version'] = '0.165.0'
                else:
                    contents['bin/codex'] = b'changed'
                contents['release.json'] = json.dumps(metadata).encode()
                with tarfile.open(archive, 'w:gz') as tar:
                    for name, data in contents.items():
                        item = tarfile.TarInfo(name)
                        item.size, item.mode = len(data), 493 if name == 'bin/codex' else 420
                        tar.addfile(item, io.BytesIO(data))
                result = subprocess.run([sys.executable, str(SCRIPT), 'inspect', str(archive)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)

    def test_new_credential_and_session_fixtures_fail_without_echoing_values(self):
        fixtures = [b'gh' + b'p_' + b'fixturesecretvalue' * 3,
                    b'12345678' + b'-1234-4123-8123-' + b'123456789abc']
        for fixture in fixtures:
            with tempfile.TemporaryDirectory() as temp:
                binary = Path(temp) / 'frontend'
                binary.write_bytes(fixture)
                result = subprocess.run([sys.executable, str(SCRIPT), 'package', '--binary', str(binary), '--output', str(Path(temp) / 'candidate.tar.gz'), '--release-id', 'test'], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'privacy:', result.stderr)
                self.assertNotIn(fixture, result.stderr)

if __name__ == '__main__':
    unittest.main()
