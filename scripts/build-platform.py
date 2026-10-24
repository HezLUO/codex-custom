#!/usr/bin/env python3
"""Native CI candidate builder. Never publishes or modifies a live installation."""
import argparse
import hashlib
from html.parser import HTMLParser
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request

import release_artifact as artifact
portable = artifact

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '6aaac694803004a63c6f393d153c96d22521a6b9'
VERSION = '0.164.0'
TOOLCHAIN = '1.99.1'
TESTS = ['context_details', 'status_line_setup', 'status_line_style', 'status_surface', 'local_settings']
OFFICIAL_PACKAGES = {
    'aarch64-apple-darwin': 'dd99e9092270691a67bdde7be04ac283dea9da8e86cbde356c2cc851a79205fa',
    'x86_64-apple-darwin': 'cfb2a9988d7ea448511166a35789af07a0065d1117db54350b17d46cf03d0294',
    'x86_64-unknown-linux-musl': '3ec55053109608d5038f7e50750f7d25f768dfd740fef071aa710e2559b63aac',
    'aarch64-unknown-linux-musl': '5918add6c7e9cf1e14a9af1b4c0f4bf1d24a43903faac26df5dc4c019ea91bd5',
    'x86_64-pc-windows-msvc': '700116be3143576d006467af8576f7f4c9dada1feddfdb7f69743bfde0997018',
}


def run(command, cwd=None, capture=False):
    return subprocess.run(list(map(str, command)), cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE if capture else None).stdout


def fetch(url, output, limit=1024 * 1024 * 1024):
    # CI uses fixed first-party HTTPS sources, never a user-provided download URL.
    with urllib.request.urlopen(url, timeout=120) as response, output.open('wb') as stream:
        if not response.url.startswith('https://'):
            raise RuntimeError('HTTPS download downgraded')
        total = 0
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise RuntimeError('CI input exceeds size limit')
            stream.write(chunk)


def write_environment(values):
    with Path(os.environ['GITHUB_ENV']).open('a', encoding='utf-8') as stream:
        for key, value in values.items():
            value = str(value)
            if '\n' in value or '\r' in value:
                raise RuntimeError('Invalid CI environment value')
            stream.write(key + '=' + value + '\n')


