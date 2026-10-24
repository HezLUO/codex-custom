"""Candidate notice generation retains usable public sources without privacy bypasses."""
import importlib.util
import json
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
