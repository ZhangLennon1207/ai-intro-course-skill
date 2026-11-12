"""Explicit, current-user setup for the pinned optional WorkBuddy add-on.

This manager never executes signin.py, opens login data, or calls an account API.
The upstream program remains unchanged and runs only on the registered schedule.
"""
from __future__ import annotations

import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


COMMIT = "34048c1b9636c5a03af580d5e9221c8bbe0c1e6c"
REPOSITORY = "88lin/workbuddy-auto-signin"
HASHES = {
    "signin.py": "f3cf601e0cda23b684b9d6079a41b5ff40a24e2ef18d61256036afafa02d5de5",
    "install-windows.ps1": "77219b2084a04c006baebc7a3d8f0e0dd96a47e7005dfbed35f20f8f6ad7ce57",
    "LICENSE.txt": "10d8eaa57b1d26c6ed73d22b7c75a0f9329b160e4dd5cd538538ea65399d2364",
}
ADDON_ROOT = Path(__file__).resolve().parents[1]
RECEIPT_NAME = "installation-receipt.json"
MANAGER = "ai-intro-course/workbuddy-auto-signin/v1"
MODE = "signin-growth"
TASK_PREFIX = "AIIntroCourse.WorkBuddy."
LEGACY_TASK_NAMES = ("WorkBuddyAutoSignin", "WorkBuddyGrowthPoll")
TIMES = (["00:05"], ["01:00", "05:00", "09:00", "13:00", "17:00", "21:00"])
EFFECTS = [
    "Read the current user's local WorkBuddy login; encrypted login may use the installed client runtime.",
    "At the scheduled times, check and claim daily signin and run the complete upstream growth center.",
    "Claim gifts, dispatch Buddy, accept tasks, claim eligible rewards, use makeup cards, redeem streak rewards, draw boxes, and spend energy.",
    "Use the API endpoint selected by the upstream login/configuration; that endpoint is not restricted by this manager.",
    "Run silently, allow battery operation, catch up missed schedules, and write upstream logs next to signin.py.",
]


class AddonError(Exception):
    def __init__(self, code: str, message: str, **details):
        super().__init__(message)
        self.code = code
        self.details = details


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def untouched_paths(path: Path) -> None:
    """Reject redirected runtime/receipt paths, including Windows junctions."""
    for item in (path, *path.parents):
        redirected = item.is_symlink() or (hasattr(item, "is_junction") and item.is_junction())
        if item.exists():
            redirected = redirected or bool(getattr(item.lstat(), "st_file_attributes", 0) & 0x400)
        if redirected:
            raise AddonError("PATH_CONFLICT", f"Refusing redirected path: {item}")


def runtime_dir(local_appdata=None) -> Path:
    value = local_appdata if local_appdata is not None else os.environ.get("LOCALAPPDATA")
    if not value or not Path(value).is_absolute():
        raise AddonError("LOCALAPPDATA_MISSING", "An absolute current-user LOCALAPPDATA directory is required.")
    path = Path(value) / "ai-intro-course" / "addons" / "workbuddy-auto-signin" / COMMIT
    untouched_paths(path)
    return path


def source_assets(addon_root: Path) -> dict[str, bytes]:
    try:
        lock = json.loads((addon_root / "upstream-lock.json").read_text(encoding="utf-8"))
        expected = {"schema_version": 1, "repository": REPOSITORY, "commit": COMMIT, "files": HASHES}
        if lock != expected:
            raise AddonError("SOURCE_INTEGRITY", "The upstream lock does not match this audited manager version.")
        content = {}
        for name, expected_hash in HASHES.items():
            path = addon_root / "assets" / "upstream" / name
            untouched_paths(path)
            blob = path.read_bytes()
            if digest(blob) != expected_hash:
                raise AddonError("SOURCE_INTEGRITY", f"Bundled upstream asset failed SHA256 verification: {name}")
            content[name] = blob
        return content
    except (OSError, ValueError) as exc:
        raise AddonError("SOURCE_INTEGRITY", "The pinned upstream assets or lock are missing or unreadable.") from exc


def find_pythonw() -> Path:
    candidates = [Path(sys.executable).with_name("pythonw.exe")]
    for command in ("pythonw.exe", "python.exe"):
        found = shutil.which(command)
        if found:
            candidates.append(Path(found).with_name("pythonw.exe"))
    for parent in (Path("C:/"), Path(os.environ.get("LOCALAPPDATA", ".")) / "Programs/Python", Path("C:/Program Files")):
        candidates.extend(sorted(parent.glob("Python3*/pythonw.exe"), reverse=True))
    for candidate in candidates:
        if candidate.is_absolute() and candidate.is_file():
            return candidate.absolute()
    raise AddonError("PYTHONW_MISSING", "Python 3 with pythonw.exe is required. Install it separately, then retry.")