def prepare(source, work, target):
    if sys.version_info < (3, 12):
        raise RuntimeError('Candidate builds require Python 3.12+; installed runtime still requires 3.9+')
    if run(['git', 'rev-parse', 'HEAD'], source, True).strip() != COMMIT or run(['git', 'status', '--porcelain'], source, True).strip():
        raise RuntimeError('Build requires a clean exact pinned upstream checkout')
    work.mkdir(parents=True, exist_ok=True)
    base = 'https://github.com/openai/codex/releases/download/rust-v' + VERSION + '/'
    name = 'codex-package-' + target + '.tar.gz'
    fetch(base + 'codex-package_SHA256SUMS', work / 'official-checksums.txt', 1024 * 1024)
    if artifact.digest((work / 'official-checksums.txt').read_bytes()) != '28fa3c96ec1b66c34c0a5b8ac26e9c4d2dcbb82d0b0d66bd0a8108c0f4b1e522':
        raise RuntimeError('Official checksum manifest changed from reviewed release')
    matches = [line.split()[0] for line in (work / 'official-checksums.txt').read_text(encoding='utf-8').splitlines()
               if len(line.split()) == 2 and line.split()[1].lstrip('*') == name]
    if len(matches) != 1 or matches[0] != OFFICIAL_PACKAGES[target]:
        raise RuntimeError('No exact official package checksum')
    archive = work / 'official.tar.gz'; fetch(base + name, archive)
    if artifact.digest(archive.read_bytes()) != matches[0]:
        raise RuntimeError('Official package checksum mismatch')
    official = work / 'official'; official.mkdir(exist_ok=False)
    with tarfile.open(archive) as stream:
        if sum(item.size for item in stream.getmembers()) > 2 * 1024**3:
            raise RuntimeError('Official package unpacked limit exceeded')
        stream.extractall(official, filter='data')
    metadata = json.loads((official / 'codex-package.json').read_text(encoding='utf-8'))
    expected = dict(layoutVersion=1, version=VERSION, target=target, variant='codex',
                    entrypoint=portable.entrypoint(target), resourcesDir='codex-resources', pathDir='codex-path')
    if any(metadata.get(k) != v for k, v in expected.items()):
        raise RuntimeError('Official input metadata mismatch')
    for name in portable.helpers(target) + [portable.entrypoint(target)]:
        if not (official / name).is_file():
            raise RuntimeError('Incomplete official CI input')
    if not (official / 'codex-resources/voice/manifest.json').is_file():
        raise RuntimeError('Official voice manifest is missing')
    values = {'CODEX_CUSTOM_CI_OFFICIAL': official, 'CODEX_CUSTOM_CI_OFFICIAL_SHA256': matches[0],
              'STABLE_GIT_COMMIT': COMMIT, 'CARGO_NET_GIT_FETCH_WITH_CLI': 'true',
              'CARGO_BUILD_JOBS': '2', 'CARGO_TARGET_DIR': work / 'ct', 'RUST_MIN_STACK': '8388608'}
    if 'linux' in target:
        values['CODEX_BWRAP_SHA256'] = artifact.digest((official / 'codex-resources/bwrap').read_bytes())
        values['AWS_LC_SYS_NO_JITTER_ENTROPY'] = '1'
        values['AWS_LC_SYS_NO_JITTER_ENTROPY_' + target.replace('-', '_')] = '1'
        index = work / 'zig-index.json'; fetch('https://ziglang.org/download/index.json', index, 4 * 1024 * 1024)
        spec = json.loads(index.read_text(encoding='utf-8'))['0.14.0'][('aarch64' if target.startswith('aarch64') else 'x86_64') + '-linux']
        if not spec['tarball'].startswith('https://ziglang.org/'):
            raise RuntimeError('Unexpected Zig download origin')
        zig = work / 'zig.tar.xz'; fetch(spec['tarball'], zig)
        if artifact.digest(zig.read_bytes()) != spec['shasum']:
            raise RuntimeError('Zig checksum mismatch')
        with tarfile.open(zig) as stream: stream.extractall(work / 'zig', filter='data')
        executable = next((work / 'zig').glob('*/zig'))
        with Path(os.environ['GITHUB_PATH']).open('a', encoding='utf-8') as stream: stream.write(str(executable.parent) + '\n')
    if portable.windows(target):
        values['LIBSQLITE3_FLAGS'] = 'SQLITE_DISABLE_INTRINSIC'
    os.environ['CODEX_REPO_ROOT'] = str(source)
    sys.path.insert(0, str(source / 'scripts'))
    from codex_package.targets import TARGET_SPECS
    from codex_package.v8 import resolve_codex_v8_cargo_env
    values.update(resolve_codex_v8_cargo_env(TARGET_SPECS[target]))
    write_environment(values)


