"""Exercise the real delivered setup ZIP in an isolated local project."""
from __future__ import annotations

import hashlib
import ast
import csv
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_IDS = ('ai-course-slides', 'ai-course-handout', 'ai-course-assessment',
                  'ai-course-analytics', 'ai-course-visual')
PRODUCTION_SCRIPTS = {
    'ai-course-slides': {'build_deck.py', 'coverage_check.py', 'envcheck.py'},
    'ai-course-handout': {'build_handout.py', 'from_slides.py'},
    'ai-course-assessment': {'build_paper.py', 'make_blueprint.py', 'build_rubric.py'},
    'ai-course-analytics': {'grade.py', 'charts.py', 'merge_scores.py'},
    'ai-course-visual': {'build_figures.py'},
}
LOCAL_HELPERS = {'deid', 'kp', 'envcheck', 'coverage_check', 'font_check',
                 'voice_check', 'inspect_template', 'fetch_textbook', 'build_figures'}

# A delivered file installer may read companion sources, but must not execute
# them, create a subprocess, or connect to an account/scheduler/publisher.
GUARDED_INSTALLER = '''
import pathlib, runpy, sys
installer = pathlib.Path(sys.argv[1]).resolve()
payload = pathlib.Path(sys.argv[3]).resolve()
def guard(event, args):
    if event in {'subprocess.Popen', 'socket.connect', 'socket.getaddrinfo', 'os.system',
                 'os.exec', 'os.posix_spawn'}:
        raise AssertionError('File installation attempted external execution: ' + event)
    if event == 'exec':
        filename = pathlib.Path(args[0].co_filename)
        if filename.is_absolute() and filename.resolve().is_relative_to(payload):
            raise AssertionError('File installation executed a companion program')
sys.addaudithook(guard)
sys.argv = [str(installer), *sys.argv[2:]]
runpy.run_path(str(installer), run_name='__main__')
'''


def guarded_command(installer: Path, payload: Path, target: Path) -> list[str]:
    return [sys.executable, '-X', 'utf8', '-c', GUARDED_INSTALLER, str(installer),
            '--source-root', str(payload), '--target', str(target)]


