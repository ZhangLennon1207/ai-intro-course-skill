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

    def test_reviewed_example_assets_are_collected_only_for_the_intended_skill(self):
        assets = {
            'ai-course-slides': {'assets/default-template.pptx'},
            'ai-course-handout': {'assets/knowledge-points-example.csv'},
            'ai-course-assessment': {'assets/knowledge-points-example.csv'},
            'ai-course-analytics': {'assets/knowledge-points-example.csv', 'assets/demo_answers.csv'},
            'ai-course-visual': set(),
            'unrelated-skill': set(),
        }
        candidates = {'assets/default-template.pptx', 'assets/knowledge-points-example.csv',
                      'assets/demo_answers.csv', 'assets/grades.csv', 'assets/teacher-template.pptx',
                      'assets/private-bank.csv', 'assets/student-roster.csv', 'assets/original.pdf',
                      'assets/teachers-notes.docx', 'assets/diagram.svg',
                      'private/assets/knowledge-points-example.csv',
                      'private/ai-course-slides/assets/default-template.pptx',
                      'teacher-materials/ai-course-slides/assets/default-template.pptx',
                      'assets/session.local.csv', '.env.csv'}
        with tempfile.TemporaryDirectory(prefix='production-example-safety-') as tmp:
            for skill_id, accepted in assets.items():
                root = Path(tmp) / skill_id
                for name in candidates | {'SKILL.md', 'scripts/generator.py'}:
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b'fictional fixture bytes')
                with self.subTest(skill_id=skill_id):
                    self.assertEqual(set(builder.read_files(root)),
                                     {'SKILL.md', 'scripts/generator.py'} | accepted)

    def test_contextual_example_allowance_survives_known_packaging_layouts(self):
        expected = {
            'ai-course-slides': {'assets/default-template.pptx'},
            'ai-course-handout': {'assets/knowledge-points-example.csv'},
            'ai-course-assessment': {'assets/knowledge-points-example.csv'},
            'ai-course-analytics': {'assets/knowledge-points-example.csv', 'assets/demo_answers.csv'},
        }
        for skill_id, names in expected.items():
            for name in names:
                with self.subTest(skill_id=skill_id, asset=name):
                    self.assertEqual(builder.check_bundle({name: b'fictional fixture bytes'}, context=skill_id), 0)
                    for prefix in (f'addons/{skill_id}/', f'.codebuddy/skills/{skill_id}/',
                                   f'assets/course-suite/.codebuddy/skills/{skill_id}/'):
                        self.assertEqual(builder.check_bundle({prefix + name: b'fictional fixture bytes'}), 0)
                    with self.assertRaises(AssertionError):
                        builder.check_bundle({name: b'fictional fixture bytes'}, context='unrelated-skill')
                    with self.assertRaises(AssertionError):
                        builder.check_bundle({'private/' + skill_id + '/' + name: b'fictional fixture bytes'}, context=skill_id)

    def test_other_grades_templates_and_course_originals_are_not_publishable_by_context(self):
        private_assets = ('assets/grades.csv', 'assets/answers.csv', 'assets/student-roster.csv',
                          'assets/real-template.pptx', 'assets/teacher-lecture.pptx',
                          'assets/course.pdf', 'assets/lecture.docx', 'assets/private-key.pem')
        for skill_id in ('ai-course-slides', 'ai-course-handout', 'ai-course-assessment',
                         'ai-course-analytics', 'ai-course-visual'):
            for name in private_assets:
                with self.subTest(skill_id=skill_id, asset=name), self.assertRaises(AssertionError):
                    builder.check_bundle({name: b'fictional private material'}, context=skill_id)
        # Naming an asset like another Skill's reviewed example does not grant
        # the current Skill a generic CSV or Office-file publishing exception.
        for skill_id, name in (('ai-course-slides', 'assets/knowledge-points-example.csv'),
                              ('ai-course-visual', 'assets/default-template.pptx'),
                              ('ai-course-handout', 'assets/demo_answers.csv')):
            with self.subTest(skill_id=skill_id, asset=name), self.assertRaises(AssertionError):
                builder.check_bundle({name: b'fictional fixture bytes'}, context=skill_id)

    def test_allowed_csv_examples_are_still_checked_for_text_and_material_links(self):
        sensitive_link = b'https://www.workbuddy.cn' + b'/space/s/' + b'FictionalSecret12345'
        for content in (b'\xff', 'invalid\ufffdtext'.encode('utf-8'), sensitive_link):
            with self.subTest(content=content), self.assertRaises((AssertionError, UnicodeDecodeError)):
                builder.check_bundle({'assets/knowledge-points-example.csv': content},
                                     context='ai-course-assessment')


if __name__ == '__main__':
    unittest.main()