def collect_notices(metadata, source, out, target):
    """Conservative target-resolved graph, including build tools; flag gaps explicitly."""
    packages = {p['id']: p for p in metadata['packages']}
    nodes = {n['id']: n for n in metadata['resolve']['nodes']}
    root = next(p['id'] for p in metadata['packages'] if p['name'] == 'codex-cli' and not p.get('source'))
    selected, pending = set(), [root]
    while pending:
        key = pending.pop()
        if key in selected: continue
        selected.add(key); pending.extend(d['pkg'] for d in nodes[key]['deps'])
    texts = ['Conservative target dependency notices for ' + target + '\nIncludes host/build dependencies; not exact linker reachability.\n']
    missing, records = [], []
    reviewed_sources = json.loads((ROOT / 'scripts/native-license-sources.json').read_text(encoding='utf-8'))
    recovered = {
        ('cookie-factory', '0.3.3'): ('https://raw.githubusercontent.com/rust-bakery/cookie-factory/d36b805dbd7dd65f2df947235c5bcc573afe2c76/LICENSES/MIT.txt', 'd09216dc1ea5f273997667935a8d6514d80f00b89fb6954ecc3a43e0a6e360de'),
        ('fax', '0.2.6'): ('https://raw.githubusercontent.com/pdf-rs/fax/5d70a161e33b62305f8bce7af3f7fbd011cfaf5d/LICENSE', '7101390b4c8edd752f4c0de47f35d61b44d9cf0ee8dd032115e25644e277cfff'),
        ('fax_derive', '0.2.0'): ('https://raw.githubusercontent.com/pdf-rs/fax/5d70a161e33b62305f8bce7af3f7fbd011cfaf5d/LICENSE', '7101390b4c8edd752f4c0de47f35d61b44d9cf0ee8dd032115e25644e277cfff'),
    }
    def reviewed_text(url, checksum):
        if (not re.fullmatch(r'https://raw\.githubusercontent\.com/[^/]+/[^/]+/[0-9a-f]{40}/[^?#]+', url)
                or not re.fullmatch(r'[0-9a-f]{64}', checksum)):
            raise RuntimeError('Reviewed license source must pin an immutable revision and digest')
        cache = out / '.license-inputs'; cache.mkdir(exist_ok=True)
        path = cache / checksum
        if not path.is_file(): fetch(url, path, 4 * 1024 * 1024)
        if artifact.digest(path.read_bytes()) != checksum:
            raise RuntimeError('Reviewed original license checksum mismatch')
        return path.read_text(encoding='utf-8')

    def mit_terms():
        text = reviewed_text(*recovered['cookie-factory', '0.3.3'])
        return text[text.index('Permission is hereby granted'):]

    for key in sorted(selected):
        p = packages[key]; location = Path(p['manifest_path']).parent
        identity = p['name'] + ' ' + p['version']
        origin = ('https://crates.io/api/v1/crates/' + p['name'] + '/' + p['version'] + '/download'
                  if str(p.get('source', '')).startswith('registry+') else p.get('source') or 'https://github.com/openai/codex/tree/' + COMMIT)
        if origin.startswith('git+https://'):
            match = re.fullmatch(r'git\+(https://[^?#]+)(?:\?[^#]*)?#([0-9a-f]{40})', origin)
            if not match: raise RuntimeError('Git dependency source must include its resolved revision')
            origin = match.group(1).removesuffix('.git') + '/tree/' + match.group(2)
        # A legitimate crate name otherwise resembles a personal home path.
        # Normalize before both the notice and its inventory are serialized.
        origin = origin.replace('crates.io/api/v1/crates/home/', 'crates.io/api/v1/crates/h%6fme/')
        texts.append('\n' + '=' * 78 + '\n' + identity + '\nSource: ' + origin + '\nDeclared license: ' + str(p.get('license')) + '\nPublished authors: ' + json.dumps(p.get('authors', []), ensure_ascii=False) + '\n')
        files = []
        # Cargo packages may inherit a license file outside the member directory.
        # Follow only an explicitly declared file inside its own source checkout.
        if p.get('license_file'):
            license_path = Path(p['license_file'])
            if not license_path.is_absolute(): license_path = location / license_path
            license_path = license_path.resolve()
            boundary = location.resolve()
            if str(p.get('source', '')).startswith('git+'):
                boundary = next((parent for parent in [boundary, *boundary.parents]
                                 if (parent / '.git').exists()), boundary)
            if license_path.is_relative_to(boundary) and license_path.is_file():
                if license_path.stat().st_size > 4 * 1024 * 1024:
                    raise RuntimeError('Unexpected oversized declared license')
                files.append((license_path.relative_to(boundary).as_posix(), license_path.read_text(encoding='utf-8')))
        for path in sorted(location.rglob('*')):
            if not path.is_file() or path.is_symlink(): continue
            relative = path.relative_to(location).as_posix()
            if any(part in ('target', '.git', 'node_modules') for part in Path(relative).parts): continue
            if ((re.match(r'(?i)^(license|licence|copying|copyright|notice)([.\-_]|$)', path.name)
                     and path.suffix.lower() not in ('.rs', '.py', '.c', '.h', '.cpp', '.js', '.ts', '.go', '.java'))
                    or any(part.upper() in ('LICENSES', 'LICENCES') for part in path.relative_to(location).parts[:-1])
                    or path == Path(p.get('license_file') or '/nonexistent')):
                if path.stat().st_size > 4 * 1024 * 1024: raise RuntimeError('Unexpected oversized dependency notice')
                try: text = path.read_text(encoding='utf-8')
                except UnicodeDecodeError: continue
                files.append((relative, text))
        for evidence in reviewed_sources.get(p['name'] + '@' + p['version'], []):
            url, checksum = evidence['url'], evidence['sha256']
            text = reviewed_text(url, checksum)
            if artifact.digest(text.encode()) not in {artifact.digest(t.encode()) for _, t in files}:
                files.append((url, text))
            if evidence.get('selected_license'):
                selected = evidence['selected_license']
                if selected not in ('MIT', 'Apache-2.0') or selected not in re.findall(r'[A-Za-z0-9.+-]+', str(p.get('license'))):
                    raise RuntimeError('Reviewed license option differs from package declaration')
                if selected == 'MIT':
                    texts.append('Upstream supplies no original copyright line; published authors and original licensing statement retained. No year or holder invented.\n')
                files.append(('Explicitly reviewed ' + selected + ' terms; original declaration retained',
                              mit_terms() if selected == 'MIT' else (source / 'LICENSE').read_text(encoding='utf-8')))
        if (p['name'], p['version']) in recovered:
            url, checksum = recovered[p['name'], p['version']]
            if p['name'] != 'cookie-factory': texts.append('Notice recovered from accepted immediate-child upstream license-only repair; not originally packaged.\n')
            files.append((url, reviewed_text(url, checksum)))
        if not files and p['name'] == 'debugserver-types' and p['version'] == '0.5.0':
            texts.append('Upstream declares MIT and names authors but supplies no original copyright line; no year or holder invented. Full canonical permission/disclaimer follow.\n')
            files = [('Canonical MIT terms (copyright line not invented)', mit_terms())]
        if not files and p['name'] in ('eventsource-stream', 'io_tee') and 'Apache-2.0' in str(p.get('license')):
            files = [('Declared Apache-2.0 option selected; upstream omits original license file', (source / 'LICENSE').read_text(encoding='utf-8'))]
        if not files and 'Apache-2.0' in str(p.get('license')):
            for path in sorted(location.rglob('*.rs')):
                prefix = path.read_text(encoding='utf-8', errors='replace')[:2000]
                header = ''
                if prefix.startswith('/*') and '*/' in prefix:
                    header = prefix.split('*/', 1)[0] + '*/\n'
                elif prefix.startswith('//'):
                    lines = []
                    for line in prefix.splitlines():
                        if not line.startswith('//'): break
                        lines.append(line)
                    header = '\n'.join(lines) + '\n'
                if 'Copyright' in header and 'Apache' in header:
                    files = [(path.relative_to(location).as_posix() + ' original header', header),
                             ('Selected Apache-2.0 full terms', (source / 'LICENSE').read_text(encoding='utf-8'))]
                    break
        if not files and not p.get('source'):
            files = [('upstream LICENSE', (source / 'LICENSE').read_text(encoding='utf-8'))]
        if not files:
            missing.append({'name': p['name'], 'version': p['version'], 'declared_license': p.get('license'), 'source': origin})
            texts.append('REVIEW REQUIRED: no original license text recovered automatically. Published declaration and authors above are retained; this entry is incomplete.\n')
        for name, text in files: texts.append('\n--- ' + name + ' ---\n' + text + '\n')
        records.append({'name': p['name'], 'version': p['version'], 'source': origin, 'texts': [{'path': n, 'sha256': artifact.digest(t.encode())} for n, t in files]})
    # Standard library and embedded assets are outside Cargo's package graph.
    toolroot = Path(run(['rustup', 'which', '--toolchain', TOOLCHAIN, 'rustc'], capture=True).strip()).parent.parent
    standard = toolroot / 'share/doc/rust/COPYRIGHT-library.html'
    if standard.is_file():
        class Text(HTMLParser):
            def __init__(self): super().__init__(); self.parts = []
            def handle_data(self, data): self.parts.append(data)
        parser = Text(); parser.feed(standard.read_text(encoding='utf-8')); texts.append('\nRust standard library notices\n' + ''.join(parser.parts))
    else:
        missing.append({'name': 'rust-standard-library', 'version': TOOLCHAIN})
    assets = [source / 'third_party/wezterm/LICENSE', *sorted(p for p in (source / 'codex-rs/skills/src/assets/samples').rglob('*') if p.is_file() and 'license' in p.name.lower())]
    for path in assets:
        if path.is_file(): texts.append('\nEmbedded asset: ' + path.relative_to(source).as_posix() + '\n' + path.read_text(encoding='utf-8') + '\n')
    notice = '\n'.join(texts).replace('crates.io/api/v1/crates/home/', 'crates.io/api/v1/crates/h%6fme/')
    artifact.privacy_check(notice.encode())
    (out / 'DEPENDENCY-NOTICES.txt').write_text(notice, encoding='utf-8')
    report = dict(target=target, packages=len(records), status='source-review-required', missing_original_texts=missing, inventory=records)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    artifact.privacy_check(serialized.encode())
    (out / 'license-review.json').write_text(serialized, encoding='utf-8')
    return report


