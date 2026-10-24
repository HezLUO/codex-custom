#!/usr/bin/env python3
"""Verify and optionally refresh a fixed compiled candidate; never compile Rust."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

import release_artifact as artifact

ROOT = Path(__file__).resolve().parents[1]
TARGET = 'x86_64-pc-windows-msvc'
ARCHIVE_SHA256 = 'b4057b0d4c3a5bdaa03edbed22c55b938fd0cc42f7578a9a570bc2849455a317'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--refresh-runtime', action='store_true')
    args = parser.parse_args()
    if artifact.host_target() != TARGET:
        raise RuntimeError('This replay requires native Windows x64')
    original = args.input / 'codex-custom.tar.gz'
    if artifact.digest(original.read_bytes()) != ARCHIVE_SHA256:
        raise RuntimeError('Compiled candidate checksum mismatch')
    manifest, payload = artifact.read_archive(original, expected_target=TARGET)
    report = json.loads((args.input / 'license-review.json').read_text(encoding='utf-8'))
    if report['target'] != TARGET or report['missing_original_texts']:
        raise RuntimeError('Compiled candidate license review mismatch')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    for name in ('codex-custom.tar.gz', 'codex-custom.tar.gz.sha256', 'release.json', 'license-review.json'):
        shutil.copyfile(args.input / name, out / name)
    spec = importlib.util.spec_from_file_location('native_builder', ROOT / 'scripts/build-platform.py')
    builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)
    official_archive = out / 'official.tar.gz'
    builder.fetch('https://github.com/openai/codex/releases/download/rust-v0.164.0/codex-package-' + TARGET + '.tar.gz', official_archive)
    if artifact.digest(official_archive.read_bytes()) != builder.OFFICIAL_PACKAGES[TARGET]:
        raise RuntimeError('Official resource checksum mismatch')
    official = out / 'official'; official.mkdir()
    with tarfile.open(official_archive) as stream:
        if sum(m.size for m in stream.getmembers()) > 2 * 1024**3:
            raise RuntimeError('Official resources exceed unpacked limit')
        stream.extractall(official, filter='data')
    if args.refresh_runtime:
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            binary = work / 'codex.exe'; binary.write_bytes(payload['bin/codex.exe'])
            notices = work / 'notices.txt'; notices.write_bytes(payload['DEPENDENCY-NOTICES.txt'])
            provenance = json.loads(json.dumps(manifest['provenance']))
            provenance['compiled_candidate_reuse'] = dict(run_id=40103098988,
                repository_commit='63f435c5fe17223597d92f173a533593d020bb5d', archive_sha256=ARCHIVE_SHA256,
                binary_sha256=artifact.digest(binary.read_bytes()), rust_compiled_in_this_run=False,
                rust_tests_executed_in_this_run=False)
            provenance['rust_tests_executed_in_this_run'] = False
            provenance['rust_test_evidence'] = dict(status='previous-native-tests-passed',
                run_id=40103098988, job_id=120899100332, counts=[2, 20, 9, 37, 7],
                source_commit='63f435c5fe17223597d92f173a533593d020bb5d',
                url='https://github.com/HezLUO/codex-custom/actions/runs/40103098988/job/120899100332')
            provenance['runtime_source_commit'] = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
            proof = work / 'provenance.json'; proof.write_text(json.dumps(provenance))
            runtime = {'runtime/precompiled.py': 'scripts/precompiled.py',
                'runtime/release_artifact.py': 'scripts/release_artifact.py',
                'runtime/update-codex-custom.py': 'update-codex-custom.py',
                'bootstrap.py': 'bootstrap.py', 'bootstrap.sh': 'bootstrap.sh', 'bootstrap.ps1': 'bootstrap.ps1'}
            packaged = artifact.package(argparse.Namespace(binary=binary, provenance=proof,
                dependency_notices=notices, release_id='0.164.0-custom.10', target=TARGET,
                output=work / 'codex-custom.tar.gz',
                runtime=[name + '=' + str(ROOT / path) for name, path in runtime.items()]))
            refreshed, members = artifact.read_archive(work / 'codex-custom.tar.gz', expected_target=TARGET)
            for name in ('bin/codex.exe', 'DEPENDENCY-NOTICES.txt', 'LICENSE', 'NOTICE'):
                if members[name] != payload[name]:
                    raise RuntimeError('Compiled payload or original notices changed')
            for name in ('codex-custom.tar.gz', 'codex-custom.tar.gz.sha256'):
                shutil.copyfile(work / name, out / name)
            descriptor = {key: refreshed[key] for key in ('schema', 'release_id', 'official_version', 'target', 'layout_version')}
            descriptor.update(archive='codex-custom.tar.gz', sha256=packaged['sha256'])
            (out / 'release.json').write_text(json.dumps(descriptor, indent=2))
    print('Fixed compiled frontend and original notices verified; no Rust compilation.')


if __name__ == '__main__':
    main()
