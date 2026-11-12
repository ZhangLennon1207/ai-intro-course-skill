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
            names = ['guide.md', 'tool.py', 'assets/template.html', '.env', '.env.md', 'config.local.json',
                     'signing.pem', 'key.pfx', 'slides.pptx', 'bank.csv',
                     'assets/session.local.html', 'private/answer.html',
                     'private/answer.md', 'teacher-materials/notes.md', '__pycache__/tool.pyc']
            for name in names:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('fictional test content', encoding='utf-8')
            self.assertEqual(set(builder.read_files(root)), {'guide.md', 'tool.py', 'assets/template.html'})

    def test_bundle_validation_rejects_secret_paths_even_if_manually_added(self):
        for path in ('docs/.env', 'tools/.env.md', 'docs/keys.pem', 'docs/config.local.json',
                     'private/answer.md', 'teacher-answers/solution.md'):
            with self.subTest(path=path), self.assertRaises(AssertionError):
                builder.check_bundle({path: b'fictional sensitive content'})

    def test_html_is_checked_for_encoding_and_populated_material_links(self):
        self.assertEqual(builder.check_bundle({'assets/layout.html': '<title>周报</title>'.encode('utf-8')}), 0)
        for content in (b'\xff', 'bad\ufffdtext'.encode('utf-8'),
                        b'https://www.workbuddy.cn' + b'/space/s/' + b'FictionalSecret12345'):
            with self.subTest(content=content), self.assertRaises((AssertionError, UnicodeDecodeError)):
                builder.check_bundle({'assets/layout.html': content})

    def test_markdown_examples_are_not_resolved_as_live_relative_links(self):
        guide = b'[real reference](references/guide.md)\n```markdown\n![example](assets/replace-this.jpg)\n```\n~~~~\n[another example](missing.md)\n~~~~\n'
        self.assertEqual(builder.check_bundle({'SKILL.md': guide, 'references/guide.md': b'# Reference'}), 1)
        with self.assertRaises(AssertionError):
            builder.check_bundle({'SKILL.md': b'[actual broken reference](missing.md)'})


if __name__ == '__main__':
    unittest.main()
