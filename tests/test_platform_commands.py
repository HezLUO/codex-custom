"""Cross-target command fixtures; these do not claim real OS acceptance."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest

import test_precompiled as fixtures


class CrossTargetCommands(unittest.TestCase):
    tool = fixtures.PrecompiledTests.tool
    command = fixtures.PrecompiledTests.command
    archive = fixtures.PrecompiledTests.archive

    def prepare(self, target):
        fixtures.PrecompiledTests.setUp(self)
        windows, linux = 'windows' in target, 'linux' in target
        system = 'Windows' if windows else 'Linux' if linux else 'Darwin'
        machine = 'AMD64' if windows else 'aarch64' if target.startswith('aarch64') and linux else 'x86_64'
        source = Path(self.env['PYTHONPATH']) / 'sitecustomize.py'
        text = source.read_text().replace("lambda: 'Darwin'", 'lambda: ' + repr(system)).replace("lambda: 'arm64'", 'lambda: ' + repr(machine))
        text = text.replace("str(command[0]).endswith('/bin/codex') and Path(command[0]).read_bytes().startswith(bytes.fromhex('cffaedfe'))", "str(command[0]).endswith(('/bin/codex', '/bin/codex.exe')) and b'fixture-version=' in Path(command[0]).read_bytes()")
        source.write_text(text)
        suffix = '.exe' if windows else ''
        if windows:
            for name in ('bin/codex', 'bin/codex-code-mode-host', 'codex-path/rg'):
                (self.official / name).rename(self.official / (name + suffix))
            for name in ('codex-command-runner.exe', 'codex-windows-sandbox-setup.exe'):
                item = self.official / 'codex-resources' / name; item.write_bytes(b'helper'); item.chmod(0o755)
        if linux:
            helper = self.official / 'codex-resources/bwrap'; helper.write_bytes(b'exact-bwrap'); helper.chmod(0o755)
        if not target.endswith('apple-darwin'): self.tool('codesign', '#!/bin/sh\nexit 1\n')
        metadata = json.loads((self.official / 'codex-package.json').read_text())
        metadata.update(target=target, entrypoint='bin/codex' + suffix)
        (self.official / 'codex-package.json').write_text(json.dumps(metadata))
        self.env['CODEX_OFFICIAL_BIN'] = str(self.official / metadata['entrypoint'])
        return metadata

    def payload(self, target, bad_bwrap=False):
        def mutate(payload):
            manifest = json.loads(payload['release.json']); manifest['target'] = target
            if 'windows' in target:
                data = bytearray(128); data[:2] = b'MZ'; struct.pack_into('<I', data, 60, 64)
                data[64:70] = b'PE\0\0\x64\x86'; data[88:90] = b'\x0b\x02'
                payload.pop('bin/codex'); name = 'bin/codex.exe'
            elif 'linux' in target:
                data = bytearray(64); data[:6] = b'\x7fELF\x02\x01'
                struct.pack_into('<H', data, 18, 183 if target.startswith('aarch64') else 62); name = 'bin/codex'
                manifest['provenance']['official_bwrap_sha256'] = hashlib.sha256(b'wrong' if bad_bwrap else b'exact-bwrap').hexdigest()
            else:
                data = bytearray(bytes.fromhex('cffaedfe07000001') + bytes(24)); name = 'bin/codex'
            payload[name] = bytes(data) + b'fixture-version=0.164.0'
            manifest['signing'] = ('ad-hoc' if 'darwin' in target else 'unsigned') + '; no publisher identity or notarization'
            manifest['members'] = {n: dict(sha256=hashlib.sha256(d).hexdigest(), mode=0o755 if n in ('bin/codex', 'bin/codex.exe', 'bootstrap.sh') else 0o644) for n, d in payload.items() if n != 'release.json'}
            payload['release.json'] = json.dumps(manifest).encode()
        return self.archive(mutate)

    def test_install_launch_and_safe_purge_for_each_new_target(self):
        for target in ('x86_64-apple-darwin', 'x86_64-unknown-linux-musl', 'aarch64-unknown-linux-musl', 'x86_64-pc-windows-msvc'):
            with self.subTest(target=target):
                metadata = self.prepare(target); original = Path(self.env['CODEX_OFFICIAL_BIN']).read_bytes()
                result = self.command(*self.payload(target)); self.assertEqual(result.returncode, 0, result.stderr)
                state = self.root / 'state'
                release = state / 'releases' / json.loads((state / 'current.json').read_text())['release'] if 'windows' in target else (state / 'current').resolve()
                result = subprocess.run([sys.executable, str(release / 'runtime/precompiled.py'), '--launch', '--', 'resume', 'a b', '$(false)'], env=self.env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['args'], ['resume', 'a b', '$(false)'])
                parent = self.official.parent / 'codex-custom' / release.name
                sentinel = parent / 'foreign.txt'; sentinel.write_text('keep')
                result = self.command('--uninstall', '--purge'); self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(sentinel.read_text(), 'keep'); self.assertFalse((parent / 'package').exists())
                self.assertEqual(Path(self.env['CODEX_OFFICIAL_BIN']).read_bytes(), original)

    def test_legacy_windows_launcher_migration_rolls_back_with_failed_activation(self):
        target = 'x86_64-pc-windows-msvc'; self.prepare(target)
        result = self.command(*self.payload(target)); self.assertEqual(result.returncode, 0, result.stderr)
        launcher = self.bin / 'codex-custom.cmd'; current = launcher.read_text()
        legacy = current.replace('@(goto) 2>nul & ', '@echo off\nrem codex-custom-precompiled-v1\n')
        self.assertNotEqual(current, legacy)
        original = legacy.replace('\n', '\r\n').encode(); launcher.write_bytes(original)
        pointer = self.root / 'state/current.json'; before = pointer.read_bytes()
        adapter = Path(self.env['PYTHONPATH']) / 'sitecustomize.py'
        adapter.write_text(adapter.read_text().replace("str(destination).endswith('/current')", "str(destination).endswith(('/current', '/current.json'))"))
        self.env['FIXTURE_FAIL_ACTIVATION'] = '1'
        result = self.command(*self.payload(target)); self.assertNotEqual(result.returncode, 0)
        self.assertEqual(launcher.read_bytes(), original)
        self.assertEqual(pointer.read_bytes(), before)
        del self.env['FIXTURE_FAIL_ACTIVATION']
        result = self.command(*self.payload(target)); self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(launcher.read_text(), current)
        launcher.write_bytes(original); before = pointer.read_bytes()
        adapter.write_text(adapter.read_text().replace(
            "        raise PermissionError('fixture activation denied')",
            "        Path(os.environ['FIXTURE_FOREIGN_ON_ROLLBACK']).write_bytes(b'foreign-after-migration')\n        raise PermissionError('fixture activation denied')"))
        self.env['FIXTURE_FAIL_ACTIVATION'] = '1'
        self.env['FIXTURE_FOREIGN_ON_ROLLBACK'] = str(launcher)
        result = self.command(*self.payload(target)); self.assertNotEqual(result.returncode, 0)
        self.assertEqual(launcher.read_bytes(), b'foreign-after-migration')
        self.assertEqual(pointer.read_bytes(), before)

    def test_launcher_replaced_during_staging_is_not_overwritten(self):
        target = 'x86_64-pc-windows-msvc'; self.prepare(target)
        result = self.command(*self.payload(target)); self.assertEqual(result.returncode, 0, result.stderr)
        launcher = self.bin / 'codex-custom.cmd'
        pointer = self.root / 'state/current.json'; before = pointer.read_bytes()
        adapter = Path(self.env['PYTHONPATH']) / 'sitecustomize.py'
        marker = "        version = re.search"
        adapter.write_text(adapter.read_text().replace(marker,
            "        if os.environ.get('FIXTURE_SWAP_LAUNCHER'): Path(os.environ['FIXTURE_SWAP_LAUNCHER']).write_bytes(b'foreign-sentinel')\n" + marker))
        self.env['FIXTURE_SWAP_LAUNCHER'] = str(launcher)
        result = self.command(*self.payload(target))
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(launcher.read_bytes(), b'foreign-sentinel')
        self.assertEqual(pointer.read_bytes(), before)

    def test_linux_wrong_build_time_bwrap_digest_is_refused_before_activation(self):
        self.prepare('x86_64-unknown-linux-musl')
        result = self.command(*self.payload('x86_64-unknown-linux-musl', bad_bwrap=True))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('sandbox resource differs', result.stderr)
        self.assertFalse((self.root / 'state/current').exists())


if __name__ == '__main__': unittest.main()
