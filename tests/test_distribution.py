"""Exercise the real delivered setup ZIP in an isolated local project."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


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
            self.assertEqual(plan['recommended_selection']['skill_ids'], ['ai-intro-course', 'ai-frontier-weekly'])
            companions = {item['id']: item for item in plan['companion_skills']}
            self.assertEqual(set(companions), {'workbuddy-auto-signin', 'ai-frontier-weekly'})
            for companion in companions.values():
                self.assertIs(companion['install_skill_with_suite'], True)
                self.assertIs(companion['bind_to_course_experts'], False)
                self.assertIs(companion['enable_background_by_default'], False)
                self.assertEqual(hashlib.sha256((setup / companion['archive']).read_bytes()).hexdigest(),
                                 companion['sha256'])
            weekly = companions['ai-frontier-weekly']
            self.assertIs(weekly['enable_publication_by_default'], False)
            self.assertEqual(weekly['scheduler'], 'workbuddy_native')
            payload = setup / plan['payload_root']
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
            command = [sys.executable, '-X', 'utf8', str(setup / plan['local_installer']),
                       '--source-root', str(payload), '--target', str(target)]
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
            self.assertEqual(result['changed_files'], [])
            self.assertEqual(receipt.read_bytes(), before_receipt)
            for field in ('registry_verified', 'project_binding_verified', 'runtime_verified'):
                self.assertIs(result[field], False)
            # An actual delivered HTML file is protected by the same ownership
            # check as expert prompts; an update must preserve teacher edits.
            edited = target / '.codebuddy/skills/ai-frontier-weekly/assets/weekly-report-template.html'
            custom = b'<!doctype html><title>Teacher custom layout</title>'
            edited.write_bytes(custom)
            rejected = subprocess.run(command, text=True, capture_output=True, encoding='utf-8')
            self.assertNotEqual(rejected.returncode, 0)
            self.assertEqual(edited.read_bytes(), custom)
            self.assertEqual(receipt.read_bytes(), before_receipt)


if __name__ == '__main__':
    unittest.main()