def redact_build_paths(binary, target, prefixes):
    """Replace known CI prefixes only inside non-executable constant sections.

    Preserve length, offsets and all other bytes. Unknown path/credential matches
    still fail the ordinary artifact admission check. Never patch instructions.
    """
    data = bytearray(binary.read_bytes())
    regions = artifact.constant_data_ranges(data, target)
    replacements = {}
    for prefix in prefixes:
        raw = str(prefix).encode('utf-8')
        if len(raw) < 8: raise RuntimeError('Build prefix too short to sanitize safely')
        for value in {raw, raw.replace(b'\\', b'/'), raw.replace(b'\\', b'\\\\')}:
            neutral = b'/build/' + b'_' * (len(value) - 7)
            replacements[value] = neutral
            if portable.windows(target):
                replacements[value.decode().encode('utf-16-le')] = neutral.decode().encode('utf-16-le')
    edits = []
    for prefix, replacement in sorted(replacements.items(), key=lambda item: -len(item[0])):
        for match in re.finditer(re.escape(prefix), data):
            start, end = match.span()
            # A prefix must end at a path component boundary, never inside a name.
            suffix = bytes(data[end:end + 2])
            if suffix[:1] not in (b'/', b'\\', b'\0'):
                continue
            if not any(a <= start and end <= b for a, b in regions):
                raise RuntimeError('Build path lies outside approved constant sections')
            if not any(a < end and start < b for a, b, _ in edits):
                edits.append((start, end, replacement))
    for start, end, replacement in edits:
        data[start:end] = replacement
    binary.write_bytes(data)
    return len(edits)


