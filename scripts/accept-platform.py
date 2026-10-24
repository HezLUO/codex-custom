#!/usr/bin/env python3
"""Native, isolated real-binary lifecycle smoke test; no login or model request."""
import argparse
import functools
import http.server
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading

import release_artifact as artifact
portable = artifact

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, help='Optional previous compatible archive for an actual legacy updater test')
    parser.add_argument('--official', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest, payload = artifact.read_archive(args.archive, expected_target=portable.host_target())
    target = manifest['target']; entrypoint = portable.entrypoint(target)
    report = dict(target=target, release_id=manifest['release_id'], status='failed',
                  no_model_request=True, no_live_installation=True, checks=[])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='codex-custom-native-') as temporary:
            root = Path(temporary); home = root / 'home'; ch = home / '.codex'; work = root / 'workspace'; work.mkdir()
            official = ch / 'packages/standalone/releases' / ('0.164.0-' + target)
            shutil.copytree(args.official, official, symlinks=True)
            environment = dict(os.environ, HOME=str(home), USERPROFILE=str(home), CODEX_HOME=str(ch),
                               CODEX_OFFICIAL_BIN=str(official / entrypoint), CODEX_CUSTOM_STATE_DIR=str(root / 'state'),
                               CODEX_CUSTOM_CACHE_DIR=str(root / 'cache'), APPDATA=str(home / 'AppData/Roaming'),
                               LOCALAPPDATA=str(home / 'AppData/Local'))
            environment.pop('PYTHONPATH', None)
            (ch / 'config.toml').write_text('check_for_update_on_startup = false\n')
            (ch / 'sessions').mkdir(); sentinel = ch / 'sessions/keep.txt'; sentinel.write_text('synthetic user data')
            # Do not supply credentials; commands below never perform inference.
            sys.path.insert(0, str(ROOT))
            import importlib.util
            spec = importlib.util.spec_from_file_location('inventory', ROOT / 'update-codex-custom.py')
            updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)
            baseline = updater.package_inventory(official); config_before = (ch / 'config.toml').read_bytes()
            commands = root / 'commands'; launcher = commands / ('codex-custom.cmd' if portable.windows() else 'codex-custom')
            def call(command):
                result = subprocess.run(list(map(str, command)), env=environment, cwd=work, capture_output=True, timeout=180)
                if result.returncode:
                    raise RuntimeError('Native acceptance command failed (exit ' + str(result.returncode) + ')')
                return result.stdout
            initial = args.baseline or args.archive
            call([sys.executable, ROOT / 'scripts/install.py', '--archive', initial.resolve(), '--sha256', artifact.digest(initial.read_bytes()), '--bin-dir', commands])
            if args.baseline: report['checks'].append('previous-release installer/runtime upgrade')
            if str(ROOT) in launcher.read_text(encoding='utf-8'): raise RuntimeError('Launcher retains checkout path')
            def invoke(*arguments):
                if portable.windows():
                    # Fixed smoke-test arguments; no untrusted shell text.
                    return call(['cmd.exe', '/d', '/s', '/c', '"' + subprocess.list2cmdline([str(launcher), *arguments]) + '"'])
                return call([launcher, *arguments])
            if invoke('--version').strip() != b'codex-cli 0.164.0': raise RuntimeError('Installed version mismatch')
            invoke('resume', '--help'); report['checks'] += ['source-independent launcher', 'version', 'resume argument forwarding']
            # Exercise downloader and update with another explicit custom revision.
            serve = root / 'served' / ('official-0.164.0-' + target); serve.mkdir(parents=True)
            changed = json.loads(json.dumps(manifest)); changed['release_id'] += '-smoke'
            served_archive = serve / 'codex-custom.tar.gz'
            with tarfile.open(served_archive, 'w:gz', format=tarfile.USTAR_FORMAT) as stream:
                for name, data in {**payload, 'release.json': (json.dumps(changed) + '\n').encode()}.items():
                    item = tarfile.TarInfo(name); item.size = len(data); item.mode = changed['members'].get(name, {'mode': 0o644})['mode']
                    stream.addfile(item, io.BytesIO(data))
            descriptor = {k: changed[k] for k in ('schema', 'release_id', 'official_version', 'target', 'layout_version')}
            descriptor.update(archive='codex-custom.tar.gz', sha256=artifact.digest(served_archive.read_bytes()))
            (serve / 'release.json').write_text(json.dumps(descriptor))
            class Quiet(http.server.SimpleHTTPRequestHandler):
                def log_message(self, *args): pass
            server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Quiet, directory=str(serve.parent)))
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                invoke('--update', '--release-source', 'http://127.0.0.1:' + str(server.server_port))
            finally:
                server.shutdown(); server.server_close(); thread.join()
            if invoke('--version').strip() != b'codex-cli 0.164.0': raise RuntimeError('Offline version mismatch')
            report['checks'] += ['loopback HTTP update to distinct revision', 'offline launch']
            if 'linux' in target:
                if b'custom-sandbox-ok' not in invoke('sandbox', '--', '/bin/sh', '-c', 'printf custom-sandbox-ok'):
                    raise RuntimeError('Bundled Linux sandbox smoke failed')
                report['checks'].append('actual bundled bwrap execution')
            native = official.parent / 'codex-custom'
            siblings = []
            for parent in native.iterdir():
                path = parent / 'foreign-notes'; path.write_text('not owned'); siblings.append(path)
            invoke('--uninstall'); invoke('--uninstall')
            if launcher.exists(): raise RuntimeError('Owned launcher not removed')
            call([sys.executable, ROOT / 'scripts/install.py', '--archive', args.archive.resolve(), '--sha256', artifact.digest(args.archive.read_bytes()), '--bin-dir', commands])
            invoke('--uninstall', '--purge')
            if any(not p.is_file() for p in siblings): raise RuntimeError('Unknown native sibling removed')
            if updater.package_inventory(official) != baseline or (ch / 'config.toml').read_bytes() != config_before or sentinel.read_text(encoding='utf-8') != 'synthetic user data':
                raise RuntimeError('Official or user fixture data changed')
            report['checks'] += ['uninstall/repeat/reinstall/purge', 'foreign sibling preservation', 'official and synthetic user data unchanged']
            report['status'] = 'passed'
            report['limits'] = ['No model inference, voice functional test, full TUI acceptance, or Windows non-admin console acceptance',
                               'Installed launcher has no source path; OS-level source-read denial not performed']
    finally:
        args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
