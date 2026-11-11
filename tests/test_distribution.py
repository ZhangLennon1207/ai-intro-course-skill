"""Exercise the real delivered setup ZIP in an isolated local project."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


class DistributionTests(unittest.TestCase):
    def test_delivered_payload_installs_and_repeats_without_registration_claims(self):
        archives = list((ROOT / 'dist').glob('ai-intro-course-setup-*.zip'))
        self.assertEqual(len(archives), 1, 'Build the current distribution before running this test')
        with tempfile.TemporaryDirectory(prefix='course-distribution-') as tmp:
            stage = Path(tmp)
            with zipfile.ZipFile(archives[0]) as bundle:
                for name in bundle.namelist():
                    self.assertTrue((stage / name).resolve().is_relative_to(stage.resolve()))
                bundle.extractall(stage)
            setup = stage / 'ai-intro-course-setup'
            plan = json.loads((setup / 'assets/install-plan.json').read_text(encoding='utf-8'))
            payload = setup / plan['payload_root']
            for name, expected in plan['file_hashes'].items():
                self.assertEqual(hashlib.sha256((payload / name).read_bytes()).hexdigest(), expected)
            for key in ('runtime_skill', 'native_team'):
                archive = setup / plan['artifacts'][key + '_archive']
                self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(),
                                 plan['artifacts'][key + '_sha256'])
            target = stage / 'project'
            target.mkdir()
            command = [sys.executable, '-X', 'utf8', str(setup / plan['local_installer']),
                       '--source-root', str(payload), '--target', str(target), '--mode', 'teacher']
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
            self.assertEqual(result['changed_files'], [])
            self.assertEqual(receipt.read_bytes(), before_receipt)
            for field in ('registry_verified', 'project_binding_verified', 'runtime_verified'):
                self.assertIs(result[field], False)


if __name__ == '__main__':
    unittest.main()
