import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_install_launch_from_space_path_and_uninstall(self):
        with tempfile.TemporaryDirectory(prefix='candidate space ') as directory:
            root = Path(directory)
            source = root / "source ' checkout"
            source.mkdir()
            launcher = source / 'codex-custom'
            launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            launcher.chmod(0o755)
            target = root / 'bin'
            with patch.object(installer, 'ROOT', source), patch('sys.argv', ['install', '--bin-dir', str(target)]):
                installer.main()
                installer.main()
                result = subprocess.run([str(target / 'codex-custom'), 'resume', 'a b', '$(false)'],
                                        cwd='/', check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.splitlines(), ['resume', 'a b', '$(false)'])
                with patch('sys.argv', ['install', '--bin-dir', str(target), '--uninstall']):
                    installer.main()
                self.assertFalse(os.path.lexists(target / 'codex-custom'))

    def test_refuses_existing_file_and_broken_symlink_for_install_and_uninstall(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'codex-custom'
            for symlink in (False, True):
                if symlink:
                    target.symlink_to(root / 'missing')
                else:
                    target.write_text('existing installation')
                for uninstall in (False, True):
                    args = ['install', '--bin-dir', str(root)] + (['--uninstall'] if uninstall else [])
                    with patch('sys.argv', args), self.assertRaises(RuntimeError):
                        installer.main()
                    self.assertTrue(os.path.lexists(target))
                target.unlink()
