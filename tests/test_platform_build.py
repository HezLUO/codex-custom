"""Candidate notice generation retains usable public sources without privacy bypasses."""
import importlib.util
import json
import struct
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('native_builder', ROOT / 'scripts/build-platform.py')
builder = importlib.util.module_from_spec(spec); spec.loader.exec_module(builder)


class NoticeGenerationTests(unittest.TestCase):
    def test_macho_and_pe_constant_sections_keep_their_layout(self):
        prefix = '/' + 'home/fixture-ci'
        payload = (prefix + '/source.cc\0').encode()
        macho = bytearray(512)
        macho[:8] = bytes.fromhex('cffaedfe07000001')
        struct.pack_into('<II', macho, 16, 1, 152)
        struct.pack_into('<II', macho, 32, 0x19, 152)
        struct.pack_into('<I', macho, 96, 1)
        macho[104:113] = b'__cstring'
        macho[120:126] = b'__TEXT'
        struct.pack_into('<Q', macho, 144, len(payload))
        struct.pack_into('<I', macho, 152, 256)
        macho[256:256 + len(payload)] = payload
        pe = bytearray(768); pe[:2] = b'MZ'
        struct.pack_into('<I', pe, 60, 64)
        pe[64:70] = b'PE\0\0\x64\x86'
        struct.pack_into('<H', pe, 70, 1)
        struct.pack_into('<H', pe, 84, 224)
        struct.pack_into('<H', pe, 88, 0x20b)
        struct.pack_into('<II', pe, 328, len(payload), 512)
        struct.pack_into('<I', pe, 348, 0x40000040)
        pe[512:512 + len(payload)] = payload
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'codex'
            for target, data, offset in [('x86_64-apple-darwin', macho, 256), ('x86_64-pc-windows-msvc', pe, 512)]:
                path.write_bytes(data)
                self.assertEqual(builder.redact_build_paths(path, target, [prefix]), 1)
                after = path.read_bytes()
                self.assertEqual(len(after), len(data))
                self.assertEqual(after[:offset], data[:offset])
                self.assertEqual(after[offset + len(prefix):], data[offset + len(prefix):])
                builder.artifact.privacy_check(after)

    def test_only_known_build_paths_in_constant_sections_are_replaced(self):
        prefix = '/' + 'home/fixture-ci'
        payload = (prefix + '/source/file.cc\0').encode()
        def elf(flags):
            data = bytearray(384)
            data[:6] = b'\x7fELF\x02\x01'
            struct.pack_into('<H', data, 18, 62)
            struct.pack_into('<Q', data, 40, 256)
            struct.pack_into('<HH', data, 58, 64, 2)
            struct.pack_into('<IIQQQQ', data, 320, 0, 1, flags, 0, 64, len(payload))
            data[64:64 + len(payload)] = payload
            return bytes(data)
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / 'codex'
            before = elf(2); binary.write_bytes(before)
            self.assertEqual(builder.redact_build_paths(binary, 'x86_64-unknown-linux-musl', [prefix]), 1)
            after = binary.read_bytes()
            self.assertEqual(len(before), len(after))
            self.assertEqual(before[:64], after[:64])
            self.assertEqual(before[64 + len(prefix):], after[64 + len(prefix):])
            builder.artifact.privacy_check(after)
            before = elf(6); binary.write_bytes(before)
            with self.assertRaisesRegex(RuntimeError, 'outside approved'):
                builder.redact_build_paths(binary, 'x86_64-unknown-linux-musl', [prefix])
            self.assertEqual(binary.read_bytes(), before)
            binary.write_bytes(elf(2))
            builder.redact_build_paths(binary, 'x86_64-unknown-linux-musl', ['/' + 'home/other-ci'])
            with self.assertRaises(builder.artifact.ReleaseError):
                builder.artifact.privacy_check(binary.read_bytes())

    def test_credentials_adjacent_to_other_binary_literals_still_fail(self):
        for prefix in (b'\0', b'field', b'const_', b'prefix-'):
            for marker in (b'sk' + b'-', b'gh' + b'p_', b'Bearer '):
                with self.assertRaises(builder.artifact.ReleaseError):
                    builder.artifact.privacy_check(prefix + marker + b'fixturesecretvalue' * 3)

    def test_home_crate_source_remains_usable_in_both_notice_and_inventory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'LICENSE').write_text('fixture Apache license text')
            cli = root / 'cli'; cli.mkdir(); home = root / 'home-crate'; home.mkdir()
            (home / 'LICENSE-MIT').write_text('fixture original MIT license text')
            tool = root / 'toolchain'; standard = tool / 'share/doc/rust'; standard.mkdir(parents=True)
            (standard / 'COPYRIGHT-library.html').write_text('<p>fixture standard library notices</p>')
            out = root / 'output'; out.mkdir()
            metadata = {'packages': [
                dict(id='cli', name='codex-cli', version='0.164.0', source=None, manifest_path=str(cli / 'Cargo.toml'), license='Apache-2.0', authors=[]),
                dict(id='home', name='home', version='0.5.12', source='registry+https://github.com/rust-lang/crates.io-index', manifest_path=str(home / 'Cargo.toml'), license='MIT', authors=[]),
            ], 'resolve': {'nodes': [dict(id='cli', deps=[{'pkg': 'home'}]), dict(id='home', deps=[])]}}
            with patch.object(builder, 'run', return_value=str(tool / 'bin/rustc')):
                builder.collect_notices(metadata, source, out, 'x86_64-unknown-linux-musl')
            notice = (out / 'DEPENDENCY-NOTICES.txt').read_text()
            inventory = json.loads((out / 'license-review.json').read_text())
            self.assertEqual(inventory['missing_original_texts'], [])
            url = next(x['source'] for x in inventory['inventory'] if x['name'] == 'home')
            self.assertEqual(url, 'https://crates.io/api/v1/crates/h%6fme/0.5.12/download')
            self.assertIn(url, notice)
            builder.artifact.privacy_check(notice.encode())
            builder.artifact.privacy_check(json.dumps(inventory).encode())


if __name__ == '__main__': unittest.main()
