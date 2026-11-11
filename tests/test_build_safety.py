"""Regression coverage for accidentally packaging local secrets or ignored data."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'tools/build_packages.py'
SPEC = importlib.util.spec_from_file_location('course_builder', SCRIPT)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


class BuildSafetyTests(unittest.TestCase):
    def test_source_collection_excludes_local_secrets_and_original_materials(self):
        with tempfile.TemporaryDirectory(prefix='course-package-safety-') as tmp:
            root = Path(tmp)
            names = ['guide.md', 'tool.py', '.env', '.env.md', 'config.local.json',
                     'signing.pem', 'key.pfx', 'slides.pptx', 'bank.csv',
                     'private/answer.md', 'teacher-materials/notes.md', '__pycache__/tool.pyc']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fictional test content', encoding='utf-8')
            self.assertEqual(set(builder.read_files(root)), {'guide.md', 'tool.py'})

    def test_bundle_validation_rejects_secret_paths_even_if_manually_added(self):
        for path in ('docs/.env', 'tools/.env.md', 'docs/keys.pem', 'docs/config.local.json',
                     'private/answer.md', 'teacher-answers/solution.md'):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                builder.check_bundle({path: b'fictional sensitive content'})


if __name__ == '__main__':
    unittest.main()
