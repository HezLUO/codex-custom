#!/usr/bin/env python3
"""Build the context-details patch for the installed official Codex version."""

import argparse
import fcntl
import hashlib
import json
import os
import platform
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parent
PATCH = ROOT / "patches/codex-0.164.0-context-details.patch"
# Separate source, generated state, and cache. Legacy outputs/work remain untouched.
INSTALL = Path(os.environ.get("CODEX_CUSTOM_STATE_DIR",
                              str(Path.home() / ".local/share/codex-custom/builds"))).expanduser().resolve()
WORK = Path(os.environ.get("CODEX_CUSTOM_CACHE_DIR",
                           str(Path.home() / ".cache/codex-custom"))).expanduser().resolve()
OFFICIAL = Path(os.environ.get("CODEX_OFFICIAL_BIN",
                               str(Path.home() / ".local/bin/codex"))).expanduser().absolute()
BUILD_SCHEMA = 3
TEST_FILTERS = ["context_details", "status_line_setup", "status_line_style", "status_surface", "local_settings"]


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_inventory(root):
    """Receipt covering packaged file contents, permissions and symlink targets."""
    receipt = {}
    for item in sorted(root.rglob("*")):
        relative = item.relative_to(root).as_posix()
        if item.is_symlink():
            receipt[relative] = {"symlink": os.readlink(item)}
        elif item.is_file():
            receipt[relative] = {"sha256": file_hash(item),
                                 "mode": item.stat().st_mode & 0o777}
    return receipt


def official_package(version):
    executable = OFFICIAL.resolve(strict=True)
    root = executable.parent.parent
    if root.parent.name != "releases" or root.parent.parent.name != "standalone":
        raise RuntimeError("Expected an official standalone/releases package location")
    metadata = json.loads((root / "codex-package.json").read_text())
    if (metadata.get("layoutVersion") != 1 or metadata.get("version") != version
            or metadata.get("target") != "aarch64-apple-darwin"
            or metadata.get("variant") != "codex"
            or metadata.get("entrypoint") != "bin/codex"
            or metadata.get("resourcesDir") != "codex-resources"
            or metadata.get("pathDir") != "codex-path"
            or executable != root / "bin/codex"):
        raise RuntimeError("Expected a matching complete official macOS ARM64 package")
    for helper in ["bin/codex-code-mode-host", "codex-path/rg"]:
        if not os.access(root / helper, os.X_OK):
            raise RuntimeError(f"Official package is missing executable {helper}")
    if not (root / "codex-resources/voice").is_dir():
        raise RuntimeError("Official package is missing voice resources")
    return root, metadata


def stage_package(official_root, binary, release):
    """Copy the complete official layout; replace only the frontend executable."""
    before = package_inventory(official_root)
    # Native install detection requires a real path below standalone/releases.
    # A private parent without package metadata is skipped by the official pruner.
    package = official_root.parent / "codex-custom" / release.name / "package"
    package.parent.mkdir(parents=True, exist_ok=False)
    shutil.copytree(official_root, package, symlinks=True)
    if package_inventory(package) != before:
        raise RuntimeError("Official package changed during copy")
    # Unlink first: never write through a packaged symlink or retain old signing xattrs.
    entrypoint = package / "bin/codex"
    entrypoint.unlink()
    shutil.copy2(binary, entrypoint)
    (release / "package").symlink_to(package.resolve(), target_is_directory=True)
    (release / "codex").symlink_to("package/bin/codex")
    after = package_inventory(package)
    if ({k: v for k, v in before.items() if k != "bin/codex"}
            != {k: v for k, v in after.items() if k != "bin/codex"}):
        raise RuntimeError("Packaged helpers or resources changed")
    return after


def official_version():
    result = subprocess.run([str(OFFICIAL), "--version"], check=True, text=True,
                            capture_output=True)
    match = re.search(r"^codex-cli ([0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?)$",
                      result.stdout.strip(), re.MULTILINE)
    if not match:
        raise RuntimeError("Cannot identify the official Codex version")
    return match.group(1)


def patch_hash():
    return hashlib.sha256(PATCH.read_bytes()).hexdigest()


def current_matches(version):
    try:
        manifest = json.loads((INSTALL / "current/manifest.json").read_text())
        binary = INSTALL / "current/package/bin/codex"
        official_root, metadata = official_package(version)
        return (manifest["version"] == version
                and manifest.get("build_schema") == BUILD_SCHEMA
                and manifest.get("profile") == "release"
                and manifest.get("updater_sha256") == file_hash(Path(__file__))
                and manifest.get("official_package") == str(official_root)
                and manifest.get("package_metadata") == metadata
                and official_root.parent / "codex-custom" in binary.resolve().parents
                and manifest["patch_sha256"] == patch_hash()
                and os.access(binary, os.X_OK)
                and manifest["package_inventory"] == package_inventory(INSTALL / "current/package"))
    except (OSError, KeyError, ValueError, RuntimeError):
        return False


