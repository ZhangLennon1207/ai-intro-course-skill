"""Filesystem-level installer checks; these never access a WorkBuddy service."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "install_project.py"
SPEC = importlib.util.spec_from_file_location("course_project_installer", SCRIPT)
installer = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(installer)


class ProjectInstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="course-project-installer-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.target = self.root / "project"
        self.target.mkdir()
        for name in installer.AGENT_IDS:
            self.write(self.source / ".codebuddy/agents" / f"{name}.md", f"# {name}\nsource-v1\n")
        self.skill = self.source / ".codebuddy/skills/ai-intro-course"
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.2.0\n---\n# Course\n")
        self.write(self.skill / "references/concepts.md", "Public fictional concepts.\n")
        self.write(self.source / ".codebuddy/agents/unrelated.md", "not part of this installer\n")

    @staticmethod
    def write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def install(self, **kwargs):
        return installer.install_project(self.source, self.target, **kwargs)

    def test_repeat_install_is_a_noop_and_preserves_unrelated_resources(self):
        unrelated = self.target / ".codebuddy/rules/team-policy.md"
        self.write(unrelated, "custom rule\n")
        first = self.install()
        receipt = self.target / str(installer.RECEIPT_PATH)
        first_receipt = receipt.read_bytes()
        installed = self.target / ".codebuddy/agents" / f"{installer.AGENT_IDS[0]}.md"
        modified_at = installed.stat().st_mtime_ns
        second = self.install()
        self.assertTrue(first["changed_files"])
        self.assertEqual(second["changed_files"], [])
        self.assertEqual(receipt.read_bytes(), first_receipt)
        self.assertEqual(installed.stat().st_mtime_ns, modified_at)
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "custom rule\n")
        self.assertFalse((self.target / ".codebuddy/agents/unrelated.md").exists())
        self.assertFalse(first["registry_verified"])
        self.assertFalse(first["project_binding_verified"])
        self.assertFalse(first["runtime_verified"])
        self.assertEqual(first["status"], "filesystem_installed")

    def test_companion_skill_copies_without_running_or_copying_local_data(self):
        addon = self.source / "addons/workbuddy-auto-signin"
        self.write(addon / "SKILL.md", "---\nname: workbuddy-auto-signin\n---\n# Sign-in\n")
        self.write(addon / "scripts/manage_signin.py", "raise RuntimeError('must never execute during course install')\n")
        self.write(addon / "assets/upstream/LICENSE.txt", "Fictional license for copy test\n")
        self.write(addon / ".env", "fictional secret\n")
        self.write(addon / "session.local.json", "fictional session\n")
        self.write(addon / "__pycache__/cache.pyc", "fictional bytecode\n")
        self.write(addon / "signin.log", "fictional account result\n")
        first = self.install()
        installed = self.target / str(installer.SIGNIN_SKILL_ROOT)
        self.assertTrue((installed / "scripts/manage_signin.py").is_file())
        self.assertEqual({p.relative_to(installed).as_posix() for p in installed.rglob('*') if p.is_file()},
                         {"SKILL.md", "scripts/manage_signin.py", "assets/upstream/LICENSE.txt"})
        self.assertIs(first["account_automation_modified"], False)
        self.assertEqual(self.install()["changed_files"], [])
        (installed / "scripts/manage_signin.py").write_text("my changed script\n", encoding="utf-8")
        with self.assertRaises(installer.InstallationConflict):
            self.install()

    def test_companion_payload_layout_is_supported_and_ambiguous_sources_rejected(self):
        addon = self.source / str(installer.SIGNIN_SKILL_ROOT)
        self.write(addon / "SKILL.md", "---\nname: workbuddy-auto-signin\n---\n# Companion\n")
        self.install()
        self.assertTrue((self.target / str(installer.SIGNIN_SKILL_ROOT) / "SKILL.md").is_file())
        self.write(self.source / "addons/workbuddy-auto-signin/SKILL.md", "another source\n")
        with self.assertRaises(installer.InstallationError):
            self.install()

    def test_owned_update_backs_up_prior_content_and_installs_new_resources(self):
        self.install()
        relative = f".codebuddy/agents/{installer.AGENT_IDS[1]}.md"
        dest = self.target / relative
        old = dest.read_bytes()
        self.write(self.source / relative, "updated owned expert\n")
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.3.0\n---\n# Course\n")
        self.write(self.skill / "references/new.md", "new content\n")
        outcome = self.install()
        self.assertEqual(outcome["version"], "1.3.0")
        self.assertEqual(dest.read_text(encoding="utf-8"), "updated owned expert\n")
        saved = [self.target / value for value in outcome["backups"] if value.endswith(relative)]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), old)
        receipt = json.loads((self.target / str(installer.RECEIPT_PATH)).read_text(encoding="utf-8"))
        self.assertEqual(receipt["files"][relative], installer.digest(dest.read_bytes()))
        self.assertTrue((self.target / ".codebuddy/skills/ai-intro-course/references/new.md").is_file())

    def test_first_install_collision_prevents_every_write(self):
        collision = self.target / ".codebuddy/agents" / f"{installer.AGENT_IDS[2]}.md"
        self.write(collision, "my own expert\n")
        before = sorted(str(p.relative_to(self.target)) for p in self.target.rglob("*") if p.is_file())
        with self.assertRaises(installer.InstallationConflict):
            self.install()
        after = sorted(str(p.relative_to(self.target)) for p in self.target.rglob("*") if p.is_file())
        self.assertEqual(after, before)
        self.assertEqual(collision.read_text(encoding="utf-8"), "my own expert\n")
        self.assertFalse((self.target / str(installer.RECEIPT_PATH)).exists())

    def test_user_edit_blocks_an_update_before_unrelated_owned_files_are_changed(self):
        self.install()
        changed_by_user = self.target / ".codebuddy/agents" / f"{installer.AGENT_IDS[0]}.md"
        self.write(changed_by_user, "teacher customized this prompt\n")
        other_rel = f".codebuddy/agents/{installer.AGENT_IDS[1]}.md"
        other_before = (self.target / other_rel).read_bytes()
        self.write(self.source / other_rel, "new source version\n")
        receipt = self.target / str(installer.RECEIPT_PATH)
        receipt_before = receipt.read_bytes()
        with self.assertRaises(installer.InstallationConflict):
            self.install()
        self.assertEqual(changed_by_user.read_text(encoding="utf-8"), "teacher customized this prompt\n")
        self.assertEqual((self.target / other_rel).read_bytes(), other_before)
        self.assertEqual(receipt.read_bytes(), receipt_before)

    def test_legacy_non_teacher_directory_is_preserved_without_writes(self):
        self.install(materials_entry="https://example.invalid/legacy-materials")
        rule_path = self.target / str(installer.RULE_PATH)
        self.write(rule_path, "course_mode: student\nlegacy learning project\n")
        receipt_path = self.target / str(installer.RECEIPT_PATH)
        receipt = json.loads(receipt_path.read_bytes())
        receipt["mode"] = "student"
        receipt["version"] = "1.1.0"
        receipt["files"][str(installer.RULE_PATH)] = installer.digest(rule_path.read_bytes())
        self.write(receipt_path, json.dumps(receipt))
        before = {p.relative_to(self.target).as_posix(): p.read_bytes()
                  for p in self.target.rglob("*") if p.is_file()}
        for entry in (None, "https://example.invalid/teacher-materials"):
            with self.assertRaises(installer.InstallationError):
                self.install(materials_entry=entry)
            after = {p.relative_to(self.target).as_posix(): p.read_bytes()
                     for p in self.target.rglob("*") if p.is_file()}
            self.assertEqual(after, before)

    def test_legacy_teacher_receipt_upgrades_without_reselecting_a_mode(self):
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.1.0\n---\n# Legacy course\n")
        entry = "https://example.invalid/teacher-materials"
        self.install(materials_entry=entry)
        rule_path = self.target / str(installer.RULE_PATH)
        self.write(rule_path, "course_mode: teacher\nlegacy teacher rule\n")
        receipt_path = self.target / str(installer.RECEIPT_PATH)
        receipt = json.loads(receipt_path.read_bytes())
        receipt["files"][str(installer.RULE_PATH)] = installer.digest(rule_path.read_bytes())
        self.write(receipt_path, json.dumps(receipt))
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.2.0\n---\n# Teacher course\n")
        outcome = self.install()
        self.assertEqual(outcome["version"], "1.2.0")
        upgraded = json.loads(receipt_path.read_bytes())
        self.assertEqual(upgraded["mode"], "teacher")
        self.assertEqual(upgraded["materials_entry"], entry)
        self.assertIn(str(installer.RULE_PATH), outcome["changed_files"])
        self.assertIn("preferred_course_agent: ai-intro-course-team-lead", rule_path.read_text(encoding="utf-8"))

    def test_same_mode_update_preserves_an_omitted_materials_entry(self):
        entry = "https://example.invalid/authorized-course"
        self.install(materials_entry=entry)
        rule = self.target / str(installer.RULE_PATH)
        receipt = self.target / str(installer.RECEIPT_PATH)
        first_rule = rule.read_bytes()
        first_receipt = receipt.read_bytes()
        repeated = self.install()
        self.assertEqual(repeated["changed_files"], [])
        self.assertEqual(rule.read_bytes(), first_rule)
        self.assertEqual(receipt.read_bytes(), first_receipt)
        self.assertEqual(json.loads(first_receipt)["materials_entry"], entry)
        relative = f".codebuddy/agents/{installer.AGENT_IDS[1]}.md"
        self.write(self.source / relative, "updated expert with retained materials\n")
        updated = self.install()
        self.assertEqual(updated["changed_files"], [relative])
        self.assertEqual(rule.read_bytes(), first_rule)
        self.assertEqual(json.loads(receipt.read_bytes())["materials_entry"], entry)

    def test_non_teacher_api_request_is_rejected_without_writes(self):
        with self.assertRaises(installer.InstallationError):
            self.install(mode="student")
        self.assertEqual(list(self.target.iterdir()), [])

    def test_second_write_failure_rolls_back_and_does_not_block_a_later_version(self):
        self.install()
        receipt_path = self.target / str(installer.RECEIPT_PATH)
        old_receipt = receipt_path.read_bytes()
        original = {rel: (self.target / rel).read_bytes()
                    for rel in json.loads(old_receipt)["files"]}
        for name in installer.AGENT_IDS:
            self.write(self.source / f".codebuddy/agents/{name}.md", f"{name} v2\n")
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.3.0\n---\nv2\n")
        real_write = installer.atomic_write
        writes = 0

        def fail_second(project, relative, content):
            nonlocal writes
            if str(relative).startswith(".codebuddy/agents/"):
                writes += 1
                if writes == 2:
                    raise OSError("simulated second update write failure")
            return real_write(project, relative, content)

        with mock.patch.object(installer, "atomic_write", side_effect=fail_second):
            with self.assertRaises(installer.InstallationWriteError) as caught:
                self.install()
        self.assertEqual(caught.exception.rollback_status, "rolled_back")
        self.assertEqual(caught.exception.rollback_failures, [])
        self.assertEqual(receipt_path.read_bytes(), old_receipt)
        for rel, content in original.items():
            self.assertEqual((self.target / rel).read_bytes(), content)
        for name in installer.AGENT_IDS:
            self.write(self.source / f".codebuddy/agents/{name}.md", f"{name} v3\n")
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.4.0\n---\nv3\n")
        result = self.install()
        self.assertEqual(result["version"], "1.4.0")
        receipt = json.loads((self.target / str(installer.RECEIPT_PATH)).read_text(encoding="utf-8"))
        self.assertEqual(receipt["version"], "1.4.0")

    def test_receipt_failure_after_replace_restores_receipt_and_removes_only_new_files(self):
        self.install()
        receipt_path = self.target / str(installer.RECEIPT_PATH)
        old_receipt = receipt_path.read_bytes()
        original_skill = (self.target / ".codebuddy/skills/ai-intro-course/SKILL.md").read_bytes()
        self.write(self.skill / "SKILL.md", "---\nname: ai-intro-course\nversion: 1.3.0\n---\nv2\n")
        new_relative = ".codebuddy/skills/ai-intro-course/references/new.md"
        self.write(self.source / new_relative, "newly created in failed update\n")
        unrelated = self.target / "user.txt"
        self.write(unrelated, "keep user file\n")
        real_write = installer.atomic_write
        failed = False

        def fail_after_receipt_replace(project, relative, content):
            nonlocal failed
            real_write(project, relative, content)
            if str(relative) == str(installer.RECEIPT_PATH) and not failed:
                failed = True
                raise OSError("simulated failure after receipt replacement")

        with mock.patch.object(installer, "atomic_write", side_effect=fail_after_receipt_replace):
            with self.assertRaises(installer.InstallationWriteError) as caught:
                self.install()
        self.assertEqual(caught.exception.rollback_status, "rolled_back")
        self.assertEqual(receipt_path.read_bytes(), old_receipt)
        self.assertEqual((self.target / ".codebuddy/skills/ai-intro-course/SKILL.md").read_bytes(), original_skill)
        self.assertFalse((self.target / new_relative).exists())
        self.assertEqual(unrelated.read_text(encoding="utf-8"), "keep user file\n")

    def test_backup_failure_occurs_before_live_files_are_changed(self):
        self.install()
        receipt_path = self.target / str(installer.RECEIPT_PATH)
        old_receipt = receipt_path.read_bytes()
        original = {rel: (self.target / rel).read_bytes()
                    for rel in json.loads(old_receipt)["files"]}
        for name in installer.AGENT_IDS:
            self.write(self.source / f".codebuddy/agents/{name}.md", f"{name} updated\n")
        real_write = installer.atomic_write
        backups = 0

        def fail_second_backup(project, relative, content):
            nonlocal backups
            if str(relative).startswith(str(installer.BACKUP_ROOT)):
                backups += 1
                if backups == 2:
                    raise OSError("simulated backup failure")
            return real_write(project, relative, content)

        with mock.patch.object(installer, "atomic_write", side_effect=fail_second_backup):
            with self.assertRaises(OSError):
                self.install()
        self.assertEqual(receipt_path.read_bytes(), old_receipt)
        for rel, content in original.items():
            self.assertEqual((self.target / rel).read_bytes(), content)

    def test_failed_recovery_preserves_concurrent_changes_and_reports_the_path(self):
        self.install()
        relative = f".codebuddy/agents/{installer.AGENT_IDS[1]}.md"
        # Sorted update order is assessment, design, domain, team-lead, tutor.
        first_relative = ".codebuddy/agents/ai-intro-course-assessment.md"
        self.write(self.source / relative, "new design\n")
        self.write(self.source / first_relative, "new assessment\n")
        real_write = installer.atomic_write

        def concurrent_edit_then_fail(project, rel, content):
            if str(rel) == relative:
                self.write(self.target / first_relative, "concurrent user edit\n")
                raise OSError("simulated update failure")
            return real_write(project, rel, content)

        with mock.patch.object(installer, "atomic_write", side_effect=concurrent_edit_then_fail):
            with self.assertRaises(installer.InstallationWriteError) as caught:
                self.install()
        self.assertEqual(caught.exception.status, "recovery_required")
        self.assertEqual(caught.exception.rollback_status, "incomplete")
        self.assertEqual([item["path"] for item in caught.exception.rollback_failures], [first_relative])
        self.assertEqual((self.target / first_relative).read_text(encoding="utf-8"), "concurrent user edit\n")
        self.assertTrue(caught.exception.backups)

    def test_dry_run_does_not_create_any_project_files(self):
        result = self.install(dry_run=True, materials_entry="https://example.invalid/course")
        self.assertEqual(result["status"], "dry_run")
        self.assertTrue(result["changed_files"])
        self.assertEqual(list(self.target.iterdir()), [])

    def test_cli_installs_teacher_project_without_a_mode_option(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--source-root", str(self.source),
                                 "--target", str(self.target)], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        outcome = json.loads(result.stdout)
        self.assertEqual(outcome["mode"], "teacher")
        receipt = json.loads((self.target / str(installer.RECEIPT_PATH)).read_bytes())
        self.assertEqual(receipt["mode"], "teacher")
        legacy = subprocess.run([sys.executable, str(SCRIPT), "--source-root", str(self.source),
                                 "--target", str(self.target), "--mode", "teacher"],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
        self.assertEqual(json.loads(legacy.stdout)["changed_files"], [])

    def test_cli_rejects_a_legacy_student_request_before_writing(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--source-root", str(self.source),
                                 "--target", str(self.target), "--mode", "student"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(list(self.target.iterdir()), [])

    def test_missing_source_or_target_is_rejected_without_creating_directories(self):
        absent = self.root / "absent"
        with self.assertRaises(installer.InstallationError):
            installer.install_project(self.source, absent, "teacher")
        with self.assertRaises(installer.InstallationError):
            installer.install_project(absent, self.target, "teacher")
        self.assertFalse(absent.exists())
        self.assertEqual(list(self.target.iterdir()), [])

    def test_invalid_existing_receipt_is_preserved(self):
        receipt = self.target / str(installer.RECEIPT_PATH)
        self.write(receipt, '{"schema_version":1,"suite_id":"another-suite"}')
        before = receipt.read_bytes()
        with self.assertRaises(installer.InstallationError):
            self.install()
        self.assertEqual(receipt.read_bytes(), before)
        self.assertFalse((self.target / ".codebuddy/agents").exists())

    def test_destination_link_escape_is_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.target / ".codebuddy").mkdir()
        try:
            (self.target / ".codebuddy/agents").symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"This account cannot create directory links: {error}")
        with self.assertRaises(installer.InstallationError):
            self.install()
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.target / str(installer.RECEIPT_PATH)).exists())

    def test_source_link_escape_is_rejected(self):
        outside = self.root / "private.txt"
        outside.write_text("outside content", encoding="utf-8")
        try:
            (self.skill / "references/private.md").symlink_to(outside)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"This account cannot create file links: {error}")
        with self.assertRaises(installer.InstallationError):
            self.install()
        self.assertEqual(list(self.target.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
