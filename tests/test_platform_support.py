"""Platform selection, executable admission and Windows ownership boundaries."""
import base64
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import release_artifact as artifact
portable = artifact
sys.path.insert(0, str(ROOT))
import bootstrap
import precompiled


class PlatformTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Requires the actual Windows command processor')
    def test_native_cmd_launches_batch_with_spaced_paths_and_arguments(self):
        spec = importlib.util.spec_from_file_location('native_acceptance', ROOT / 'scripts/accept-platform.py')
        acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)
        for prefix, filename in [('codex-cmd-fixture-', 'fixture.cmd'), ('codex cmd fixture ', 'fixture launcher.cmd')]:
            with self.subTest(path=filename), tempfile.TemporaryDirectory(prefix=prefix) as temporary:
                launcher = Path(temporary) / filename
                launcher.write_bytes(b'@echo fixture-native-ok %*\r\n')
                command = acceptance.launcher_command(launcher, ['--version', 'arg with space'], True)
                result = subprocess.run(command, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
                self.assertIn(b'fixture-native-ok --version "arg with space"', result.stdout)

    def test_bootstrap_and_runtime_select_exact_targets_and_reject_unknown_hosts(self):
        cases = [('Darwin', 'arm64', 'aarch64-apple-darwin'),
                 ('Darwin', 'x86_64', 'x86_64-apple-darwin'),
                 ('Linux', 'x86_64', 'x86_64-unknown-linux-musl'),
                 ('Linux', 'aarch64', 'aarch64-unknown-linux-musl'),
                 ('Windows', 'AMD64', 'x86_64-pc-windows-msvc')]
        for system, machine, target in cases:
            with self.subTest(target=target), patch.object(portable.platform, 'system', return_value=system), patch.object(portable.platform, 'machine', return_value=machine):
                self.assertEqual(portable.host_target(), target)
                self.assertEqual(bootstrap.host_target(), target)
        for system, machine in [('Windows', 'ARM64'), ('Linux', 'i686'), ('FreeBSD', 'x86_64')]:
            with patch.object(portable.platform, 'system', return_value=system), patch.object(portable.platform, 'machine', return_value=machine):
                with self.assertRaises(ValueError): portable.host_target()
                with self.assertRaises(ValueError): bootstrap.host_target()

    def test_binary_headers_reject_wrong_machine_and_truncated_pe(self):
        elf = bytearray(64); elf[:6] = b'\x7fELF\x02\x01'; struct.pack_into('<H', elf, 18, 62)
        pe = bytearray(128); pe[:2] = b'MZ'; struct.pack_into('<I', pe, 60, 64); pe[64:70] = b'PE\0\0\x64\x86'; pe[88:90] = b'\x0b\x02'
        samples = {'x86_64-unknown-linux-musl': elf, 'x86_64-pc-windows-msvc': pe,
                   'x86_64-apple-darwin': bytes.fromhex('cffaedfe07000001') + bytes(24),
                   'aarch64-apple-darwin': bytes.fromhex('cffaedfe0c000001') + bytes(24)}
        for target, data in samples.items():
            portable.check_architecture(data, target)
            for other in set(samples) - {target}:
                with self.assertRaises(ValueError): portable.check_architecture(data, other)
        with self.assertRaises(ValueError): portable.check_architecture(pe[:80], 'x86_64-pc-windows-msvc')

    def test_windows_private_paths_are_rejected_in_ascii_and_utf16(self):
        for value in [b'C:\\Users\\private-person\\source.rs', 'C:\\Users\\private-person\\source.rs'.encode('utf-16-le')]:
            with self.assertRaises(artifact.ReleaseError): artifact.privacy_check(value)

    def test_windows_selection_and_launcher_do_not_create_symlinks_or_interpolate_state(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(portable, 'windows', return_value=True):
            state = Path(temporary) / 'percent% and space'
            state.mkdir(); (state / 'current.json').write_text(json.dumps({'release': 'valid.1-abcd'}))
            self.assertEqual(precompiled.current_release(state), state / 'releases/valid.1-abcd')
            command = precompiled.shim(state)
            self.assertNotIn(str(state), command)
            encoded = command.split("b64decode('", 1)[1].split("')", 1)[0]
            code = base64.b64decode(encoded).decode()
            compile(code, '<launcher>', 'exec')
            self.assertIn(repr(str(state)), code)
            for invalid in ('../other', '..', 'C:other', 'release\\other', '/absolute'):
                (state / 'current.json').write_text(json.dumps({'release': invalid}))
                with self.assertRaises(RuntimeError): precompiled.current_release(state)

    def test_staging_reseals_only_frontend_voice_digest_and_preserves_official_package(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); official = root / 'releases/official'; (official / 'bin').mkdir(parents=True)
            entrypoint = portable.entrypoint()
            (official / entrypoint).write_bytes(b'official')
            voice = official / 'codex-resources/voice/manifest.json'; voice.parent.mkdir(parents=True)
            original = {'schemaVersion': 1, 'buildCommit': 'fixed', 'sha256': {entrypoint: artifact.digest(b'official'), 'codex-resources/voice/data': 'unchanged'}}
            voice.write_text(json.dumps(original)); before = voice.read_bytes()
            release = root / 'state/release'; release.mkdir(parents=True); binary = root / 'custom'; binary.write_bytes(b'custom')
            updater = precompiled.package
            updater.stage_package(official, binary, release)
            result = json.loads((official.parent / 'codex-custom/release/package/codex-resources/voice/manifest.json').read_text())
            expected = json.loads(json.dumps(original)); expected['sha256'][entrypoint] = artifact.digest(b'custom')
            self.assertEqual(result, expected)
            self.assertEqual(voice.read_bytes(), before)
            self.assertEqual((official / entrypoint).read_bytes(), b'official')

    def test_native_locks_exclude_update_and_allow_shared_session_leases(self):
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / 'lease'
            script = ('import sys;from pathlib import Path;sys.path.insert(0,' + repr(str(ROOT / 'scripts'))
                      + ');import release_artifact as p;f=Path(sys.argv[1]).open("a+");'
                      + '\ntry:p.flock(f,int(sys.argv[2])|p.LOCK_NB)'
                      + '\nexcept BlockingIOError:sys.exit(3)')
            with lock.open('a+') as stream:
                portable.flock(stream, portable.LOCK_SH)
                for flag, expected in [(portable.LOCK_EX, 3), (portable.LOCK_SH, 0)]:
                    result = subprocess.run([sys.executable, '-c', script, str(lock), str(flag)], capture_output=True)
                    self.assertEqual(result.returncode, expected, result.stderr)
            result = subprocess.run([sys.executable, '-c', script, str(lock), str(portable.LOCK_EX)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_windows_staging_uses_regular_pointer_and_no_file_symlink(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(portable, 'host_target', return_value='x86_64-pc-windows-msvc'):
            root = Path(temporary); official = root / 'releases/official'; (official / 'bin').mkdir(parents=True)
            (official / 'bin/codex.exe').write_bytes(b'official'); release = root / 'state/release'; release.mkdir(parents=True)
            binary = root / 'custom.exe'; binary.write_bytes(b'custom')
            precompiled.package.stage_package(official, binary, release)
            target = official.parent / 'codex-custom/release/package'
            self.assertEqual(json.loads((release / 'package.json').read_text()), {'path': str(target.resolve())})
            self.assertEqual((target / 'bin/codex.exe').read_bytes(), b'custom')
            self.assertFalse((release / 'package').exists())
            self.assertFalse((release / 'codex').exists())


if __name__ == '__main__':
    unittest.main()
