"""Download/install command seam against a loopback release service."""
import functools
import hashlib
import http.server
import json
from pathlib import Path
import subprocess
import sys
import threading
import unittest

import test_precompiled as fixtures

ROOT = Path(__file__).resolve().parents[1]

class DownloadTests(unittest.TestCase):
    setUp = fixtures.PrecompiledTests.setUp
    tool = fixtures.PrecompiledTests.tool
    archive = fixtures.PrecompiledTests.archive
    local_command = fixtures.PrecompiledTests.command

    def service(self):
        folder = self.root / 'server'
        folder.mkdir()
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(folder)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        return folder, 'http://127.0.0.1:' + str(server.server_port)

    def publish(self, folder):
        args = self.archive()
        archive = Path(args[1])
        release = folder / 'official-0.164.0-aarch64-apple-darwin'
        release.mkdir(exist_ok=True)
        (release / 'codex-custom.tar.gz').write_bytes(archive.read_bytes())
        descriptor = dict(schema=1, official_version='0.164.0', target='aarch64-apple-darwin', layout_version=1,
                          release_id='fixture.1', archive='codex-custom.tar.gz', sha256=args[-1])
        (release / 'release.json').write_text(json.dumps(descriptor))
        return release

    def command(self, source, *args):
        return subprocess.run([sys.executable, str(ROOT / 'bootstrap.py'), '--release-source', source,
                               '--bin-dir', str(self.bin), *args], env=self.env, text=True, capture_output=True)

    def test_download_install_and_repeat_then_offline_launch(self):
        folder, source = self.service()
        self.publish(folder)
        for _ in range(2):
            result = self.command(source)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = subprocess.run([str(self.bin / 'codex-custom'), 'resume', 'a b', '$(false)'], env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['args'], ['resume', 'a b', '$(false)'])

    def test_explicit_custom_update_then_offline_launch(self):
        folder, source = self.service()
        release = self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        before = (self.root / 'state/current').readlink()
        def change(payload):
            manifest = json.loads(payload['release.json'])
            manifest['release_id'] = 'fixture.2'
            payload['release.json'] = json.dumps(manifest).encode()
        args = self.archive(change)
        (release / 'codex-custom.tar.gz').write_bytes(Path(args[1]).read_bytes())
        descriptor = json.loads((release / 'release.json').read_text())
        descriptor.update(release_id='fixture.2', sha256=args[-1])
        (release / 'release.json').write_text(json.dumps(descriptor))
        result = self.local_command('--update', '--release-source', source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual((self.root / 'state/current').readlink(), before)
        self.assertTrue((self.root / 'state' / before).exists())
        env = dict(self.env, CODEX_CUSTOM_RELEASE_SOURCE='http://127.0.0.1:1')
        result = subprocess.run([str(self.bin / 'codex-custom'), '--version'], env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_official_change_fetches_only_exact_release_and_preserves_old_on_failure(self):
        folder, source = self.service()
        self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        before = (self.root / 'state/current').readlink()
        official_meta = self.official / 'codex-package.json'
        meta = json.loads(official_meta.read_text())
        meta['version'] = '0.165.0'
        official_meta.write_text(json.dumps(meta))
        (self.official / 'bin/codex').write_text('#!/bin/sh\necho codex-cli 0.165.0\n')
        env = dict(self.env, CODEX_CUSTOM_RELEASE_SOURCE=source)
        def launch():
            return subprocess.run([str(self.bin / 'codex-custom'), '--version'], env=env, text=True, capture_output=True)
        result = launch()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('use official codex', result.stderr)
        self.assertEqual((self.root / 'state/current').readlink(), before)
        def change(payload):
            payload['bin/codex'] = payload['bin/codex'].replace(b'0.164.0', b'0.165.0')
            manifest = json.loads(payload['release.json'])
            manifest.update(official_version='0.165.0', release_id='fixture.2')
            manifest['members']['bin/codex']['sha256'] = hashlib.sha256(payload['bin/codex']).hexdigest()
            payload['release.json'] = json.dumps(manifest).encode()
        args = self.archive(change)
        release = folder / 'official-0.165.0-aarch64-apple-darwin'
        release.mkdir()
        (release / 'codex-custom.tar.gz').write_bytes(Path(args[1]).read_bytes())
        descriptor = dict(schema=1, official_version='0.165.0', target='aarch64-apple-darwin', layout_version=1,
                          release_id='fixture.2', archive='codex-custom.tar.gz', sha256=args[-1])
        (release / 'release.json').write_text(json.dumps(descriptor))
        result = launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual((self.root / 'state/current').readlink(), before)
        self.assertTrue((self.root / 'state' / before).exists())

    def test_uninstall_cannot_overtake_pending_update_download(self):
        folder, source = self.service()
        self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        entered, release_response = threading.Event(), threading.Event()
        class Delayed(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.path.endswith('.tar.gz'):
                    entered.set()
                    release_response.wait(10)
                super().do_GET()
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Delayed, directory=str(folder)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        source = 'http://127.0.0.1:' + str(server.server_port)
        child = subprocess.Popen([sys.executable, str(ROOT / 'scripts/install.py'), '--update', '--bin-dir', str(self.bin), '--release-source', source], env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(entered.wait(10))
            result = self.local_command('--uninstall', '--purge')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('active', result.stderr)
            self.assertTrue((self.bin / 'codex-custom').exists())
        finally:
            release_response.set()
            stdout, stderr = child.communicate(timeout=15)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertTrue((self.bin / 'codex-custom').exists())

    def test_update_uses_new_downloaded_validator_not_old_import_cache(self):
        folder, source = self.service()
        release = self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        before = (self.root / 'state/current').readlink()
        def change(payload):
            name = 'runtime/release_artifact.py'
            payload[name] += b"\ndef read_archive(path, expected_version='0.164.0'):\n    raise ReleaseError('new runtime validator rejected candidate')\n"
            manifest = json.loads(payload['release.json'])
            manifest['members'][name]['sha256'] = hashlib.sha256(payload[name]).hexdigest()
            payload['release.json'] = json.dumps(manifest).encode()
        args = self.archive(change)
        (release / 'codex-custom.tar.gz').write_bytes(Path(args[1]).read_bytes())
        descriptor = json.loads((release / 'release.json').read_text())
        descriptor['sha256'] = args[-1]
        (release / 'release.json').write_text(json.dumps(descriptor))
        result = self.local_command('--update', '--release-source', source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('new runtime validator', result.stderr)
        self.assertEqual((self.root / 'state/current').readlink(), before)

    def test_interrupted_update_preserves_activation_and_releases_management_lock(self):
        folder, source = self.service()
        self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        before = (self.root / 'state/current').readlink()
        entered, release_response = threading.Event(), threading.Event()
        class Delayed(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                entered.set()
                release_response.wait(10)
                try:
                    super().do_GET()
                except (BrokenPipeError, ConnectionResetError):
                    pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Delayed, directory=str(folder)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        source = 'http://127.0.0.1:' + str(server.server_port)
        child = subprocess.Popen([str(self.bin / 'codex-custom'), '--update', '--release-source', source], env=self.env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertTrue(entered.wait(10))
            child.terminate()
            child.communicate(timeout=10)
        finally:
            release_response.set()
            if child.poll() is None:
                child.kill()
                child.communicate()
        self.assertEqual((self.root / 'state/current').readlink(), before)
        self.assertTrue((self.bin / 'codex-custom').exists())
        self.assertEqual(self.local_command('--uninstall').returncode, 0)

    def test_missing_official_helper_stops_before_any_network_request(self):
        (self.official / 'codex-path/rg').unlink()
        result = self.command('http://127.0.0.1:1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('missing executable helpers', result.stderr)
        self.assertFalse((self.root / 'state').exists())

    def test_wrong_descriptor_and_missing_release_preserve_active_install(self):
        folder, source = self.service()
        release = self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        current = (self.root / 'state/current').readlink()
        descriptor = json.loads((release / 'release.json').read_text())
        descriptor['official_version'] = '0.165.0'
        (release / 'release.json').write_text(json.dumps(descriptor))
        result = self.command(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('matching release descriptor', result.stderr)
        (release / 'release.json').unlink()
        self.assertNotEqual(self.command(source).returncode, 0)
        self.assertEqual((self.root / 'state/current').readlink(), current)

    def test_corrupt_download_and_invalid_archive_preserve_active_install(self):
        folder, source = self.service()
        release = self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        current = (self.root / 'state/current').readlink()
        (release / 'codex-custom.tar.gz').write_bytes(b'interrupted')
        self.assertIn('SHA-256 mismatch', self.command(source).stderr)
        descriptor = json.loads((release / 'release.json').read_text())
        descriptor['sha256'] = hashlib.sha256(b'interrupted').hexdigest()
        (release / 'release.json').write_text(json.dumps(descriptor))
        self.assertNotEqual(self.command(source).returncode, 0)
        self.assertEqual((self.root / 'state/current').readlink(), current)

    def test_plain_http_remote_source_is_rejected(self):
        result = self.command('http://example.invalid/releases')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('loopback', result.stderr)

    def test_shell_entry_checks_python_and_runs_same_http_install_flow(self):
        folder, source = self.service()
        self.publish(folder)
        (folder / 'bootstrap.py').write_bytes((ROOT / 'bootstrap.py').read_bytes())
        environment = dict(self.env, CODEX_CUSTOM_BOOTSTRAP_URL=source + '/bootstrap.py', CODEX_CUSTOM_RELEASE_SOURCE=source)
        result = subprocess.run(['/bin/sh', str(ROOT / 'bootstrap.sh'), '--bin-dir', str(self.bin)],
                                env=environment, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.bin / 'codex-custom').exists())

    def test_missing_python_stops_with_dependency_instructions(self):
        environment = dict(self.env, PATH=str(self.tools), CODEX_CUSTOM_BOOTSTRAP_URL='http://127.0.0.1:1/unreachable')
        result = subprocess.run(['/bin/sh', str(ROOT / 'bootstrap.sh')], env=environment, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python 3.9+', result.stderr)
        self.assertIn('install Python', result.stderr)

    def test_old_python_and_unsupported_platform_stop_shell_before_loader_download(self):
        self.tool('python3', '#!/bin/sh\nexit 1\n')
        environment = dict(self.env, CODEX_CUSTOM_BOOTSTRAP_URL='http://127.0.0.1:1/unreachable')
        result = subprocess.run(['/bin/sh', str(ROOT / 'bootstrap.sh')], env=environment, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Python 3.9+', result.stderr)
        (self.tools / 'python3').unlink()
        self.tool('uname', '#!/bin/sh\necho Linux\n')
        result = subprocess.run(['/bin/sh', str(ROOT / 'bootstrap.sh')], env=environment, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('macOS Apple Silicon', result.stderr)

    def test_signature_failure_and_wrong_archive_architecture_or_version_preserve_install(self):
        folder, source = self.service()
        release = self.publish(folder)
        self.assertEqual(self.command(source).returncode, 0)
        current = (self.root / 'state/current').readlink()
        self.tool('codesign', '#!/bin/sh\nexit 1\n')
        self.assertNotEqual(self.command(source).returncode, 0)
        self.tool('codesign', '#!/bin/sh\ncase "$1" in -dv) echo Signature=adhoc >&2;; esac\n')
        for mutation in ('architecture', 'version'):
            def change(payload):
                if mutation == 'architecture':
                    payload['bin/codex'] = b'not Mach-O'
                manifest = json.loads(payload['release.json'])
                if mutation == 'version':
                    manifest['official_version'] = '0.165.0'
                else:
                    manifest['members']['bin/codex']['sha256'] = hashlib.sha256(payload['bin/codex']).hexdigest()
                payload['release.json'] = json.dumps(manifest).encode()
            args = self.archive(change)
            (release / 'codex-custom.tar.gz').write_bytes(Path(args[1]).read_bytes())
            descriptor = json.loads((release / 'release.json').read_text())
            descriptor['sha256'] = args[-1]
            (release / 'release.json').write_text(json.dumps(descriptor))
            self.assertNotEqual(self.command(source).returncode, 0)
        self.assertEqual((self.root / 'state/current').readlink(), current)

    def test_http_truncation_and_oversized_response_never_install(self):
        class Broken(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', '1000000' if 'large' in self.path else '100')
                self.end_headers()
                self.wfile.write(b'{}')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Broken)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        source = 'http://127.0.0.1:' + str(server.server_port)
        for base in (source, source + '/large'):
            self.assertNotEqual(self.command(base).returncode, 0)
        self.assertFalse((self.root / 'state').exists())

if __name__ == '__main__':
    unittest.main()