def task_names(sid: str) -> list[str]:
    suffix = digest(sid.encode("utf-8"))[:12]
    return [f"{TASK_PREFIX}Signin.{suffix}", f"{TASK_PREFIX}GrowthPoll.{suffix}"]


def new_boundaries() -> list[list[str]]:
    threshold = datetime.now() + timedelta(minutes=10)
    rows = []
    for times in TIMES:
        row = []
        for at in times:
            first = threshold.replace(hour=int(at[:2]), minute=int(at[3:]), second=0, microsecond=0)
            if first <= threshold:
                first += timedelta(days=1)
            row.append(first.isoformat(timespec="seconds"))
        rows.append(row)
    return rows


def task_spec(name: str, sid: str, root: Path, pythonw: Path, marker: str, poll: bool, boundaries: list[str]) -> dict:
    # Property order also matches the PowerShell transport's normalized view.
    return {
        "name": name, "path": "\\", "description": marker,
        "actions": [{"execute": str(pythonw), "arguments": f'"{root / "signin.py"}" {"silent-poll" if poll else "silent"}', "working_directory": str(root)}],
        "principal": {"sid": sid, "logon_type": "Interactive", "run_level": "Limited"},
        "triggers": [{"type": "daily", "at": at, "start_boundary": boundary, "days_interval": 1, "enabled": True, "repetition_interval": "", "random_delay": "", "end_boundary": ""}
                     for at, boundary in zip(TIMES[int(poll)], boundaries)],
        "settings": {"enabled": True, "hidden": True, "start_when_available": True,
                     "disallow_battery": False, "stop_on_battery": False,
                     "run_only_if_idle": False, "run_only_if_network_available": False, "wake_to_run": False,
                     "execution_time_limit": "PT5M" if poll else "PT10M", "multiple_instances": "IgnoreNew"},
    }


def make_receipt(root: Path, sid: str, pythonw: Path, boundaries=None) -> dict:
    core = {"schema_version": 1, "manager": MANAGER, "commit": COMMIT, "mode": MODE,
            "owner_sid": sid, "install_dir": str(root), "pythonw": str(pythonw), "files": HASHES}
    marker = f"{MANAGER}; ownership={digest(canonical(core))}"
    names = task_names(sid)
    starts = new_boundaries() if boundaries is None else boundaries
    return dict(core, tasks=[task_spec(name, sid, root, pythonw, marker, bool(index), starts[index]) for index, name in enumerate(names)])


def receipt_boundaries(receipt: dict) -> list[list[str]]:
    starts = [[trigger["start_boundary"] for trigger in task["triggers"]] for task in receipt["tasks"]]
    if len(starts) != 2:
        raise ValueError("invalid trigger counts")
    for row, times in zip(starts, TIMES):
        if len(row) != len(times):
            raise ValueError("invalid trigger counts")
        for boundary, at in zip(row, times):
            parsed = datetime.strptime(boundary, "%Y-%m-%dT%H:%M:%S")
            if parsed.strftime("%Y-%m-%dT%H:%M:%S") != boundary or boundary[11:] != at + ":00":
                raise ValueError("invalid trigger boundary")
    return starts


def load_receipt(root: Path, sid: str) -> dict | None:
    path = root / RECEIPT_NAME
    untouched_paths(path)
    if not path.exists():
        return None
    try:
        blob = path.read_bytes()
        parsed = json.loads(blob)
        pythonw = Path(parsed["pythonw"])
        if not pythonw.is_absolute() or pythonw.name.lower() != "pythonw.exe":
            raise ValueError("invalid interpreter")
        expected = make_receipt(root, sid, pythonw, receipt_boundaries(parsed))
        if blob != canonical(expected):
            raise ValueError("receipt mismatch")
        return expected
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise AddonError("RECEIPT_CONFLICT", "The existing receipt was modified, belongs to another user, or has unexpected paths. It was preserved.") from exc


