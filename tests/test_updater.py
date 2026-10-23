import importlib.util
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "update-codex-custom.py"
spec = importlib.util.spec_from_file_location("updater", path)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


def make_official_package(root):
    (root / "bin").mkdir(parents=True)
    (root / "codex-path").mkdir()
    (root / "codex-resources/voice").mkdir(parents=True)
    for relative, contents in [("bin/codex", b"official"),
                               ("bin/codex-code-mode-host", b"helper"),
                               ("codex-path/rg", b"ripgrep")]:
        item = root / relative
        item.write_bytes(contents)
        item.chmod(0o755)
    (root / "codex-resources/voice/data").write_bytes(b"voice resource")
    (root / "codex").symlink_to("bin/codex")
    metadata = {"layoutVersion": 1, "version": "0.164.0", "target": "aarch64-apple-darwin",
                "variant": "codex", "entrypoint": "bin/codex",
                "resourcesDir": "codex-resources", "pathDir": "codex-path"}
    (root / "codex-package.json").write_text(json.dumps(metadata))
    return metadata


class UpdaterTests(unittest.TestCase):
    def test_launcher_preserves_daemon_mode_and_forwards_user_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(path.parent / "codex-custom", root / "codex-custom")
            (root / "update-codex-custom.py").write_text(
                "import json, os, sys\nprint(json.dumps({'args': sys.argv[1:], 'status_line': os.environ.get('CODEX_CUSTOM_STATUS_LINE')}))\n")
            environment = os.environ.copy()
            environment.pop("CODEX_CUSTOM_STATUS_LINE", None)
            environment["CODEX_CUSTOM_BUILD_FROM_SOURCE"] = "1"
            result = subprocess.run([str(root / "codex-custom"), "resume", "--last",
                                     "-c", 'model="example"'],
                                    check=True, capture_output=True, text=True, env=environment)
            captured = json.loads(result.stdout)
            forwarded = captured["args"]
            self.assertNotIn("--no-daemon", forwarded)
            self.assertEqual(forwarded[-4:], ["resume", "--last", "-c", 'model="example"'])
            self.assertEqual(forwarded[:2], ["--launch", "--"])
            self.assertEqual(forwarded[2:], ["resume", "--last", "-c", 'model="example"'])
            self.assertIn("context-details", json.loads(captured["status_line"]))
            environment["CODEX_CUSTOM_STATUS_LINE"] = '["context-details"]'
            custom = subprocess.run([str(root / "codex-custom"), "--version"],
                                    check=True, capture_output=True, text=True, env=environment)
            self.assertEqual(json.loads(custom.stdout), {
                "args": ["--launch", "--", "--version"],
                "status_line": '["context-details"]',
            })

    def test_staged_package_preserves_helpers_resources_and_official_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = root / "standalone/releases/official"
            make_official_package(official)
            custom = root / "compiled"
            custom.write_bytes(b"patched release")
            custom.chmod(0o755)
            release = root / "release"
            release.mkdir()
            updater.stage_package(official, custom, release)
            self.assertEqual((release / "codex").read_bytes(), b"patched release")
            self.assertTrue((release / "package").is_symlink())
            self.assertEqual((release / "package").resolve().parent.parent.name, "codex-custom")
            self.assertEqual((official / "bin/codex").read_bytes(), b"official")
            self.assertEqual((release / "package/bin/codex-code-mode-host").read_bytes(), b"helper")
            self.assertEqual((release / "package/codex-resources/voice/data").read_bytes(), b"voice resource")
            self.assertEqual((release / "package/codex").readlink(), Path("bin/codex"))

    def test_rejects_non_standalone_layout_and_missing_package_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            arbitrary = root / "arbitrary-package"
            make_official_package(arbitrary)
            with patch.object(updater, "OFFICIAL", arbitrary / "bin/codex"):
                with self.assertRaisesRegex(RuntimeError, "standalone/releases"):
                    updater.official_package("0.164.0")
            official = root / "standalone/releases/official"
            make_official_package(official)
            with patch.object(updater, "OFFICIAL", official / "bin/codex"):
                self.assertEqual(updater.official_package("0.164.0")[0], official.resolve())
                (official / "codex-path/rg").unlink()
                with self.assertRaisesRegex(RuntimeError, "missing executable"):
                    updater.official_package("0.164.0")

    def test_development_release_is_not_accepted_as_official_parity_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "old-development-build"
            release.mkdir()
            (root / "current").symlink_to(release.name)
            binary = release / "codex"
            binary.write_bytes(b"old dev executable")
            binary.chmod(0o755)
            (release / "manifest.json").write_text(json.dumps({
                "version": "0.164.0", "patch_sha256": updater.patch_hash(),
                "binary_sha256": updater.hashlib.sha256(binary.read_bytes()).hexdigest(),
            }))
            with patch.object(updater, "INSTALL", root):
                self.assertFalse(updater.current_matches("0.164.0"))

    def test_local_version_stamping_preserves_external_pins(self):
        baseline = '''version = 4
[[package]]
name = "local"
version = "0.0.0"
[[package]]
name = "external"
version = "1.0.0"
source = "registry+https://github.com/rust-lang/crates.io-index"
checksum = "unchanged"
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / "Cargo.lock"
            lock.write_text(baseline)
            metadata = {"packages": [{"name": "local", "version": "0.164.0", "source": None}]}
            updater.normalize_local_lock_versions(root, metadata, baseline)
            expected = baseline.replace('version = "0.0.0"', 'version = "0.164.0"')
            self.assertEqual(lock.read_text(), expected)
            updater.normalize_local_lock_versions(root, metadata, baseline)
            self.assertEqual(lock.read_text(), expected)
            lock.write_text(expected.replace('version = "1.0.0"', 'version = "1.1.0"'))
            with self.assertRaisesRegex(RuntimeError, "beyond workspace"):
                updater.normalize_local_lock_versions(root, metadata, baseline)

    def test_manifest_rejects_wrong_version_patch_and_tampered_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            official = root / "standalone/releases/official"
            metadata = make_official_package(official)
            build = root / "release"
            build.mkdir()
            (root / "current").symlink_to("release")
            binary = root / "compiled"
            binary.write_bytes(b"validated executable")
            binary.chmod(0o755)
            receipt = updater.stage_package(official, binary, build)
            manifest = {"version": "0.164.0", "build_schema": updater.BUILD_SCHEMA,
                        "profile": "release", "patch_sha256": updater.patch_hash(),
                        "updater_sha256": updater.file_hash(path),
                        "official_package": str(official.resolve()), "package_metadata": metadata,
                        "package_inventory": receipt}
            (build / "manifest.json").write_text(json.dumps(manifest))
            with patch.object(updater, "INSTALL", root), patch.object(updater, "OFFICIAL", official / "bin/codex"):
                self.assertTrue(updater.current_matches("0.164.0"))
                for key, invalid in [("profile", "dev"), ("updater_sha256", "obsolete-recipe")]:
                    original = manifest[key]
                    manifest[key] = invalid
                    (build / "manifest.json").write_text(json.dumps(manifest))
                    self.assertFalse(updater.current_matches("0.164.0"))
                    manifest[key] = original
                (build / "manifest.json").write_text(json.dumps(manifest))
                self.assertFalse(updater.current_matches("0.165.0"))
                with patch.object(updater, "PATCH", root / "missing-patch"):
                    self.assertFalse(updater.current_matches("0.164.0"))
                (build / "package/bin/codex").write_bytes(b"modified executable")
                self.assertFalse(updater.current_matches("0.164.0"))
                (build / "package/bin/codex").write_bytes(b"validated executable")
                (build / "package/bin/codex-code-mode-host").write_bytes(b"modified helper")
                self.assertFalse(updater.current_matches("0.164.0"))

    def test_failed_source_validation_preserves_active_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release").mkdir()
            (root / "current").symlink_to("release")
            with patch.object(updater.platform, "system", return_value="Darwin"), patch.object(updater.platform, "machine", return_value="arm64"), patch.object(updater, "official_package"), patch.object(updater, "INSTALL", root), patch.object(updater, "WORK", root / "work"):
                with self.assertRaises((RuntimeError, OSError)):
                    updater.build("0.164.0", root / "nonexistent-source")
            self.assertEqual((root / "current").readlink(), Path("release"))

    def test_force_rebuild_does_not_skip_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release").mkdir()
            (root / "current").symlink_to("release")
            with patch.object(updater.platform, "system", return_value="Darwin"), patch.object(updater.platform, "machine", return_value="arm64"), patch.object(updater, "official_package"), patch.object(updater, "INSTALL", root), patch.object(updater, "WORK", root / "work"), patch.object(updater, "current_matches", return_value=True):
                updater.build("0.164.0", root / "missing-source")
                with self.assertRaises(OSError):
                    updater.build("0.164.0", root / "missing-source", force=True)
            self.assertEqual((root / "current").readlink(), Path("release"))


    def test_paths_are_configurable_and_do_not_depend_on_checkout_parent(self):
        with tempfile.TemporaryDirectory(prefix="custom paths ") as directory:
            root = Path(directory).resolve()
            environment = os.environ.copy()
            environment.update(CODEX_CUSTOM_STATE_DIR=str(root / "state"),
                               CODEX_CUSTOM_CACHE_DIR=str(root / "cache"),
                               CODEX_OFFICIAL_BIN=str(root / "official"))
            result = subprocess.run([
                "python3", "-c",
                "import importlib.util,json,sys; "
                "s=importlib.util.spec_from_file_location('u',sys.argv[1]); "
                "u=importlib.util.module_from_spec(s); s.loader.exec_module(u); "
                "print(json.dumps([str(u.INSTALL),str(u.WORK),str(u.OFFICIAL)]))", str(path)
            ], cwd="/", env=environment, check=True, text=True, capture_output=True)
            self.assertEqual(json.loads(result.stdout), [str(root / name) for name in ("state", "cache", "official")])
            self.assertEqual(list(root.iterdir()), [])

    def test_unsupported_platform_stops_before_creating_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "state"
            with patch.object(updater.platform, "system", return_value="Linux"), patch.object(updater, "INSTALL", root):
                with self.assertRaisesRegex(RuntimeError, "macOS Apple Silicon"):
                    updater.build("0.164.0")
            self.assertFalse(root.exists())

    def test_build_pipeline_switches_only_after_all_checks(self):
        # Exercise orchestration with deterministic tool responses, not a Rust compiler.
        for scenario in ("success", "compiler-failure", "no-tests", "signature-failure", "official-update"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                official = root / "standalone/releases/official"
                make_official_package(official)
                before = updater.package_inventory(official)
                state = root / "state"
                state.mkdir()
                (state / "old").mkdir()
                (state / "current").symlink_to("old")
                work = root / "cache"
                commands = []

                class Process:
                    def __init__(self, args, **kwargs):
                        commands.append(args)
                        output = ""
                        self.code = 0
                        if args[:3] == ["git", "worktree", "add"]:
                            rust = Path(args[4]) / "codex-rs"
                            rust.mkdir(parents=True)
                            (rust / "rust-toolchain.toml").write_text('channel = "1.99.1"')
                            (rust / "Cargo.lock").write_text("version = 4\n")
                        elif args[:3] == ["git", "rev-parse", "HEAD"]:
                            output = "baseline-commit\n"
                        elif "metadata" in args:
                            output = '{"packages": []}'
                        elif args[:3] == ["git", "show", "HEAD:codex-rs/Cargo.lock"]:
                            output = "version = 4\n"
                        elif "test" in args:
                            output = "test result: ok. 0 passed" if scenario == "no-tests" else "test result: ok. 2 passed"
                        elif "build" in args and "--release" in args:
                            if scenario == "compiler-failure":
                                self.code = 1
                            binary = work / "target/aarch64-apple-darwin/release/codex"
                            binary.parent.mkdir(parents=True, exist_ok=True)
                            binary.write_bytes(b"release-binary")
                            binary.chmod(0o755)
                        elif args[-1:] == ["--version"]:
                            output = "codex-cli 0.164.0\n"
                        elif args[0] == "/usr/bin/codesign" and "--verify" in args and scenario == "signature-failure":
                            self.code = 1
                        self.stdout = io.StringIO(output)

                    def wait(self):
                        return self.code

                with patch.object(updater.platform, "system", return_value="Darwin"), \
                     patch.object(updater.platform, "machine", return_value="arm64"), \
                     patch.object(updater, "INSTALL", state), patch.object(updater, "WORK", work), \
                     patch.object(updater, "OFFICIAL", official / "bin/codex"), \
                     patch.object(updater.shutil, "which", side_effect=lambda name: "/tools/" + name), \
                     patch.object(updater.subprocess, "Popen", Process), \
                     patch.object(updater, "official_version", return_value="0.165.0" if scenario == "official-update" else "0.164.0"):
                    if scenario == "success":
                        updater.build("0.164.0")
                        self.assertNotEqual((state / "current").readlink(), Path("old"))
                        self.assertTrue(updater.current_matches("0.164.0"))
                        self.assertEqual((state / "current/codex").read_bytes(), b"release-binary")
                        test_commands = [cmd for cmd in commands if "test" in cmd]
                        self.assertEqual([cmd[-1] for cmd in test_commands], updater.TEST_FILTERS)
                        self.assertTrue(any("--release" in cmd and "--locked" in cmd for cmd in commands))
                        self.assertTrue(any(cmd[:2] == ["/usr/bin/codesign", "--verify"] for cmd in commands))
                    else:
                        with self.assertRaises(RuntimeError):
                            updater.build("0.164.0")
                        self.assertEqual((state / "current").readlink(), Path("old"))
                self.assertEqual(updater.package_inventory(official), before)
                self.assertTrue((state / "old").is_dir())


if __name__ == "__main__":
    unittest.main()