class DistributionTests(unittest.TestCase):
    def test_delivered_payload_installs_and_repeats_without_registration_claims(self):
        skill = (ROOT / '.codebuddy/skills/ai-intro-course/SKILL.md').read_text(encoding='utf-8')
        version = re.search(r'^version:\s*(\d+\.\d+\.\d+)\s*$', skill, re.M)[1]
        archive_path = ROOT / 'dist' / f'ai-intro-course-setup-{version}.zip'
        self.assertTrue(archive_path.is_file(), 'Build the current distribution before running this test')
        with tempfile.TemporaryDirectory(prefix='course-distribution-') as tmp:
            stage = Path(tmp)
            with zipfile.ZipFile(archive_path) as bundle:
                for name in bundle.namelist():
                    self.assertTrue((stage / name).resolve().is_relative_to(stage.resolve()))
                bundle.extractall(stage)
            setup = stage / 'ai-intro-course-setup'
            plan = json.loads((setup / 'assets/install-plan.json').read_text(encoding='utf-8'))
            self.assertEqual(plan['project_type'], 'teacher')
            self.assertEqual(plan['project_config'], 'configs/teacher-project.md')
            self.assertEqual(plan['recommended_selection']['expert_ids'], ['ai-intro-course-team-lead'])
            self.assertEqual(plan['recommended_selection']['skill_ids'],
                             ['ai-intro-course', 'ai-frontier-weekly', *PRODUCTION_IDS])
            companions = {item['id']: item for item in plan['companion_skills']}
            self.assertEqual(set(companions), {'workbuddy-auto-signin', 'ai-frontier-weekly', *PRODUCTION_IDS})
            payload = setup / plan['payload_root']
            for companion in companions.values():
                self.assertIs(companion['install_skill_with_suite'], True)
                self.assertIs(companion['bind_to_course_experts'], False)
                self.assertIs(companion['enable_background_by_default'], False)
                self.assertEqual(hashlib.sha256((setup / companion['archive']).read_bytes()).hexdigest(),
                                 companion['sha256'])
                # The uploadable ZIP and unpacked installation payload must
                # contain the same complete Skill, not just the entry prompt.
                skill_id = companion['id']
                prefix = companion['source'] + '/'
                expected = {name[len(prefix):]: value for name, value in plan['file_hashes'].items()
                            if name.startswith(prefix)}
                package = setup / companion['archive']
                self.assertEqual(package.read_bytes(), (ROOT / 'dist' / package.name).read_bytes())
                with zipfile.ZipFile(package) as skill_bundle:
                    self.assertIsNone(skill_bundle.testzip())
                    contents = {name.removeprefix(skill_id + '/'): skill_bundle.read(name)
                                for name in skill_bundle.namelist()}
                    self.assertEqual(set(contents), set(expected), skill_id)
                    self.assertIn('SKILL.md', contents)
                    for name, data in contents.items():
                        self.assertEqual(hashlib.sha256(data).hexdigest(), expected[name], skill_id + '/' + name)
                    if skill_id in PRODUCTION_IDS:
                        self.assertIn('requirements.txt', contents, skill_id)
                        self.assertIs(companion['associate_with_teacher_project'], True)
                        self.assertIs(companion['enable_publication_by_default'], False)
                        self.assertTrue((payload / companion['requirements']).is_file())
                        scripts = {Path(name).stem for name in contents
                                   if name.startswith('scripts/') and name.endswith('.py')}
                        self.assertTrue({Path(name).stem for name in PRODUCTION_SCRIPTS[skill_id]} <= scripts,
                                        'Missing generator or checker in ' + skill_id)
                        for name, data in contents.items():
                            if not name.startswith('scripts/') or not name.endswith('.py'):
                                continue
                            tree = ast.parse(data.decode('utf-8-sig'), filename=name)
                            for node in ast.walk(tree):
                                imports = ([alias.name.split('.')[0] for alias in node.names]
                                           if isinstance(node, ast.Import) else
                                           [(node.module or '').split('.')[0]]
                                           if isinstance(node, ast.ImportFrom) else [])
                                for imported in set(imports) & LOCAL_HELPERS:
                                    self.assertIn(imported, scripts,
                                                  f'{skill_id}/{name} requires missing sibling {imported}')
            weekly = companions['ai-frontier-weekly']
            self.assertIs(weekly['enable_publication_by_default'], False)
            self.assertEqual(weekly['scheduler'], 'workbuddy_native')
            for key in ('schedule_template', 'task_prompt'):
                self.assertTrue((payload / weekly[key]).is_file())
            self.assertFalse((payload / 'configs/student-project.md').exists())
            for name, expected in plan['file_hashes'].items():
                self.assertEqual(hashlib.sha256((payload / name).read_bytes()).hexdigest(), expected)
            for key in ('runtime_skill', 'native_team'):
                archive = setup / plan['artifacts'][key + '_archive']
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                                 plan['artifacts'][key + '_sha256'])
            target = stage / 'project'
            target.mkdir()
            unrelated = target / 'teacher-notes.md'
            unrelated.write_text('Existing teacher notes, preserved.\n', encoding='utf-8')
            command = guarded_command(setup / plan['local_installer'], payload, target)
            first = subprocess.run(command, text=True, capture_output=True, encoding='utf-8')
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            receipt = target / '.codebuddy/ai-intro-course-installation.json'
            before_receipt = receipt.read_bytes()
            for name in plan['file_hashes']:
                if name.startswith('.codebuddy/'):
                    self.assertEqual((target / name).read_bytes(), (payload / name).read_bytes())
            second = subprocess.run(command, text=True, capture_output=True, encoding='utf-8')
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            result = json.loads(second.stdout)
            self.assertEqual(result['status'], 'filesystem_installed')
            self.assertIs(result['account_automation_modified'], False)
            self.assertIs(result['weekly_schedule_modified'], False)
            self.assertIs(result['publication_modified'], False)
            self.assertTrue((target / '.codebuddy/skills/workbuddy-auto-signin/scripts/manage_signin.py').is_file())
            self.assertTrue((target / '.codebuddy/skills/ai-frontier-weekly/assets/weekly-report-template.html').is_file())
            self.assertTrue((target / '.codebuddy/skills/ai-frontier-weekly/requirements.txt').is_file())
            self.assertEqual(unrelated.read_text(encoding='utf-8'), 'Existing teacher notes, preserved.\n')
            self.assertEqual({path.name for path in target.iterdir()}, {'.codebuddy', 'teacher-notes.md'})
            self.assertEqual(result['changed_files'], [])
            self.assertEqual(receipt.read_bytes(), before_receipt)
            for field in ('registry_verified', 'project_binding_verified', 'runtime_verified'):
                self.assertIs(result[field], False)
            # Protect actual delivered text, CSV, and Office assets using the
            # same ownership check; a conflict must happen before any writes.
            edits = {
                '.codebuddy/skills/ai-frontier-weekly/assets/weekly-report-template.html':
                    b'<!doctype html><title>Teacher custom layout</title>',
                '.codebuddy/skills/ai-course-slides/assets/default-template.pptx': b'teacher custom Office template',
                '.codebuddy/skills/ai-course-handout/assets/knowledge-points-example.csv': b'kp_id,name\nCUSTOM,teacher mapping\n',
                '.codebuddy/skills/ai-course-assessment/scripts/build_paper.py': b'# teacher custom exporter\n',
                '.codebuddy/skills/ai-course-analytics/SKILL.md': b'# teacher analytics instructions\n',
                '.codebuddy/skills/ai-course-visual/scripts/build_figures.py': b'# teacher diagram changes\n',
            }
            for name, data in edits.items():
                self.assertTrue((target / name).is_file(), name)
                (target / name).write_bytes(data)
            before_files = {path.relative_to(target).as_posix(): path.read_bytes()
                            for path in target.rglob('*') if path.is_file()}
            rejected = subprocess.run(command, text=True, capture_output=True, encoding='utf-8')
            self.assertNotEqual(rejected.returncode, 0)
            response = json.loads(rejected.stdout)
            self.assertTrue(set(edits) <= set(response['conflicts']))
            self.assertEqual({path.relative_to(target).as_posix(): path.read_bytes()
                              for path in target.rglob('*') if path.is_file()}, before_files)
            self.assertEqual(receipt.read_bytes(), before_receipt)

    def test_production_example_assets_are_usable_and_consistent_in_independent_packages(self):
        skill = (ROOT / '.codebuddy/skills/ai-intro-course/SKILL.md').read_text(encoding='utf-8')
        version = re.search(r'^version:\s*(\d+\.\d+\.\d+)\s*$', skill, re.M)[1]
        tables = []
        for skill_id in PRODUCTION_IDS:
            package = ROOT / 'dist' / f'{skill_id}-{version}-workbuddy.zip'
            self.assertTrue(package.is_file(), 'Build the current distribution before running this test')
            with zipfile.ZipFile(package) as bundle:
                if skill_id == 'ai-course-slides':
                    blob = bundle.read(skill_id + '/assets/default-template.pptx')
                    self.assertEqual(blob, (ROOT / 'addons' / skill_id / 'assets/default-template.pptx').read_bytes())
                    with zipfile.ZipFile(io.BytesIO(blob)) as presentation:
                        self.assertIsNone(presentation.testzip())
                        self.assertIn('[Content_Types].xml', presentation.namelist())
                        self.assertIn('ppt/presentation.xml', presentation.namelist())
                if skill_id in {'ai-course-handout', 'ai-course-assessment', 'ai-course-analytics'}:
                    blob = bundle.read(skill_id + '/assets/knowledge-points-example.csv')
                    self.assertEqual(blob, (ROOT / 'addons' / skill_id / 'assets/knowledge-points-example.csv').read_bytes())
                    rows = list(csv.DictReader(io.StringIO(blob.decode('utf-8-sig'))))
                    self.assertTrue(rows, 'Knowledge point example must not be empty')
                    self.assertTrue({'kp_id', 'name', 'section', 'order'} <= rows[0].keys())
                    self.assertEqual(len({row['kp_id'] for row in rows}), len(rows))
                    tables.append(rows)
                if skill_id == 'ai-course-analytics':
                    demo = bundle.read(skill_id + '/assets/demo_answers.csv')
                    self.assertEqual(demo, (ROOT / 'addons' / skill_id / 'assets/demo_answers.csv').read_bytes())
                    self.assertTrue(list(csv.DictReader(io.StringIO(demo.decode('utf-8-sig')))))
        self.assertEqual(len(tables), 3)
        self.assertEqual(tables[0], tables[1])
        self.assertEqual(tables[1], tables[2])


if __name__ == '__main__':
    unittest.main()
