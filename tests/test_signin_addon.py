"""Optional add-on checks using fake tasks and fixture files, never live accounts."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "addons/workbuddy-auto-signin/scripts/manage_signin.py"
SPEC = importlib.util.spec_from_file_location("course_signin_manager", SCRIPT)
manager = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(manager)


class FakeScheduler:
    def __init__(self):
        self.tasks = {}
        self.created = []
        self.removed = []
        self.fail_create = None
        self.fail_after_create = None

    def identity(self):
        return "S-1-5-21-111-222-333-1001"

    def get(self, name):
        return copy.deepcopy(self.tasks.get(name))

    def exists(self, name):
        return name in self.tasks

    def create(self, spec):
        if spec["name"] == self.fail_create:
            raise manager.AddonError("SCHEDULER_ERROR", "simulated registration rejection")
        if spec["name"] in self.tasks:
            raise RuntimeError("refusing overwrite")
        self.tasks[spec["name"]] = copy.deepcopy(spec)
        self.created.append(spec["name"])
        if spec["name"] == self.fail_after_create:
            raise manager.AddonError("SCHEDULER_ERROR", "simulated response loss after registration")

    def remove(self, spec):
        if self.tasks.get(spec["name"]) != spec:
            raise RuntimeError("refusing unowned removal")
        self.removed.append(spec["name"])
        del self.tasks[spec["name"]]

    def info(self, name):
        if name not in self.tasks:
            raise manager.AddonError("SCHEDULER_ERROR", "missing task")
        return {"next_run_time": "2026-11-13T00:05:00", "last_run_time": "2026-11-12T00:05:00", "last_task_result": 0}


class SigninAddonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="signin-addon-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.local = self.base / "local-app-data"
        self.source = self.base / "addon"
        self.source.mkdir()
        self.assets = {"signin.py": b"# inert fixture; never executed\n", "install-windows.ps1": b"# inert installer fixture\n", "LICENSE.txt": b"MIT fixture\n"}
        self.hashes = {name: manager.digest(blob) for name, blob in self.assets.items()}
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(manager, "HASHES", self.hashes).start()
        for name, blob in self.assets.items():
            path = self.source / "assets/upstream" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
        self.lock = {"schema_version": 1, "repository": manager.REPOSITORY, "commit": manager.COMMIT, "files": self.hashes}
        (self.source / "upstream-lock.json").write_bytes(manager.canonical(self.lock))
        self.pythonw = self.base / "Python" / "pythonw.exe"
        self.pythonw.parent.mkdir()
        self.pythonw.write_bytes(b"not an executable; do not execute")
        self.scheduler = FakeScheduler()
        self.runtime = manager.runtime_dir(self.local)
        self.transport = mock.patch.object(manager.subprocess, "run", side_effect=AssertionError("Unexpected real process or network transport"))
        self.transport.start()

    def install(self, **kwargs):
        return manager.install_addon(mode=manager.MODE, addon_root=self.source, local_appdata=self.local,
                                     scheduler=self.scheduler, pythonw=self.pythonw, **kwargs)

    def status(self):
        return manager.status_addon(local_appdata=self.local, scheduler=self.scheduler)

    def uninstall(self):
        return manager.uninstall_addon(local_appdata=self.local, scheduler=self.scheduler)

    def assert_code(self, code, function):
        with self.assertRaises(manager.AddonError) as caught:
            function()
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def test_plan_is_cross_platform_default_and_does_not_open_source_or_credentials(self):
        with mock.patch.object(manager, "WindowsScheduler", side_effect=AssertionError("scheduler in plan")), mock.patch.object(manager, "source_assets", side_effect=AssertionError("asset access in plan")), mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(manager.main([]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "plan")
        self.assertFalse(result["manager_executed_account_actions"])
        self.assertEqual(len(result["tasks"][1]["at"]), 6)
        self.assertIn("spend energy", " ".join(result["effects"]))

    def test_install_requires_explicit_mode_before_any_windows_or_file_access(self):
        with mock.patch.object(manager, "WindowsScheduler", side_effect=AssertionError("unexpected scheduler")):
            self.assert_code("MODE_REQUIRED", lambda: manager.install_addon())
        self.assertFalse(self.runtime.exists())

    def test_first_install_and_repeat_verify_real_definitions_and_preserve_bytes(self):
        first = self.install()
        saved = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.runtime.iterdir()}
        self.scheduler.created.clear()
        second = self.install()
        self.assertEqual(first["status"], "tasks_installed")
        self.assertEqual(len(first["created_tasks"]), 2)
        self.assertFalse(second["changed"])
        self.assertEqual(second["created_tasks"], [])
        self.assertEqual(self.scheduler.created, [])
        self.assertFalse(second["daily_signin_verified"])
        self.assertEqual(len(second["task_info"]), 2)
        self.assertEqual(second["log_path"], str(self.runtime / "signin.log"))
        self.assertEqual(saved, {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.runtime.iterdir()})
        for task in self.scheduler.tasks.values():
            self.assertTrue(task["actions"][0]["execute"].endswith("pythonw.exe"))
            self.assertIn(str(self.runtime / "signin.py"), task["actions"][0]["arguments"])
            self.assertEqual(task["principal"]["run_level"], "Limited")
            self.assertEqual(task["principal"]["logon_type"], "Interactive")

    def test_tampered_asset_or_lock_blocks_registration(self):
        (self.source / "assets/upstream/signin.py").write_bytes(b"tampered")
        self.assert_code("SOURCE_INTEGRITY", self.install)
        self.assertEqual(self.scheduler.created, [])
        (self.source / "assets/upstream/signin.py").write_bytes(self.assets["signin.py"])
        self.lock["commit"] = "unreviewed"
        (self.source / "upstream-lock.json").write_bytes(manager.canonical(self.lock))
        self.assert_code("SOURCE_INTEGRITY", self.install)
        self.assertFalse(self.runtime.exists())

    def test_missing_pythonw_has_specific_error_without_registered_tasks(self):
        self.pythonw.unlink()
        self.assert_code("PYTHONW_MISSING", self.install)
        self.assertEqual(self.scheduler.created, [])

    def test_unowned_task_collision_is_preserved_before_runtime_copy(self):
        name = manager.task_names(self.scheduler.identity())[1]
        self.scheduler.tasks[name] = {"name": name, "custom": "keep me"}
        before = copy.deepcopy(self.scheduler.tasks)
        self.assert_code("TASK_CONFLICT", self.install)
        self.assertEqual(self.scheduler.tasks, before)
        self.assertFalse((self.runtime / manager.RECEIPT_NAME).exists())
        self.assertFalse((self.runtime / "signin.py").exists())

    def test_existing_modified_runtime_and_receipt_are_preserved(self):
        self.install()
        path = self.runtime / "signin.py"
        path.write_bytes(b"teacher modification")
        receipt = self.runtime / manager.RECEIPT_NAME
        before_receipt = receipt.read_bytes()
        self.assert_code("FILE_CONFLICT", self.install)
        self.assertEqual(path.read_bytes(), b"teacher modification")
        self.assertEqual(receipt.read_bytes(), before_receipt)
        self.assertEqual(self.status()["status"], "incomplete")
        receipt.write_bytes(before_receipt + b" ")
        self.assert_code("RECEIPT_CONFLICT", self.install)
        self.assert_code("RECEIPT_CONFLICT", self.uninstall)
        self.assertEqual(len(self.scheduler.tasks), 2)
        self.assertEqual(receipt.read_bytes(), before_receipt + b" ")

    def test_modified_task_blocks_repeat_status_and_uninstall_without_touching_it(self):
        self.install()
        name = manager.task_names(self.scheduler.identity())[1]
        self.scheduler.tasks[name]["actions"][0]["arguments"] = '"custom.py"'
        before = copy.deepcopy(self.scheduler.tasks)
        for operation in (self.install, self.status, self.uninstall):
            self.assert_code("TASK_CONFLICT", operation)
        self.assertEqual(self.scheduler.tasks, before)
        self.assertEqual(self.scheduler.removed, [])

    def test_modified_full_boundary_and_run_conditions_are_detected_and_preserved(self):
        self.install()
        name = manager.task_names(self.scheduler.identity())[0]
        original = copy.deepcopy(self.scheduler.tasks[name])
        changes = [
            ("boundary", "2099-01-01T00:05:00"), ("boundary", "2099-01-01T00:05:59"),
            ("boundary", "2099-01-01T00:05:00+08:00"),
            ("run_only_if_idle", True), ("run_only_if_network_available", True),
        ]
        for field, value in changes:
            with self.subTest(field=field, value=value):
                changed = copy.deepcopy(original)
                if field == "boundary":
                    changed["triggers"][0]["start_boundary"] = value
                else:
                    changed["settings"][field] = value
                self.scheduler.tasks[name] = changed
                self.assert_code("TASK_CONFLICT", self.status)
                self.assert_code("TASK_CONFLICT", self.uninstall)
                self.assertEqual(self.scheduler.tasks[name], changed)
        self.assertEqual(self.scheduler.removed, [])

    def test_partial_install_rolls_back_only_new_tasks_and_is_recoverable(self):
        self.install()
        names = manager.task_names(self.scheduler.identity())
        del self.scheduler.tasks[names[1]]
        old_task = copy.deepcopy(self.scheduler.tasks[names[0]])
        self.scheduler.fail_after_create = names[1]
        error = self.assert_code("INSTALL_FAILED", self.install)
        self.assertEqual(error.details["rollback_failures"], [])
        self.assertEqual(self.scheduler.tasks, {names[0]: old_task})
        self.assertEqual(self.scheduler.removed, [names[1]])
        self.assertTrue((self.runtime / manager.RECEIPT_NAME).is_file())
        self.scheduler.fail_after_create = None
        self.assertEqual(self.install()["created_tasks"], [names[1]])

    def test_second_creation_failure_removes_first_new_task_but_keeps_external_task(self):
        names = manager.task_names(self.scheduler.identity())
        self.scheduler.tasks["ExternalTask"] = {"external": True}
        self.scheduler.fail_create = names[1]
        self.assert_code("INSTALL_FAILED", self.install)
        self.assertEqual(self.scheduler.tasks, {"ExternalTask": {"external": True}})
        self.assertEqual(self.scheduler.removed, [names[0]])

    def test_legacy_tasks_block_install_and_are_reported_by_status_but_never_removed(self):
        self.scheduler.tasks["WorkBuddyAutoSignin"] = {"external": True}
        before = copy.deepcopy(self.scheduler.tasks)
        for operation in (self.install, self.status):
            error = self.assert_code("LEGACY_TASK_CONFLICT", operation)
            self.assertEqual(error.details["legacy_tasks"], ["WorkBuddyAutoSignin"])
        self.assertEqual(self.scheduler.tasks, before)
        self.assertEqual(self.scheduler.created, [])
        self.assertEqual(self.scheduler.removed, [])
        self.assertFalse(self.runtime.exists())

    def test_legacy_task_added_after_install_does_not_prevent_removing_owned_tasks(self):
        self.install()
        self.scheduler.tasks["WorkBuddyGrowthPoll"] = {"external": True}
        self.assertEqual(self.uninstall()["status"], "tasks_removed")
        self.assertEqual(self.scheduler.tasks, {"WorkBuddyGrowthPoll": {"external": True}})

    def test_uninstall_keeps_files_logs_and_receipt_and_does_not_need_pythonw(self):
        self.install()
        (self.runtime / "signin.log").write_text("personal log", encoding="utf-8")
        (self.runtime / "signin.py").write_text("teacher changes", encoding="utf-8")
        self.pythonw.unlink()
        degraded = self.status()
        self.assertEqual(degraded["status"], "incomplete")
        self.assertEqual(degraded["dependency_problems"], [str(self.pythonw)])
        before = {path.name: path.read_bytes() for path in self.runtime.iterdir()}
        result = self.uninstall()
        self.assertEqual(result["status"], "tasks_removed")
        self.assertEqual(self.scheduler.tasks, {})
        self.assertEqual(before, {path.name: path.read_bytes() for path in self.runtime.iterdir()})
        self.assertEqual(self.uninstall()["status"], "tasks_absent")

    def test_receipt_alone_is_not_reported_as_installed_and_missing_owned_task_is_repaired(self):
        self.install()
        self.scheduler.tasks.clear()
        self.assertEqual(self.status()["status"], "tasks_absent")
        self.assertEqual(len(self.install()["created_tasks"]), 2)

    def test_transport_uses_encoded_data_and_never_force_or_executes_upstream(self):
        self.transport.stop()
        fake_output = subprocess.CompletedProcess([], 0, stdout='"S-1-5-21-test"\n', stderr="")
        with mock.patch.object(manager.sys, "platform", "win32"), mock.patch.object(manager.shutil, "which", return_value="powershell.exe"), mock.patch.object(manager.subprocess, "run", return_value=fake_output) as run:
            scheduler = manager.WindowsScheduler()
            self.assertEqual(scheduler.identity(), "S-1-5-21-test")
            args = run.call_args.args[0]
            self.assertEqual(args[:5], ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand"])
            import base64
            decoded = base64.b64decode(args[5]).decode("utf-16-le")
            self.assertNotIn("-ExecutionPolicy", decoded)
            self.assertNotIn("-Force", decoded)
            self.assertNotIn("accessToken", decoded)
            self.assertEqual(run.call_args.kwargs["timeout"], 60)

    def test_windows_and_scheduler_errors_are_specific(self):
        with mock.patch.object(manager.sys, "platform", "linux"):
            self.assert_code("WINDOWS_REQUIRED", manager.WindowsScheduler)
        self.transport.stop()
        with mock.patch.object(manager.sys, "platform", "win32"), mock.patch.object(manager.shutil, "which", return_value="powershell.exe"), mock.patch.object(manager.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, "", "do not expose raw transport output")):
            error = self.assert_code("SCHEDULER_ERROR", manager.WindowsScheduler().identity)
            self.assertNotIn("raw transport", str(error))

    def test_optional_scheduler_info_failure_does_not_undo_verified_install(self):
        with mock.patch.object(self.scheduler, "info", side_effect=manager.AddonError("SCHEDULER_ERROR", "info unavailable")):
            result = self.install()
        self.assertEqual(result["status"], "tasks_installed")
        self.assertEqual(len(self.scheduler.tasks), 2)
        self.assertFalse(result["task_info"][0]["info_available"])

    @unittest.skipUnless(sys.platform == "win32" and shutil.which("powershell.exe"), "Mock-cmdlet PowerShell roundtrip requires Windows PowerShell")
    def test_powershell_normalizes_and_removes_only_fixture_tasks_without_real_cmdlets(self):
        # Real PowerShell language/JSON behavior, with every scheduled-task
        # command replaced by an in-memory function before any invocation.
        import base64
        self.transport.stop()
        spec = manager.make_receipt(self.runtime, self.scheduler.identity(), self.pythonw)["tasks"][1]
        fixture = {
            "TaskName": spec["name"], "TaskPath": "\\", "Description": spec["description"],
            "Actions": [{"Execute": spec["actions"][0]["execute"], "Arguments": spec["actions"][0]["arguments"], "WorkingDirectory": str(self.runtime)}],
            "Principal": {"UserId": self.scheduler.identity(), "LogonType": "Interactive", "RunLevel": "Limited"},
            "Triggers": [{"CimClass": {"CimClassName": "MSFT_TaskDailyTrigger"}, "StartBoundary": row["start_boundary"],
                          "DaysInterval": 1, "Enabled": True, "Repetition": {"Interval": "PT0S"}, "RandomDelay": "PT0S", "EndBoundary": ""}
                         for row in reversed(spec["triggers"])],
            "Settings": {"Enabled": True, "Hidden": True, "StartWhenAvailable": True, "DisallowStartIfOnBatteries": False,
                         "RunOnlyIfIdle": False, "RunOnlyIfNetworkAvailable": False, "WakeToRun": False,
                         "StopIfGoingOnBatteries": False, "ExecutionTimeLimit": "PT5M", "MultipleInstances": "IgnoreNew"},
        }
        payload = base64.b64encode(json.dumps(fixture).encode("utf-8")).decode("ascii")
        definitions = "\n$fixture = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + payload + "')) | ConvertFrom-Json\n" + r'''
function Get-ScheduledTask { [CmdletBinding()] param($TaskPath) return $fixture }
function Stop-ScheduledTask { [CmdletBinding()] param($TaskName, $TaskPath) $script:fixtureStopped = $true }
function Unregister-ScheduledTask {
    [CmdletBinding(SupportsShouldProcess=$true)] param($TaskName, $TaskPath)
    if (-not $script:fixtureStopped) { throw 'fixture must be stopped first' }
}
'''
        scheduler = manager.WindowsScheduler()
        with mock.patch.object(manager, "PS_COMMON", manager.PS_COMMON + definitions):
            self.assertTrue(scheduler.exists(spec["name"]))
            self.assertFalse(scheduler.exists("absent-fixture"))
            self.assertIsNone(scheduler.get("absent-fixture"))
            self.assertEqual(scheduler.get(spec["name"]), spec)
            self.assertIsNone(scheduler.remove(spec))
            changed = copy.deepcopy(spec)
            changed["actions"][0]["arguments"] = "changed"
            self.assert_code("SCHEDULER_ERROR", lambda: scheduler.remove(changed))


if __name__ == "__main__":
    unittest.main()
