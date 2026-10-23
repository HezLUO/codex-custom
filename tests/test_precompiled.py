"""User command seam; tool fixtures stand in only for OS signing and execution."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PrecompiledTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="precompiled ' space ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tools = self.root / 'tools'
        self.tools.mkdir()
        self.tool('codesign', '#!/bin/sh\ncase "$1" in -dv) echo Signature=adhoc >&2;; esac\n')
        self.tool('uname', '#!/bin/sh\ncase "$1" in -s) echo Darwin;; -m) echo arm64;; esac\n')
        self.official = self.root / 'home/.codex/packages/standalone/releases/official'
        for name in ('bin', 'codex-path', 'codex-resources/voice'):
            (self.official / name).mkdir(parents=True)
        for name in ('bin/codex', 'bin/codex-code-mode-host', 'codex-path/rg'):
            p = self.official / name
            p.write_text('#!/bin/sh\necho codex-cli 0.164.0\n')
            p.chmod(0o755)
        (self.official / 'codex-resources/voice/data').write_text('resource')
        (self.official / 'codex-package.json').write_text(json.dumps(dict(layoutVersion=1,version='0.164.0',target='aarch64-apple-darwin',variant='codex',entrypoint='bin/codex',resourcesDir='codex-resources',pathDir='codex-path')))
        # Mach-O OS boundary: executable invocations are handled by fixture Python's subprocess adapter.
        self.env = dict(os.environ, CODEX_HOME=str(self.root / 'home/.codex'), CODEX_OFFICIAL_BIN=str(self.official / 'bin/codex'), CODEX_CUSTOM_STATE_DIR=str(self.root / 'state'), PATH=str(self.tools) + ':' + os.environ['PATH'])
        self.bin = self.root / 'commands'
        adapter = self.root / 'adapter'
        adapter.mkdir()
        (adapter / 'sitecustomize.py').write_text("""import os, platform, subprocess, json, re, time
from pathlib import Path
platform.system = lambda: 'Darwin'
platform.machine = lambda: 'arm64'
original = subprocess.run
def run(command, **kwargs):
    if str(command[0]).endswith('/bin/codex') and Path(command[0]).read_bytes().startswith(bytes.fromhex('cffaedfe')):
        version = re.search(rb'fixture-version=([0-9.]+)', Path(command[0]).read_bytes()).group(1)
        return subprocess.CompletedProcess(command, 0, b'codex-cli ' + version + b'\\n', b'')
    return original(command, **kwargs)
subprocess.run = run
def execute(path, arguments, environment):
    if environment.get('FIXTURE_HOLD_FILE'):
        hold = Path(environment['FIXTURE_HOLD_FILE'])
        hold.write_text('running')
        while hold.exists():
            time.sleep(0.01)
    print(json.dumps({'args': arguments[1:], 'status': environment.get('CODEX_CUSTOM_STATUS_LINE')}))
    raise SystemExit(0)
os.execve = execute
original_replace = os.replace
def replace(source, destination):
    if os.environ.get('FIXTURE_FAIL_ACTIVATION') and str(destination).endswith('/current'):
        raise PermissionError('fixture activation denied')
    return original_replace(source, destination)
