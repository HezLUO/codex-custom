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
    def test_reviewed_license_requires_exact_bytes_and_declared_option(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'LICENSE').write_text('fixture complete Apache terms')
            dependency = root / 'dependency'; dependency.mkdir()
            original = b'fixture original licensing declaration and attribution'
            url = 'https://raw.githubusercontent.com/example/fixture/' + 'a' * 40 + '/LICENSE'
            scripts = root / 'scripts'; scripts.mkdir()
            (scripts / 'native-license-sources.json').write_text(json.dumps({'fixture-dep@1.0.0': [
                dict(url=url, sha256=builder.artifact.digest(original), selected_license='Apache-2.0')]}))
            tool = root / 'toolchain'; standard = tool / 'share/doc/rust'; standard.mkdir(parents=True)
            (standard / 'COPYRIGHT-library.html').write_text('<p>fixture Rust notices</p>')
            dep = dict(id='dep', name='fixture-dep', version='1.0.0',
                       source='registry+https://github.com/rust-lang/crates.io-index',
                       manifest_path=str(dependency / 'Cargo.toml'), license='MIT OR Apache-2.0', authors=[])
            metadata = {'packages': [dict(id='cli', name='codex-cli', version='0.164.0', source=None,
                         manifest_path=str(source / 'Cargo.toml'), license='Apache-2.0', authors=[]), dep],
                         'resolve': {'nodes': [dict(id='cli', deps=[{'pkg': 'dep'}]), dict(id='dep', deps=[])]}}
            for index, bad_bytes, license_expression in [(0, False, 'MIT OR Apache-2.0'), (1, True, 'MIT OR Apache-2.0'), (2, False, 'MIT')]:
                output = root / str(index); output.mkdir(); dep['license'] = license_expression
                def fetch(_url, path, _limit):
                    self.assertEqual(_url, url)
                    path.write_bytes(b'fixture changed bytes' if bad_bytes else original)
                with patch.object(builder, 'ROOT', root), patch.object(builder, 'fetch', side_effect=fetch), patch.object(builder, 'run', return_value=str(tool / 'bin/rustc')):
                    if index:
                        with self.assertRaises(RuntimeError):
                            builder.collect_notices(metadata, source, output, 'x86_64-unknown-linux-musl')
                        self.assertFalse((output / 'DEPENDENCY-NOTICES.txt').exists())
                    else:
                        report = builder.collect_notices(metadata, source, output, 'x86_64-unknown-linux-musl')
                        self.assertEqual(report['missing_original_texts'], [])
                        notice = (output / 'DEPENDENCY-NOTICES.txt').read_text()
                        self.assertIn(original.decode(), notice)
                        self.assertIn('Explicitly reviewed Apache-2.0 terms', notice)

    def test_declared_workspace_license_is_read_but_external_file_is_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'LICENSE').write_text('fixture Apache terms')
            workspace = root / 'dependency'; workspace.mkdir(); (workspace / '.git').mkdir()
            member = workspace / 'member'; member.mkdir()
            terms = workspace / 'terms.custom'; terms.write_text('fixture original MIT terms and attribution')
            outside = root / 'outside.custom'; outside.write_text('fixture external private data')
            (member / 'copying.rs').write_text('pub struct NSCopyingFixture;')
            tool = root / 'toolchain'; standard = tool / 'share/doc/rust'; standard.mkdir(parents=True)
            (standard / 'COPYRIGHT-library.html').write_text('<p>fixture Rust notices</p>')
            package = dict(id='dependency', name='fixture-workspace-dependency', version='1.0.0',
                           source='git+https://github.com/example/fixture#' + 'a' * 40,
                           manifest_path=str(member / 'Cargo.toml'), license='MIT', authors=[])
            metadata = {'packages': [dict(id='cli', name='codex-cli', version='0.164.0', source=None,
                         manifest_path=str(source / 'Cargo.toml'), license='Apache-2.0', authors=[]), package],
                         'resolve': {'nodes': [dict(id='cli', deps=[{'pkg': 'dependency'}]), dict(id='dependency', deps=[])]}}
            for index, license_file in enumerate((terms, outside)):
                package['license_file'] = str(license_file)
                output = root / str(index); output.mkdir()
                with patch.object(builder, 'run', return_value=str(tool / 'bin/rustc')):
                    report = builder.collect_notices(metadata, source, output, 'x86_64-unknown-linux-musl')
                notice = (output / 'DEPENDENCY-NOTICES.txt').read_text()
                if index == 0:
                    self.assertEqual(report['missing_original_texts'], [])
                    self.assertIn(terms.read_text(), notice)
                else:
                    self.assertEqual(report['missing_original_texts'][0]['name'], package['name'])
                    self.assertNotIn(outside.read_text(), notice)

    def test_original_line_comment_attribution_retained_with_apache_option(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'LICENSE').write_text('fixture complete Apache terms')
            dependency = root / 'dependency'; dependency.mkdir()
            header = '// Copyright fixture original contributors\n// Licensed under Apache-2.0 or MIT, at your option.\n'
            (dependency / 'lib.rs').write_text(header + '\npub fn fixture() {}\n')
            tool = root / 'toolchain'; standard = tool / 'share/doc/rust'; standard.mkdir(parents=True)
            (standard / 'COPYRIGHT-library.html').write_text('<p>fixture Rust notices</p>')
            metadata = {'packages': [dict(id='cli', name='codex-cli', version='0.164.0', source=None,
                         manifest_path=str(source / 'Cargo.toml'), license='Apache-2.0', authors=[]),
                         dict(id='dep', name='fixture-line-header', version='1.0.0',
                         source='registry+https://github.com/rust-lang/crates.io-index',
                         manifest_path=str(dependency / 'Cargo.toml'), license='MIT OR Apache-2.0', authors=[])],
                         'resolve': {'nodes': [dict(id='cli', deps=[{'pkg': 'dep'}]), dict(id='dep', deps=[])]}}
            output = root / 'out'; output.mkdir()
            with patch.object(builder, 'run', return_value=str(tool / 'bin/rustc')):
                report = builder.collect_notices(metadata, source, output, 'x86_64-unknown-linux-musl')
            self.assertEqual(report['missing_original_texts'], [])
            notice = (output / 'DEPENDENCY-NOTICES.txt').read_text()
            self.assertIn(header, notice)
            self.assertIn('Selected Apache-2.0 full terms', notice)

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

    def test_reviewed_native_literals_require_exact_bytes(self):
        # Actual public TUI labels/enum metadata merged by the Linux linker.
        literals = [
            b'Bearer ' + b'tokenOAuthConversationStartParamsoutput_modalityinitial_items_countInvalidLanguageInvalidSubtagDuplicatedExtensionKnownDomainPathUriGoProProLiteProMaxSelfServeBusinessProLiteSelfServeBusinessUsageBasedEnt26EnterpriseCbpAutomationEnterpriseCbpUsageBasedEnterpriseEduEduPlusEduProSciSciPlusDataErrormarkerstr_contextsilentBindTcpConnectTcpExecuteWriteFileReadDirRemoveDirRemoveFileMakeDirMakeRegMakeBlockMakeSymReferRefreshTokenFailedErrorhas_detailed_explanationhas_steerhas_review_targetExpiredExhaustedRevokedDataMarkerId',
            b'sk' + b'-progresspull-request-numberbranch-changesapproval-modecontext-window-sizeraw-outputworkspace-headlinecontext-detailsoptionModelNameModelWithReasoningCurrentDirProjectRootGitBranchPullRequestNumberBranchChangesStatusPermissionsApprovalModeContextUsedFiveHourLimitWeeklyLimitCodexVersionContextWindowSizeUsedTokensTotalOutputTokensThreadCreditsEstimatedThreadCostSessionIdRawOutputThreadNameThreadTitleWorkspaceHeadlineTaskProgressContextDetailsTrustedFileidevimsetup-default-sandboxexperimentalimportnewappcompactrecapbtwexportrawdaemoncdpwdusagedebug-configstatuslinelogoutrolloutpscleartest-approvaldebug-m-dropdebug-m-updatePreContextPrevChunkNextChunkInvalidOffsetutf-8',
            b'sk' + b'-progresspull-request-numberbranch-changesapproval-modecontext-window-sizeraw-outputworkspace-headlinecontext-detailsoptionModelNameModelWithReasoningCurrentDirProjectRootHostnameGitBranchPullRequestNumberBranchChangesStatusPermissionsApprovalModeContextRemainingContextUsedFiveHourLimitWeeklyLimitCodexVersionContextWindowSizeUsedTokensTotalInputTokensTotalOutputTokensThreadCreditsEstimatedThreadCostSessionIdFastModeDaybreakRawOutputThreadNameThreadTitleWorkspaceHeadlineTaskProgressContextDetailsTrustedFilePreContextPrevChunkNextChunkInvalidOffset',
        ]
        for value in literals:
            builder.artifact.privacy_check(value)
            with self.assertRaises(builder.artifact.ReleaseError):
                builder.artifact.privacy_check(value + b'fixturesecretvalue')

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