def replace_owned_receipt(path: Path, previous: dict, receipt: dict) -> None:
    """Refresh only missing tasks' expired first dates, never an edited receipt."""
    if path.read_bytes() != canonical(previous):
        raise AddonError("RECEIPT_CONFLICT", "Receipt changed during setup and was preserved.")
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(canonical(receipt))
        if path.read_bytes() != canonical(previous):
            raise AddonError("RECEIPT_CONFLICT", "Receipt changed during setup and was preserved.")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def runtime_problems(root: Path) -> list[str]:
    problems = []
    for name, expected in HASHES.items():
        path = root / name
        untouched_paths(path)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            problems.append(name)
    return problems


def preflight_files(root: Path, assets: dict[str, bytes]) -> None:
    for name, content in assets.items():
        path = root / name
        untouched_paths(path)
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise AddonError("FILE_CONFLICT", f"Existing user-modified or unrelated file was preserved: {path}")


@contextmanager
def operation_lock(root: Path):
    untouched_paths(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / ".manage-signin.lock"
    token = uuid.uuid4().hex.encode("ascii")
    try:
        with path.open("xb") as stream:
            stream.write(token)
    except FileExistsError as exc:
        raise AddonError("MANAGER_BUSY", "Another setup operation is active, or its lock remains after interruption. Check before removing .manage-signin.lock.") from exc
    try:
        yield
    finally:
        if path.is_file() and not path.is_symlink() and path.read_bytes() == token:
            path.unlink()


# All user-controlled strings enter PowerShell through a base64-encoded JSON
# payload. No upstream program or credential is evaluated by this transport.
PS_COMMON = r'''
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
function Read-Task($name) {
    $found = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskPath -eq '\' -and $_.TaskName -eq $name })
    if ($found.Count -eq 0) { return $null }
    if ($found.Count -ne 1) { throw 'Ambiguous scheduled task' }
    $t = $found[0]
    $sid = [string]$t.Principal.UserId
    if ($sid -notmatch '^S-1-') {
        $sid = ([System.Security.Principal.NTAccount]::new($sid)).Translate([System.Security.Principal.SecurityIdentifier]).Value
    }
    [pscustomobject]@{
        name = [string]$t.TaskName; path = [string]$t.TaskPath; description = [string]$t.Description
        actions = @($t.Actions | ForEach-Object { [pscustomobject]@{
            execute = [string]$_.Execute; arguments = [string]$_.Arguments; working_directory = [string]$_.WorkingDirectory
        } })
        principal = [pscustomobject]@{ sid = $sid; logon_type = [string]$t.Principal.LogonType; run_level = [string]$t.Principal.RunLevel }
        triggers = @($t.Triggers | Sort-Object { if ($_.StartBoundary) { ([datetime]$_.StartBoundary).ToString('HH:mm') } else { '' } } | ForEach-Object { [pscustomobject]@{
            type = $(if ($_.CimClass.CimClassName -eq 'MSFT_TaskDailyTrigger') { 'daily' } else { [string]$_.CimClass.CimClassName })
            at = $(if ([string]::IsNullOrEmpty([string]$_.StartBoundary)) { '' } else { ([datetime]$_.StartBoundary).ToString('HH:mm') })
            start_boundary = [string]$_.StartBoundary; days_interval = [int]$_.DaysInterval
            enabled = [bool]$_.Enabled
            repetition_interval = $(if ([string]$_.Repetition.Interval -in @('', 'PT0S')) { '' } else { [string]$_.Repetition.Interval })
            random_delay = $(if ([string]$_.RandomDelay -in @('', 'PT0S')) { '' } else { [string]$_.RandomDelay })
            end_boundary = [string]$_.EndBoundary
        } })
        settings = [pscustomobject]@{
            enabled = [bool]$t.Settings.Enabled; hidden = [bool]$t.Settings.Hidden; start_when_available = [bool]$t.Settings.StartWhenAvailable
            disallow_battery = [bool]$t.Settings.DisallowStartIfOnBatteries; stop_on_battery = [bool]$t.Settings.StopIfGoingOnBatteries
            run_only_if_idle = [bool]$t.Settings.RunOnlyIfIdle; run_only_if_network_available = [bool]$t.Settings.RunOnlyIfNetworkAvailable; wake_to_run = [bool]$t.Settings.WakeToRun
            execution_time_limit = [string]$t.Settings.ExecutionTimeLimit; multiple_instances = [string]$t.Settings.MultipleInstances
        }
    }
}
'''


class WindowsScheduler:
    def __init__(self):
        if sys.platform != "win32":
            raise AddonError("WINDOWS_REQUIRED", "Installation, scheduler status, and removal require Windows; plan works on every platform.")
        self.executable = shutil.which("powershell.exe")
        if not self.executable:
            raise AddonError("POWERSHELL_MISSING", "Windows PowerShell and its ScheduledTasks module are required.")

    def run(self, operation: str, payload=None):
        encoded_payload = base64.b64encode(json.dumps(payload or {}).encode("utf-8")).decode("ascii")
        script = PS_COMMON + "\n$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('" + encoded_payload + "')) | ConvertFrom-Json\n"
        if operation == "identity":
            script += "$result = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value\n"
        elif operation == "get":
            script += "$result = Read-Task $p.name\n"
        elif operation == "exists":
            script += "$result = @(Get-ScheduledTask -ErrorAction Stop | Where-Object { $_.TaskPath -eq '\\' -and $_.TaskName -eq $p.name }).Count -gt 0\n"
        elif operation == "info":
            script += r'''
$info = Get-ScheduledTaskInfo -TaskName $p.name -TaskPath '\' -ErrorAction Stop
$result = [pscustomobject]@{
    next_run_time = $info.NextRunTime.ToString('o')
    last_run_time = $info.LastRunTime.ToString('o')
    last_task_result = [long]$info.LastTaskResult
}
'''
        elif operation == "create":
            script += r'''
$s = $p.spec
if ($null -ne (Read-Task $s.name)) { throw 'Task already exists; refusing overwrite' }
$a = $s.actions[0]
$action = New-ScheduledTaskAction -Execute $a.execute -Argument $a.arguments -WorkingDirectory $a.working_directory
$principal = New-ScheduledTaskPrincipal -UserId $s.principal.sid -LogonType Interactive -RunLevel Limited
$triggers = @($s.triggers | ForEach-Object { New-ScheduledTaskTrigger -Daily -At ([datetime]$_.start_boundary) })
$minutes = $(if ($s.settings.execution_time_limit -eq 'PT5M') { 5 } else { 10 })
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -Hidden -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes $minutes) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $s.name -TaskPath '\' -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Description $s.description -ErrorAction Stop | Out-Null
$result = Read-Task $s.name
'''
        elif operation == "remove":
            script += r'''
$s = $p.spec
$live = Read-Task $s.name
if ($null -ne $live) {
    if (($live | ConvertTo-Json -Depth 12 -Compress) -cne ($s | ConvertTo-Json -Depth 12 -Compress)) { throw 'Task changed; refusing removal' }
    Stop-ScheduledTask -TaskName $s.name -TaskPath '\' -ErrorAction Stop
    Unregister-ScheduledTask -TaskName $s.name -TaskPath '\' -Confirm:$false -ErrorAction Stop
}
$result = $null
'''
        else:
            raise ValueError("Unknown scheduler operation")
        script += "\nif ($null -eq $result) { [Console]::WriteLine('null') } else { ConvertTo-Json -InputObject $result -Depth 12 -Compress }\n"
        command = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        try:
            result = subprocess.run([self.executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", command],
                                    capture_output=True, text=True, encoding="utf-8", timeout=60,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if result.returncode:
                raise AddonError("SCHEDULER_ERROR", f"Windows rejected scheduler operation '{operation}'; no elevation or policy change was attempted.")
            return json.loads(result.stdout.strip().lstrip("\ufeff"))
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise AddonError("SCHEDULER_ERROR", f"Unable to complete scheduler operation '{operation}'.") from exc

    def identity(self):
        return self.run("identity")

    def get(self, name):
        return self.run("get", {"name": name})

    def exists(self, name):
        return self.run("exists", {"name": name})

    def create(self, spec):
        return self.run("create", {"spec": spec})

    def remove(self, spec):
        return self.run("remove", {"spec": spec})

    def info(self, name):
        return self.run("info", {"name": name})


def read_tasks(scheduler, receipt: dict | None, sid: str) -> list:
    expected = {task["name"]: task for task in receipt["tasks"]} if receipt else {}
    found = []
    for name in task_names(sid):
        if receipt is None and scheduler.exists(name):
            raise AddonError("TASK_CONFLICT", f"A task with this name has no matching receipt and was preserved: {name}")
        actual = scheduler.get(name)
        if actual is not None and actual != expected.get(name):
            raise AddonError("TASK_CONFLICT", f"A task with this name is unowned or modified and was preserved: {name}")
        found.append(actual)
    return found


def check_legacy_tasks(scheduler) -> None:
    conflicts = [name for name in LEGACY_TASK_NAMES if scheduler.exists(name)]
    if conflicts:
        raise AddonError("LEGACY_TASK_CONFLICT", "Existing upstream WorkBuddy tasks would duplicate account operations. They were preserved; review and remove them separately before enabling this add-on.",
                         legacy_tasks=conflicts)


def task_info(scheduler, tasks: list) -> list[dict]:
    """Optional scheduler timestamps are observations, never signin evidence."""
    rows = []
    for task in tasks:
        if task is None:
            continue
        row = {"name": task["name"]}
        try:
            row.update(scheduler.info(task["name"]))
        except (AddonError, AttributeError):
            row["info_available"] = False
        rows.append(row)
    return rows


def outcome(state: str, root: Path, **extra) -> dict:
    return {"status": state, "mode": MODE, "commit": COMMIT, "runtime_dir": str(root),
            "log_path": str(root / "signin.log"),
            "manager_executed_account_actions": False, "credentials_checked": False,
            "daily_signin_verified": False, "growth_results_verified": False, **extra}


def plan(local_appdata=None) -> dict:
    try:
        destination = str(runtime_dir(local_appdata))
    except AddonError as exc:
        if exc.code != "LOCALAPPDATA_MISSING":
            raise
        destination = "%LOCALAPPDATA%/ai-intro-course/addons/workbuddy-auto-signin/" + COMMIT
    return {"status": "plan", "mode": MODE, "explicit_install_mode_required": True,
            "platform": "Windows current user", "runtime_dir": destination, "commit": COMMIT,
            "source_sha256": HASHES, "effects": EFFECTS,
            "legacy_tasks_checked": False, "legacy_task_conflict_names": list(LEGACY_TASK_NAMES),
            "first_run": "Each new trigger starts at its next daily clock time more than ten minutes in the future; registration does not catch up earlier occurrences.",
            "tasks": [{"name": TASK_PREFIX + "Signin.<current-user-SID-hash>", "at": ["00:05"], "arguments": "silent", "limit_minutes": 10},
                      {"name": TASK_PREFIX + "GrowthPoll.<current-user-SID-hash>", "at": ["01:00", "05:00", "09:00", "13:00", "17:00", "21:00"], "arguments": "silent-poll", "limit_minutes": 5}],
            "installation_actions": ["Verify pinned SHA256 assets", "Refuse activation if the legacy upstream WorkBuddy tasks exist", "Preserve matching files; refuse modified files or receipts", "Copy runtime to stable current-user storage", "Register two limited interactive tasks without replacing existing tasks", "Read back both full task definitions before reporting installation"],
            "uninstall": "Remove only unchanged owned tasks; retain runtime, receipt, and logs.",
            "manager_executed_account_actions": False, "credentials_checked": False,
            "daily_signin_verified": False, "growth_results_verified": False}


def install_addon(*, mode=None, addon_root=ADDON_ROOT, local_appdata=None, scheduler=None, pythonw=None) -> dict:
    if mode != MODE:
        raise AddonError("MODE_REQUIRED", "Explicit --mode signin-growth is required to enable all scheduled account actions. Run plan to review them.")
    scheduler = scheduler if scheduler is not None else WindowsScheduler()
    root = runtime_dir(local_appdata)
    assets = source_assets(Path(addon_root))
    sid = scheduler.identity()
    check_legacy_tasks(scheduler)
    with operation_lock(root):
        previous = load_receipt(root, sid)
        interpreter = Path(previous["pythonw"]) if previous else Path(pythonw) if pythonw is not None else find_pythonw()
        if not interpreter.is_absolute() or interpreter.name.lower() != "pythonw.exe" or not interpreter.is_file():
            raise AddonError("PYTHONW_MISSING", "The required pythonw.exe is missing; no task was registered.")
        found = read_tasks(scheduler, previous, sid)
        boundaries = receipt_boundaries(previous) if previous else new_boundaries()
        refreshed = new_boundaries()
        for index, actual in enumerate(found):
            if actual is None and any(datetime.fromisoformat(value) <= datetime.now() + timedelta(minutes=5) for value in boundaries[index]):
                boundaries[index] = refreshed[index]
        receipt = make_receipt(root, sid, interpreter, boundaries)
        preflight_files(root, assets)
        # Exclusive creation never replaces a pre-existing or user-edited file.
        created_files = []
        for name, content in assets.items():
            target = root / name
            if not target.exists():
                with target.open("xb") as stream:
                    stream.write(content)
                created_files.append(name)
        receipt_path = root / RECEIPT_NAME
        if previous is None:
            with receipt_path.open("xb") as stream:
                stream.write(canonical(receipt))
        elif previous != receipt:
            replace_owned_receipt(receipt_path, previous, receipt)
        attempted = []
        try:
            check_legacy_tasks(scheduler)
            for actual, spec in zip(found, receipt["tasks"]):
                if actual is None:
                    attempted.append(spec)
                    scheduler.create(spec)
                    if scheduler.get(spec["name"]) != spec:
                        raise AddonError("TASK_VERIFICATION", f"Registered task did not match its expected definition: {spec['name']}")
            verified = read_tasks(scheduler, receipt, sid)
            check_legacy_tasks(scheduler)
            if any(task is None for task in verified) or runtime_problems(root) or load_receipt(root, sid) != receipt:
                raise AddonError("INSTALL_VERIFICATION", "Runtime, receipt, or tasks changed during installation.")
        except Exception as exc:
            failures = []
            for spec in reversed(attempted):
                try:
                    actual = scheduler.get(spec["name"])
                    if actual is not None:
                        if actual != spec:
                            failures.append(spec["name"] + ": changed/unowned; preserved")
                        else:
                            scheduler.remove(spec)
                            if scheduler.get(spec["name"]) is not None:
                                failures.append(spec["name"] + ": removal not verified")
                except Exception:
                    failures.append(spec["name"] + ": rollback failed; inspect scheduler")
            raise AddonError("INSTALL_FAILED", "Installation did not finish. Previously existing tasks, runtime files, logs, and receipt were preserved.",
                             cause=exc.code if isinstance(exc, AddonError) else type(exc).__name__,
                             rollback_failures=failures, runtime_retained=True) from exc
        return outcome("tasks_installed", root, scheduler_verified=True, tasks=[task["name"] for task in verified],
                       task_info=task_info(scheduler, verified),
                       created_tasks=[task["name"] for task in attempted], created_files=created_files,
                       changed=bool(attempted or created_files or previous != receipt))


def status_addon(*, local_appdata=None, scheduler=None) -> dict:
    scheduler = scheduler if scheduler is not None else WindowsScheduler()
    root = runtime_dir(local_appdata)
    sid = scheduler.identity()
    check_legacy_tasks(scheduler)
    receipt = load_receipt(root, sid)
    found = read_tasks(scheduler, receipt, sid)
    if receipt is None:
        return outcome("not_installed", root, scheduler_verified=True, tasks=[])
    problems = runtime_problems(root)
    dependencies = [] if Path(receipt["pythonw"]).is_file() else [receipt["pythonw"]]
    present = [task["name"] for task in found if task is not None]
    state = "tasks_installed" if len(present) == 2 and not problems and not dependencies else "tasks_absent" if not present else "incomplete"
    return outcome(state, root, scheduler_verified=True, tasks=present, task_info=task_info(scheduler, found),
                   runtime_problems=problems, dependency_problems=dependencies)


def uninstall_addon(*, local_appdata=None, scheduler=None) -> dict:
    scheduler = scheduler if scheduler is not None else WindowsScheduler()
    root = runtime_dir(local_appdata)
    sid = scheduler.identity()
    if not root.exists():
        read_tasks(scheduler, None, sid)
        return outcome("not_installed", root, removed_tasks=[], runtime_retained=True)
    with operation_lock(root):
        receipt = load_receipt(root, sid)
        found = read_tasks(scheduler, receipt, sid)
        removed = []
        for task in found:
            if task is not None:
                scheduler.remove(task)
                if scheduler.get(task["name"]) is not None:
                    raise AddonError("UNINSTALL_FAILED", "A task remains after removal; runtime and logs were preserved.", removed_tasks=removed)
                removed.append(task["name"])
        return outcome("tasks_removed" if removed else "tasks_absent", root, removed_tasks=removed, runtime_retained=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="plan", choices=("plan", "install", "status", "uninstall"))
    parser.add_argument("--mode", choices=(MODE,), help="Required for install; enables signin AND the complete upstream growth center.")
    args = parser.parse_args(argv)
    try:
        if args.action == "install":
            result = install_addon(mode=args.mode)
        else:
            result = {"plan": plan, "status": status_addon, "uninstall": uninstall_addon}[args.action]()
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except AddonError as exc:
        print(json.dumps({"status": "error", "code": exc.code, "message": str(exc),
                          "manager_executed_account_actions": False, "daily_signin_verified": False, **exc.details}, ensure_ascii=False))
        return 1
    except OSError as exc:
        print(json.dumps({"status": "error", "code": "FILESYSTEM_ERROR", "message": str(exc),
                          "manager_executed_account_actions": False, "daily_signin_verified": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