os.replace = replace
""")
        self.env['PYTHONPATH'] = str(adapter)

    def tool(self, name, text):
        p = self.tools / name
        p.write_text(text)
        p.chmod(0o755)

    def command(self, *args):
        return subprocess.run([sys.executable, str(ROOT / 'scripts/install.py'), '--bin-dir', str(self.bin), *args], env=self.env, capture_output=True, text=True)

    def archive(self, mutation=None):
        payload = {'bin/codex': bytes.fromhex('cffaedfe0c000001') + bytes(32) + b'fixture-version=0.164.0', 'LICENSE': b'license', 'NOTICE': b'notice', 'DEPENDENCY-NOTICES.txt': b'dependencies'}
        for name in ('precompiled.py', 'release_artifact.py'):
            payload['runtime/' + name] = (ROOT / 'scripts' / name).read_bytes()
        payload['runtime/update-codex-custom.py'] = (ROOT / 'update-codex-custom.py').read_bytes()
        for name in ('bootstrap.py', 'bootstrap.sh'):
            payload[name] = (ROOT / name).read_bytes()
        manifest = dict(schema=1, official_version='0.164.0', target='aarch64-apple-darwin', layout_version=1, release_id='fixture.1', source_commit='a' * 40, patch_sha256='b' * 64, provenance={}, signing='ad-hoc; no publisher identity or notarization', members={name: dict(sha256=hashlib.sha256(data).hexdigest(), mode=0o755 if name in ('bin/codex', 'bootstrap.sh') else 0o644) for name, data in payload.items()})
        payload['release.json'] = json.dumps(manifest).encode()
        if mutation:
            mutation(payload)
        archive = self.root / 'release.tar.gz'
        with tarfile.open(archive, 'w:gz', format=tarfile.USTAR_FORMAT) as stream:
            for name, data in payload.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(data)
                entry.mode = 0o755 if name in ('bin/codex', 'bootstrap.sh') else 0o644
                stream.addfile(entry, io.BytesIO(data))
        return ['--archive', str(archive), '--sha256', hashlib.sha256(archive.read_bytes()).hexdigest()]

    def test_local_install_and_offline_launch_preserve_arguments(self):
        result = self.command(*self.archive())
        self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(self.bin / 'codex-custom'), 'resume', 'a b', '$(false)'], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['args'], ['resume', 'a b', '$(false)'])
        self.assertIn('context-details', value['status'])

    def test_repeat_install_and_custom_status_preserve_official_resources(self):
        before = (self.official / 'bin/codex').read_bytes()
        args = self.archive()
        for _ in range(2):
            result = self.command(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        environment = dict(self.env, CODEX_CUSTOM_STATUS_LINE='["context-details"]')
        result = subprocess.run([str(self.bin / 'codex-custom'), '--version'], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'], '["context-details"]')
        self.assertEqual((self.official / 'bin/codex').read_bytes(), before)

    def test_corrupt_archive_cannot_replace_active_release(self):
        args = self.archive()
        self.assertEqual(self.command(*args).returncode, 0)
        active = (self.root / 'state/current').readlink()
        args = self.archive(lambda payload: payload.update({'../escape': b'bad'}))
        result = self.command(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('archive member rejected', result.stderr)
        self.assertEqual((self.root / 'state/current').readlink(), active)
        self.assertFalse((self.root / 'escape').exists())

    def test_foreign_command_and_broken_link_are_preserved(self):
        args = self.archive()
        self.bin.mkdir()
        target = self.bin / 'codex-custom'
        for symlink in (False, True):
            if symlink:
                target.symlink_to('missing')
            else:
                target.write_text('unmanaged')
            result = self.command(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.lexists(target))
            target.unlink()

    def test_installed_helper_or_runtime_tampering_stops_offline_launch(self):
        args = self.archive()
        self.assertEqual(self.command(*args).returncode, 0)
        helper = self.root / 'state/current/package/codex-path/rg'
        helper.write_text('changed')
        result = subprocess.run([str(self.bin / 'codex-custom'), '--version'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('resources changed', result.stderr)

    def test_signature_failure_and_checksum_failure_keep_active_install(self):
        args = self.archive()
        self.assertEqual(self.command(*args).returncode, 0)
        current = (self.root / 'state/current').readlink()
        wrong = args[:-1] + ['0' * 64]
        self.assertNotEqual(self.command(*wrong).returncode, 0)
        self.tool('codesign', '#!/bin/sh\nexit 1\n')
        self.assertNotEqual(self.command(*args).returncode, 0)
        self.assertEqual((self.root / 'state/current').readlink(), current)

    def test_missing_official_resources_and_wrong_native_location_stop_install(self):
        args = self.archive()
        (self.official / 'codex-path/rg').unlink()
        self.assertNotEqual(self.command(*args).returncode, 0)
        self.assertFalse((self.bin / 'codex-custom').exists())
        self.env['CODEX_HOME'] = str(self.root / 'different-home')
        (self.official / 'codex-path/rg').write_text('restored')
        (self.official / 'codex-path/rg').chmod(0o755)
        result = self.command(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('CODEX_HOME', result.stderr)

    def test_concurrent_operation_refuses_without_changing_current(self):
        import fcntl
        args = self.archive()
        self.assertEqual(self.command(*args).returncode, 0)
        current = (self.root / 'state/current').readlink()
        with (self.root / 'state/update.lock').open('a') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.command(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('active', result.stderr)
        self.assertEqual((self.root / 'state/current').readlink(), current)

    def test_owned_uninstall_is_repeatable_and_retains_data_by_default(self):
        self.assertEqual(self.command(*self.archive()).returncode, 0)
        current = (self.root / 'state/current').resolve()
        private = self.root / 'home/.codex/private-config'
        private.write_text('keep private data')
        official = (self.official / 'bin/codex').read_bytes()
        for _ in range(2):
            result = self.command('--uninstall')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((self.bin / 'codex-custom').exists())
        self.assertTrue(current.exists())
        self.assertEqual(private.read_text(), 'keep private data')
        self.assertEqual((self.official / 'bin/codex').read_bytes(), official)

    def test_optional_cleanup_removes_only_receipted_packages(self):
        self.assertEqual(self.command(*self.archive()).returncode, 0)
        current = (self.root / 'state/current').resolve()
        target = (current / 'package').resolve()
        other = target.parent.parent / 'another-installation'
        other.mkdir()
        (other / 'keep').write_text('other installation')
        result = self.command('--uninstall', '--purge')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(current.exists())
        self.assertFalse(target.exists())
        self.assertEqual((other / 'keep').read_text(), 'other installation')
        self.assertTrue((self.official / 'bin/codex').exists())
        self.assertEqual(self.command('--uninstall', '--purge').returncode, 0)

    def test_cleanup_refuses_running_session_and_foreign_receipt_without_deletion(self):
        import time
        self.assertEqual(self.command(*self.archive()).returncode, 0)
        current = (self.root / 'state/current').resolve()
        hold = self.root / 'running'
        env = dict(self.env, FIXTURE_HOLD_FILE=str(hold))
        child = subprocess.Popen([str(self.bin / 'codex-custom')], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(lambda: child.kill() if child.poll() is None else None)
        deadline = time.monotonic() + 10
        while not hold.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue(hold.exists())
        result = self.command('--uninstall', '--purge')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('session is running', result.stderr)
        self.assertTrue(current.exists())
        self.assertTrue((self.bin / 'codex-custom').exists())
        hold.unlink()
        child.communicate(timeout=10)
        receipt_path = current / 'receipt.json'
        receipt = json.loads(receipt_path.read_text())
        receipt['installation_id'] = 'foreign'
        receipt_path.write_text(json.dumps(receipt))
        result = self.command('--uninstall')
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue((self.bin / 'codex-custom').exists())

    def test_uninstall_refuses_replaced_launcher_and_broken_current_and_symlink_state(self):
        self.assertEqual(self.command(*self.archive()).returncode, 0)
        launcher = self.bin / 'codex-custom'
        owned = launcher.read_text()
        for symlink in (False, True):
            launcher.unlink()
            if symlink:
                launcher.symlink_to('missing')
            else:
                launcher.write_text('foreign command')
            result = self.command('--uninstall', '--purge')
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(os.path.lexists(launcher))
        launcher.unlink()
        launcher.write_text(owned)
        current = self.root / 'state/current'
        current.unlink()
        current.symlink_to('missing')
        self.assertNotEqual(self.command('--uninstall').returncode, 0)
        self.assertTrue(launcher.exists())
        state = self.root / 'state'
        moved = self.root / 'moved-state'
        state.rename(moved)
        state.symlink_to(moved)
        self.assertNotEqual(self.command('--uninstall', '--purge').returncode, 0)
        self.assertTrue(launcher.exists())

    def test_permission_or_official_change_during_install_preserves_current(self):
        args = self.archive()
        self.assertEqual(self.command(*args).returncode, 0)
        before = (self.root / 'state/current').readlink()
        self.env['FIXTURE_FAIL_ACTIVATION'] = '1'
        result = self.command(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / 'state/current').readlink(), before)
        del self.env['FIXTURE_FAIL_ACTIVATION']
        self.tool('codesign', '#!/bin/sh\ncase "$1" in --verify) echo changed >> "$CODEX_OFFICIAL_BIN/../../codex-path/rg";; -dv) echo Signature=adhoc >&2;; esac\n')
        # Use a canonical sibling path; shell cannot traverse through a file.
        text = (self.tools / 'codesign').read_text().replace('$CODEX_OFFICIAL_BIN/../../codex-path/rg', str(self.official / 'codex-path/rg'))
        (self.tools / 'codesign').write_text(text)
        result = self.command(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('changed during installation', result.stderr)
        self.assertEqual((self.root / 'state/current').readlink(), before)
        self.assertTrue((self.bin / 'codex-custom').exists())

    def test_tampered_installed_downloader_is_never_executed(self):
        self.assertEqual(self.command(*self.archive()).returncode, 0)
        current = (self.root / 'state/current').resolve()
        sentinel = self.root / 'executed'
        (current / 'bootstrap.py').write_text('from pathlib import Path; Path(' + repr(str(sentinel)) + ').touch()')
        result = subprocess.run([str(self.bin / 'codex-custom'), '--update'], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('integrity check failed', result.stderr)
        self.assertFalse(sentinel.exists())
        self.assertEqual((self.root / 'state/current').resolve(), current)

    def test_failed_first_activation_can_retry_without_manual_state_cleanup(self):
        args = self.archive()
        self.env['FIXTURE_FAIL_ACTIVATION'] = '1'
        self.assertNotEqual(self.command(*args).returncode, 0)
        self.assertFalse((self.bin / 'codex-custom').exists())
        self.assertFalse(os.path.lexists(self.root / 'state/current'))
        del self.env['FIXTURE_FAIL_ACTIVATION']
        result = self.command(*args)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_archive_stops_without_installing_or_compiling(self):
        result = self.command('--archive', str(self.root / 'missing'), '--sha256', '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Installation stopped', result.stderr)
        self.assertFalse((self.bin / 'codex-custom').exists())

    def test_oversized_local_archive_is_rejected_before_digest_or_extraction(self):
        archive = self.root / 'oversized.tar.gz'
        with archive.open('wb') as stream:
            stream.truncate(256 * 1024 * 1024 + 1)
        result = self.command('--archive', str(archive), '--sha256', '0' * 64)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('archive size limit', result.stderr)
        self.assertFalse((self.root / 'state').exists())

if __name__ == '__main__':
    unittest.main()
