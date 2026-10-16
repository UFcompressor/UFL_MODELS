"""Registration lifecycle tests using an isolated Git repository."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'register_model.py'
spec = importlib.util.spec_from_file_location('register_model', SCRIPT)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)


class RegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q')
        for name in ('first', 'second', 'third'):
            (self.root / (name + '.pt')).write_bytes(name.encode())
        self.git('add', '.')
        self.git('-c', 'user.name=Test', '-c', 'user.email=test@example.com', 'commit', '-qm', 'checkpoints')
        self.revision = self.git('rev-parse', 'HEAD').strip()
        self.catalog = dict(schema_version=1, default_model='first', models=[self.model('first', 1)])
        self.save()
        (self.root / "README.md").write_text(registry.render_readme(self.catalog, "# Test registry\n"))

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True)

    def model(self, name, number):
        sha = hashlib.sha256(name.encode()).hexdigest()
        return dict(name=name, registration_id=number, display_name=name, description='Test',
                    filename=name + '.pt', sha256=sha, id=f'ufl:{number}@sha256:{sha}',
                    min_dims=3, max_dims=5, architecture='caesar-bcrn-v1',
                    url=f'https://raw.githubusercontent.com/UFcompressor/UFL_MODELS/{self.revision}/{name}.pt')

    def save(self):
        (self.root / 'model_catalog.json').write_text(json.dumps(self.catalog))

    def run_cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), '--catalog', str(self.root / 'model_catalog.json'), *args], capture_output=True, text=True)

    def register(self, name):
        return self.run_cli('--name', name, '--display-name', name, '--description', 'Test',
                            '--checkpoint', str(self.root / (name + '.pt')), '--revision', self.revision)

    def test_readme_tracks_add_and_delete(self):
        result = self.register('second')
        self.assertEqual(result.returncode, 0, result.stderr)
        readme = self.root / 'README.md'
        self.assertIn('second (second) | Active | second.pt', readme.read_text())
        self.assertEqual(self.run_cli('--delete', 'second').returncode, 0)
        self.assertIn('second (second) | Retired | second.pt', readme.read_text())
        self.assertIn('first (first) | Active (default)', readme.read_text())
        self.assertEqual(self.run_cli('--check').returncode, 0)

    def test_refresh_preserves_prose_and_check_detects_stale_list(self):
        readme = self.root / 'README.md'
        readme.write_text(readme.read_text() + "\nKeep these instructions.\n")
        self.catalog['models'][0]['description'] = 'new | details\nnext line'
        self.save()
        self.assertNotEqual(self.run_cli('--check').returncode, 0)
        result = self.run_cli('--update-readme')
        self.assertEqual(result.returncode, 0, result.stderr)
        text = readme.read_text()
        self.assertIn('new &#124; details next line', text)
        self.assertTrue(text.endswith('Keep these instructions.\n'))
        self.assertEqual(self.run_cli('--check').returncode, 0)

    def test_invalid_markers_do_not_change_catalog(self):
        (self.root / 'README.md').write_text(registry.README_START)
        before = (self.root / 'model_catalog.json').read_bytes()
        self.assertNotEqual(self.register('second').returncode, 0)
        self.assertEqual((self.root / 'model_catalog.json').read_bytes(), before)

    def test_committed_checkpoint(self):
        registry.validate(self.catalog, self.root)
        result = self.register('second')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_uncommitted_checkpoint_rejected(self):
        (self.root / 'second.pt').write_bytes(b'changed')
        result = self.register('second')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Committed checkpoint hash mismatch', result.stderr)

    def test_file_absent_from_revision_rejected(self):
        (self.root / 'new.pt').write_bytes(b'new')
        result = self.register('new')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('not committed', result.stderr)

    def test_delete_preserves_history_and_reserves_number(self):
        self.assertEqual(self.register('second').returncode, 0)
        previous = json.loads((self.root / 'model_catalog.json').read_text())
        result = self.run_cli('--delete', 'second')
        self.assertEqual(result.returncode, 0, result.stderr)
        retired = json.loads((self.root / 'model_catalog.json').read_text())
        registry.validate(retired, self.root, previous)
        self.assertEqual(retired['retired_models'][0]['registration_id'], 2)
        self.assertTrue((self.root / 'second.pt').exists())
        self.assertEqual(self.register('third').returncode, 0)
        current = json.loads((self.root / 'model_catalog.json').read_text())
        self.assertEqual(current['models'][-1]['registration_id'], 3)
        result = self.register('second')
        self.assertNotEqual(result.returncode, 0)

    def test_default_deletion_needs_replacement(self):
        before = (self.root / 'model_catalog.json').read_bytes()
        self.assertNotEqual(self.run_cli('--delete', 'first').returncode, 0)
        self.assertEqual(before, (self.root / 'model_catalog.json').read_bytes())
        self.assertEqual(self.register('second').returncode, 0)
        result = self.run_cli('--delete', 'first', '--default-model', 'second')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads((self.root / 'model_catalog.json').read_text())['default_model'], 'second')

    def test_history_cannot_be_erased(self):
        previous = dict(self.catalog, retired_models=[self.model('second', 2)])
        with self.assertRaisesRegex(ValueError, 'cannot be removed'):
            registry.validate(self.catalog, self.root, previous)
        self.catalog['models'].append(self.model('second', 2))
        with self.assertRaisesRegex(ValueError, 'cannot be reactivated'):
            registry.validate(self.catalog, self.root, previous)


if __name__ == '__main__':
    unittest.main()
