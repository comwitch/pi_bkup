import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('pi_config', Path(__file__).resolve().parents[1] / 'scripts/pi_config.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.agent = self.root / 'source'
        self.agent.mkdir()
        (self.agent / 'settings.json').write_text(json.dumps({'theme': 'dark', 'shellPath': '/bin/bash'}))
        (self.agent / 'auth.json').write_text('SECRET')
        (self.agent / 'sessions').mkdir()
        (self.agent / 'sessions' / 'a.jsonl').write_text('PRIVATE')
        (self.agent / 'prompts').mkdir()
        (self.agent / 'prompts' / 'hello.md').write_text('안녕하세요', encoding='utf-8')
        self.archive = self.root / 'backup.zip'

    def backup(self):
        config.save_archive(self.archive, config.collect(self.agent, portable=True))

    def args(self, dry_run=False):
        return Namespace(archive=self.archive, yes=True, dry_run=dry_run,
                         rollback_dir=self.root / 'rollback')

    def test_roundtrip_and_exclusions(self):
        self.backup()
        entries = config.load_archive(self.archive)
        self.assertEqual(set(entries), {'settings.json', 'prompts/hello.md'})
        self.assertEqual(json.loads(entries['settings.json'][0]), {'theme': 'dark'})
        self.assertIn('shellPath', json.loads((self.agent / 'settings.json').read_text()))
        target = self.root / 'destination'
        target.mkdir()
        (target / 'settings.json').write_text('{"theme":"light"}')
        (target / 'auth.json').write_text('LOCAL SECRET')
        config.restore(self.args(), target)
        self.assertEqual((target / 'auth.json').read_text(), 'LOCAL SECRET')
        self.assertEqual((target / 'prompts/hello.md').read_text(encoding='utf-8'), '안녕하세요')
        rollback = next((self.root / 'rollback').glob('*.zip'))
        self.assertEqual(json.loads(config.load_archive(rollback)['settings.json'][0]), {'theme': 'light'})

    def test_preview_does_not_write(self):
        self.backup()
        target = self.root / 'destination'
        config.restore(self.args(dry_run=True), target)
        self.assertFalse(target.exists())
        self.assertFalse((self.root / 'rollback').exists())

    def test_reject_unsafe_paths(self):
        for name in ['../auth.json', '/settings.json', 'themes/../auth.json',
                     'themes/C:/bad', 'themes\\bad', 'themes/CON.txt', 'themes/a.']:
            self.assertFalse(config.valid_path(name), name)
        self.assertFalse(config.allowed('auth.json'))
        self.assertFalse(config.allowed('extensions/node_modules/a.js'))

    def test_tamper_rejected(self):
        self.backup()
        broken = self.root / 'tampered.zip'
        with zipfile.ZipFile(self.archive) as source, zipfile.ZipFile(broken, 'w') as dest:
            for name in source.namelist():
                dest.writestr(name, b'changed' if name == 'agent/settings.json' else source.read(name))
        with self.assertRaisesRegex(ValueError, 'Checksum'):
            config.load_archive(broken)

    def test_no_overwrite_archive(self):
        self.backup()
        with self.assertRaisesRegex(ValueError, 'overwrite'):
            self.backup()

    def test_failed_restore_rolls_back(self):
        self.backup()
        target = self.root / 'destination'
        target.mkdir()
        (target / 'settings.json').write_text('original')
        real_put = config.put
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated failure')
            return real_put(*args)

        with patch.object(config, 'put', side_effect=fail_once):
            with self.assertRaises(OSError):
                config.restore(self.args(), target)
        self.assertEqual((target / 'settings.json').read_text(), 'original')
        self.assertFalse((target / 'prompts/hello.md').exists())

    def test_symlink_destination_rejected(self):
        self.backup()
        target = self.root / 'destination'
        target.mkdir()
        try:
            (target / 'prompts').symlink_to(self.agent / 'prompts', target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            config.restore(self.args(), target)


if __name__ == '__main__':
    unittest.main()