def build(source, work, out, target):
    import tomllib
    if run(['git', 'rev-parse', 'HEAD'], source, True).strip() != COMMIT or run(['git', 'status', '--porcelain'], source, True).strip():
        raise RuntimeError('Build requires a clean pinned source')
    run(['git', 'apply', '--check', ROOT / 'patches/codex-0.164.0-context-details.patch'], source)
    run(['git', 'apply', ROOT / 'patches/codex-0.164.0-context-details.patch'], source)
    cargo = ['cargo', '+' + TOOLCHAIN]; rust = source / 'codex-rs'
    config = tomllib.loads((rust / '.cargo/config.toml').read_text(encoding='utf-8'))
    flags = list(config.get('target', {}).get(target, {}).get('rustflags', []))
    if portable.windows(target):
        flags += config['target']['cfg(all(windows, target_env = "msvc"))']['rustflags']
        flags += ['-C', 'link-arg=/PDBALTPATH:codex.pdb']
    for prefix, neutral in [(Path.home(), '/build/runner'), (source.parent, '/build/workspace'),
                            (Path(os.environ.get('CARGO_HOME', Path.home() / '.cargo')), '/build/cargo'),
                            (Path(os.environ.get('RUSTUP_HOME', Path.home() / '.rustup')), '/build/rustup')]:
        for value in {str(prefix.resolve()), prefix.resolve().as_posix()}:
            flags.append('--remap-path-prefix=' + value + '=' + neutral)
    os.environ['CARGO_ENCODED_RUSTFLAGS'] = '\x1f'.join(flags)
    # Preserve upstream compiler flags, including curl NTLM and MSVC stack/CRT.
    if os.name != 'nt':
        mapping = ' -ffile-prefix-map=' + str(Path.home()) + '=/build/runner'
        for variable in ('CFLAGS', 'CXXFLAGS'): os.environ[variable] = os.environ.get(variable, '') + mapping
    metadata = json.loads(run([*cargo, 'metadata', '--no-deps', '--format-version', '1'], rust, True))
    spec = importlib.util.spec_from_file_location('updater', ROOT / 'update-codex-custom.py')
    updater = importlib.util.module_from_spec(spec); spec.loader.exec_module(updater)
    updater.normalize_local_lock_versions(rust, metadata, run(['git', 'show', 'HEAD:codex-rs/Cargo.lock'], source, True))
    out.mkdir(parents=True, exist_ok=False)
    metadata = json.loads(run([*cargo, 'metadata', '--locked', '--format-version', '1', '--filter-platform', target], rust, True))
    report = collect_notices(metadata, source, out, target)
    if report['missing_original_texts']:
        raise RuntimeError('Target notice review has unresolved original texts; inspect license-review.json before compiling')
    for name in TESTS:
        result = run([*cargo, 'test', '--locked', '--release', '--target', target, '-p', 'codex-tui', '--lib', name], rust, True)
        summary = re.search(r'test result: ok\. [1-9][0-9]* passed', result)
        if not summary: raise RuntimeError('Targeted tests did not pass: ' + name)
        print('Native test ' + name + ': ' + summary.group(), flush=True)
    run([*cargo, 'build', '--locked', '--release', '--target', target, '-p', 'codex-cli', '--bin', 'codex'], rust)
    binary = Path(os.environ['CARGO_TARGET_DIR']) / target / 'release' / ('codex.exe' if portable.windows(target) else 'codex')
    if target.endswith('apple-darwin'):
        run(['strip', '-S', '-x', binary])
    elif 'linux' in target:
        run(['strip', '--strip-debug', '--strip-unneeded', binary])
    # Static V8/native archives can retain their original public CI paths even
    # when Rust and C compiler prefix remapping is enabled for this checkout.
    prefixes = {str(Path.home()), '/home/' + 'runner', '/Users/' + 'runner'}
    if portable.windows(target):
        # OpenSSL's published Windows objects retain a DOS short CI home path.
        prefixes.add('C:' + '\\Users' + '\\RUNNER~1')
    redactions = redact_build_paths(binary, target, prefixes)
    if target.endswith('apple-darwin'):
        run(['codesign', '--force', '--sign', '-', binary])
    try:
        artifact.verify_binary(binary, target=target)
    except artifact.ReleaseError:
        # Preserve a redacted diagnostic if admission fails; never upload the
        # unreviewed binary or matching private values to the public repository.
        data = binary.read_bytes(); findings = {}
        for label, pattern in artifact.RULES.items():
            for match in re.finditer(pattern, data):
                checksum = artifact.digest(match.group())
                if checksum not in artifact.REVIEWED_LITERALS:
                    key = (label, checksum, len(match.group()))
                    findings[key] = findings.get(key, 0) + 1
        diagnostic = dict(status='blocked', binary_sha256=artifact.digest(data), findings=[
            dict(rule=label, sha256=checksum, size=size, count=count)
            for (label, checksum, size), count in sorted(findings.items())])
        (out / 'privacy-review.json').write_text(json.dumps(diagnostic, indent=2), encoding='utf-8')
        # Reviewers can inspect exact unknown matches without publishing them.
        # Only the public encryption certificate belongs in source; the private
        # recipient key remains outside the checkout on the maintainer machine.
        details = dict(binary_sha256=artifact.digest(data), findings=[
            dict(rule=label, sha256=artifact.digest(match.group()), value_hex=match.group().hex())
            for label, pattern in artifact.RULES.items() for match in re.finditer(pattern, data)
            if artifact.digest(match.group()) not in artifact.REVIEWED_LITERALS])
        with tempfile.TemporaryDirectory() as temporary:
            plaintext = Path(temporary) / 'details.json'
            plaintext.write_text(json.dumps(details), encoding='utf-8')
            run(['openssl', 'cms', '-encrypt', '-binary', '-aes-256-cbc', '-in', plaintext,
                 '-outform', 'DER', '-out', out / 'privacy-details.cms', ROOT / 'scripts/privacy-diagnostic-cert.pem'])
        raise
    run([binary, '--help'], capture=True)
    provenance = dict(binary_sha256=artifact.digest(binary.read_bytes()), build_action='native clean CI build',
                      build_path_redactions=redactions,
                      toolchain=TOOLCHAIN, target=target, tests=TESTS, upstream_commit=COMMIT,
                      official_package_sha256=os.environ['CODEX_CUSTOM_CI_OFFICIAL_SHA256'],
                      distribution_review={'status': 'target-source-review-required', 'dependency_notice_sha256': artifact.digest((out / 'DEPENDENCY-NOTICES.txt').read_bytes())})
    if 'linux' in target: provenance['official_bwrap_sha256'] = os.environ['CODEX_BWRAP_SHA256']
    provenance_file = work / 'provenance.json'; provenance_file.write_text(json.dumps(provenance))
    runtime = {'runtime/precompiled.py': 'scripts/precompiled.py', 'runtime/release_artifact.py': 'scripts/release_artifact.py',
               'runtime/update-codex-custom.py': 'update-codex-custom.py', 'bootstrap.py': 'bootstrap.py', 'bootstrap.sh': 'bootstrap.sh'}
    if portable.windows(target): runtime['bootstrap.ps1'] = 'bootstrap.ps1'
    args = argparse.Namespace(binary=binary, provenance=provenance_file, dependency_notices=out / 'DEPENDENCY-NOTICES.txt',
                              release_id='0.164.0-custom.8', target=target, output=out / 'codex-custom.tar.gz',
                              runtime=[name + '=' + str(ROOT / path) for name, path in runtime.items()])
    result = artifact.package(args)
    descriptor = dict(schema=1, release_id=args.release_id, official_version=VERSION, target=target, layout_version=1,
                      archive='codex-custom.tar.gz', sha256=result['sha256'])
    (out / 'release.json').write_text(json.dumps(descriptor, indent=2))
    print('Native candidate packaged; target-specific notice review and lifecycle acceptance still required.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'build'])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); target = portable.host_target()
    if os.environ.get('TARGET', target) != target: raise RuntimeError('Matrix target does not match native runner')
    if args.action == 'prepare': prepare(args.source.resolve(), args.work.resolve(), target)
    else:
        if not args.output: parser.error('--output required for build')
        build(args.source.resolve(), args.work.resolve(), args.output.resolve(), target)


if __name__ == '__main__':
    main()