def normalize_local_lock_versions(rust_root, metadata, baseline):
    """Repair release stamping for workspace packages; preserve external pins."""
    lock_path = rust_root / "Cargo.lock"
    original = baseline
    versions = {p["name"]: p["version"] for p in metadata["packages"]
                if p.get("source") is None}
    blocks = original.split("[[package]]")
    for i, block in enumerate(blocks[1:], 1):
        name = re.search(r'^name = "([^"]+)"$', block, re.MULTILINE)
        old = re.search(r'^version = "([^"]+)"$', block, re.MULTILINE)
        if name and old and not re.search(r'^source = ', block, re.MULTILINE):
            expected = versions.get(name.group(1))
            if expected and old.group(1) != expected:
                blocks[i] = block[:old.start(1)] + expected + block[old.end(1):]
    updated = "[[package]]".join(blocks)
    if lock_path.read_text() not in (original, updated):
        raise RuntimeError("Lockfile contains changes beyond workspace version stamping")
    if lock_path.read_text() != updated:
        lock_path.write_text(updated)


def build(version, source=None, force=False):
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("Only macOS Apple Silicon is supported")
    INSTALL.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    with (INSTALL / "update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another custom CLI build is running; retry when it finishes")
        if not force and current_matches(version):
            print(f"Custom CLI {version} is already validated.")
            return

        # Fail before network/build activity for unsupported or incomplete packages.
        official_package(version)
        stamp = time.strftime("%Y%m%d-%H%M%S") + f"-{os.getpid()}"
        log_path = INSTALL / f"build-{version}-{stamp}.log"
        print(f"Building Codex {version}; log: {log_path}", flush=True)
        with log_path.open("w") as log:
            def run(args, cwd=None, env=None, capture=False):
                log.write("\n$ " + " ".join(map(str, args)) + "\n")
                log.flush()
                proc = subprocess.Popen(list(map(str, args)), cwd=cwd, env=env,
                                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        text=True)
                lines = []
                for line in proc.stdout:
                    log.write(line)
                    log.flush()
                    if capture:
                        lines.append(line)
                if proc.wait():
                    raise RuntimeError(f"Command failed: {args[0]}; see {log_path}")
                return "".join(lines)

            if source:
                repo = source.resolve()
                # The supplied source must be the official baseline with only this patch.
                tag_commit = run(["git", "rev-parse", f"rust-v{version}^{{commit}}"], repo, capture=True).strip()
                head = run(["git", "rev-parse", "HEAD"], repo, capture=True).strip()
                if head != tag_commit:
                    raise RuntimeError("Supplied source is not at the requested release tag")
                untracked = run(["git", "ls-files", "--others", "--exclude-standard"], repo, capture=True)
                if untracked.strip():
                    raise RuntimeError("Supplied source contains untracked files")
                run(["git", "apply", "--reverse", "--check", PATCH], repo)
                actual = run(["git", "diff", "--no-ext-diff", "--binary", "HEAD", "--", ".", ":(exclude)codex-rs/Cargo.lock"], repo, capture=True)
                if actual != PATCH.read_text():
                    raise RuntimeError("Supplied source has changes beyond the saved patch")
            else:
                cache = WORK / "updater-source.git"
                if not cache.exists():
                    run(["git", "clone", "--bare", "--filter=blob:none", "--depth", "1",
                         "https://github.com/openai/codex.git", cache])
                tag = f"rust-v{version}"
                run(["git", "fetch", "--depth", "1", "origin", f"refs/tags/{tag}:refs/tags/{tag}"], cache)
                repo = WORK / f"build-{version}-{stamp}"
                run(["git", "worktree", "add", "--detach", repo, tag], cache)
                # A conflict stops here; no fuzzy application and no automatic rewriting.
                run(["git", "apply", "--check", PATCH], repo)
                run(["git", "apply", PATCH], repo)

            rust_root = repo / "codex-rs"
            toolchain_match = re.search(r'^channel\s*=\s*"([^"]+)"',
                                        (rust_root / "rust-toolchain.toml").read_text(), re.MULTILINE)
            if not toolchain_match:
                raise RuntimeError("Cannot identify repository Rust toolchain")
            toolchain = toolchain_match.group(1)
            cargo = shutil.which("cargo")
            rustup = shutil.which("rustup")
            if not cargo or not rustup:
                raise RuntimeError("Install Rust via rustup and add cargo/rustup to PATH; see README.md")
            env = os.environ.copy()
            # The launcher's display preference must not alter build/test fixtures.
            env.pop("CODEX_CUSTOM_STATUS_LINE", None)
            env.update(RUST_MIN_STACK="8388608",
                       CARGO_BUILD_JOBS=env.get("CARGO_BUILD_JOBS", "6"),
                       CARGO_TARGET_DIR=str(WORK / "target"))
            official_root, package_metadata = official_package(version)
            commit = run(["git", "rev-parse", "HEAD"], repo, capture=True).strip()
            env["STABLE_GIT_COMMIT"] = commit
            target = package_metadata["target"]
            run([rustup, "toolchain", "install", toolchain, "--profile", "minimal",
                 "--component", "rustfmt"], env=env)
            run([rustup, "target", "add", "--toolchain", toolchain, target], env=env)
            metadata = run([cargo, f"+{toolchain}", "metadata", "--offline", "--no-deps",
                            "--format-version", "1"], rust_root, env, capture=True)
            baseline_lock = run(["git", "show", "HEAD:codex-rs/Cargo.lock"], repo, capture=True)
            normalize_local_lock_versions(rust_root, json.loads(metadata), baseline_lock)
            lock_diff = run(["git", "diff", "--", "codex-rs/Cargo.lock"], repo, capture=True)
            run([cargo, f"+{toolchain}", "fmt", "--all", "--", "--check"], rust_root, env)
            for test_filter in TEST_FILTERS:
                print(f"Testing {test_filter}…", flush=True)
                output = run([cargo, f"+{toolchain}", "test", "--locked", "-p", "codex-tui",
                              "--lib", test_filter], rust_root, env, capture=True)
                if not re.search(r"test result: ok\. [1-9][0-9]* passed", output):
                    raise RuntimeError(f"No passing tests matched {test_filter}; refusing to publish")
            print("Compiling optimized release CLI…", flush=True)
            run([cargo, f"+{toolchain}", "build", "--locked", "--target", target,
                 "--release", "-p", "codex-cli", "--bin", "codex"], rust_root, env)
            binary = Path(env["CARGO_TARGET_DIR"]) / target / "release/codex"
            reported = run([binary, "--version"], rust_root, env, capture=True).strip()
            if reported != f"codex-cli {version}":
                raise RuntimeError(f"Unexpected binary version: {reported}")
            run([binary, "--help"], rust_root, env)
            release = Path(tempfile.mkdtemp(prefix=f"{version}-", dir=INSTALL))
            stage_package(official_root, binary, release)
            packaged_binary = release / "package/bin/codex"
            # Match the official macOS runtime symbol stripping; retain the cache's
            # unstripped artifact and use a local signature on the packaged copy.
            run(["/usr/bin/strip", "-S", "-x", packaged_binary])
            run(["/usr/bin/codesign", "--force", "--sign", "-", packaged_binary])
            run(["/usr/bin/codesign", "--verify", "--strict", packaged_binary])
            receipt = package_inventory(release / "package")
            run([release / "package/bin/codex", "--version"], rust_root, env)
            run([release / "package/bin/codex", "--help"], rust_root, env)
            # Do not publish stale-version work if the official CLI updated during compilation.
            if official_version() != version or official_package(version)[0] != official_root:
                raise RuntimeError("Official CLI changed during build; retry for its new version")
            manifest = dict(version=version, commit=commit, patch_sha256=patch_hash(),
                            build_schema=BUILD_SCHEMA, profile="release", target=target,
                            symbol_processing="strip -S -x", signing="ad-hoc",
                            toolchain=toolchain, updater_sha256=file_hash(Path(__file__)),
                            official_package=str(official_root), package_metadata=package_metadata,
                            package_inventory=receipt, binary_sha256=file_hash(release / "codex"),
                            tests=TEST_FILTERS,
                            log=str(log_path))
            (release / "release-lockfile.diff").write_text(lock_diff)
            (release / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
            # Atomically replace only our own link, after every check has succeeded.
            pending = INSTALL / f".current-{os.getpid()}"
            pending.symlink_to(release.name, target_is_directory=True)
            pending.replace(INSTALL / "current")
        print(f"Validated Codex {version}: {INSTALL / 'current/codex'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", help="Release version; default: installed official CLI")
    parser.add_argument("--source", type=Path, help="Use an already patched matching checkout")
    parser.add_argument("--check", action="store_true", help="Check whether rebuilding is needed")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the installed custom version matches")
    parser.add_argument("--launch", action="store_true", help="Rebuild if needed, then launch")
    parser.add_argument("args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    version = args.version or official_version()
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][\w.-]+)?", version):
        raise RuntimeError("Invalid release version")
    if args.check:
        ready = current_matches(version)
        print(f"Official {version}: " + ("custom CLI ready" if ready else "rebuild required"))
        return 0 if ready else 2
    build(version, args.source, args.force)
    if args.launch:
        forwarded = args.args[1:] if args.args[:1] == ["--"] else args.args
        os.execv(str(INSTALL / "current/codex"), ["codex-custom", *forwarded])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(f"Update stopped: {exc}\nNo new custom build was activated. Use the official codex command to recover.", file=sys.stderr)
        sys.exit(1)
