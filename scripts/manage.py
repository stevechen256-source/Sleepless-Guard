#!/usr/bin/env python3
"""Per-user installation. Dry runs never execute power or administrator commands."""
import argparse
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import time

APP_ID = "io.github.sleeplesscn.app"
GUARD_ID = "io.github.sleeplesscn.guard"
ROOT = Path(__file__).resolve().parent.parent


def paths(home, uid):
    home = Path(home)
    base = home / "Library/Application Support/SleeplessCN"
    return {
        "app": home / "Applications/SleeplessCN.app",
        "base": base,
        "agent": home / "Library/LaunchAgents" / (GUARD_ID + ".plist"),
        "manifest": base / "installation.json",
        "grant": Path("/etc/sudoers.d") / ("sleeplesscn-" + str(uid)),
    }


def guard_plist(p):
    return {
        "Label": GUARD_ID,
        "ProgramArguments": ["/usr/bin/python3", str(p["base"] / "guard.py")],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ThrottleInterval": 2,
        "ExitTimeOut": 10,
        "ProcessType": "Background",
        "EnvironmentVariables": {"PYTHONDONTWRITEBYTECODE": "1"},
        "StandardOutPath": str(p["base"] / "launch.log"),
        "StandardErrorPath": str(p["base"] / "error.log"),
    }


def run(args, check=True, timeout=30):
    return subprocess.run(args, check=check, timeout=timeout)


def restore_verified():
    """Do not remove protection on a successful command with an unverified result."""
    run(["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", "0"], timeout=4)
    result = subprocess.run(["/usr/bin/pmset", "-g"], capture_output=True, text=True, timeout=4)
    lines = [line.split() for line in result.stdout.splitlines()
             if line.split() and line.split()[0].lower() == 'sleepdisabled']
    if result.returncode != 0 or lines != [["SleepDisabled", "0"]]:
        raise RuntimeError("Sleep restoration could not be verified; protection files were retained.")


def startup_verified(data, uid, now):
    """A recent JSON file alone does not establish successful guard startup."""
    try:
        return (data['schema_version'] == 2 and data['version'] == '0.2.0-dev'
                and data['uid'] == uid and -1 <= now - data['updated'] < 15
                and data['health'] == 'healthy' and data['observation']['state'] == 'off'
                and data['observation']['exit_code'] == 0
                and data['observation'].get('error') is None
                and data['last_reset']['verified'] is True
                and data['last_reset']['exit_code'] == 0
                and data['last_reset'].get('error') is None
                and data['last_reset']['observation']['state'] == 'off'
                and data['last_reset']['observation']['exit_code'] == 0)
    except (KeyError, TypeError, ValueError):
        return False


def refuse_symlinks(p, home):
    home = Path(home)
    for key in ("app", "base", "agent"):
        item = p[key]
        while item != home and item != item.parent:
            if item.is_symlink():
                raise RuntimeError("Refusing a symlink in the installation path: " + str(item))
            item = item.parent


def verify_owned(p, uid):
    """Check the installation marker and identities before any destructive cleanup."""
    if not p["manifest"].is_file() or p["manifest"].is_symlink():
        raise RuntimeError("No owned installation marker; refusing automated removal.")
    marker = json.loads(p["manifest"].read_text())
    if marker != {"schema": 1, "application_id": APP_ID, "uid": uid}:
        raise RuntimeError("The installation marker does not match this user and application.")
    if p["app"].exists():
        info = plistlib.loads((p["app"] / "Contents/Info.plist").read_bytes())
        if info.get("CFBundleIdentifier") != APP_ID:
            raise RuntimeError("The destination app has a different identity; refusing removal.")
    if p["agent"].exists():
        info = plistlib.loads(p["agent"].read_bytes())
        if info.get("Label") != GUARD_ID:
            raise RuntimeError("The launch agent belongs to a different application.")


def install(p, uid):
    # A release update is explicit: uninstall the previous CN Guard installation first.
    for key in ("app", "base", "agent", "grant"):
        if p[key].exists() or p[key].is_symlink():
            raise RuntimeError("Destination already exists; nothing overwritten: " + str(p[key]))
    source = ROOT / "build/SleeplessCN.app"
    if not source.is_dir():
        raise RuntimeError("Build the app first with ./build.sh.")
    run(["/usr/bin/codesign", "--verify", "--strict", str(source)])
    print("Installing an isolated per-user copy. Administrator permission is needed only for the two-command grant.", flush=True)
    run(["/bin/bash", str(ROOT / "grant.sh")], timeout=None)
    loaded = False
    try:
        p["base"].mkdir(mode=0o700, parents=True)
        p["app"].parent.mkdir(parents=True, exist_ok=True)
        p["agent"].parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, p["app"])
        shutil.copy2(ROOT / "scripts/guard.py", p["base"] / "guard.py")
        shutil.copy2(ROOT / "scripts/diagnostics.py", p["base"] / "diagnostics.py")
        p["manifest"].write_text(json.dumps({"schema": 1, "application_id": APP_ID, "uid": uid}, indent=2) + "\n")
        p["agent"].write_bytes(plistlib.dumps(guard_plist(p)))
        p["agent"].chmod(0o600)
        domain = "gui/" + str(uid)
        run(["/bin/launchctl", "enable", domain + "/" + GUARD_ID])
        run(["/bin/launchctl", "bootstrap", domain, str(p["agent"])])
        loaded = True
        for _ in range(20):
            status = p["base"] / "status.json"
            if status.exists():
                data = json.loads(status.read_text())
                if startup_verified(data, uid, time.time()):
                    break
            time.sleep(0.5)
        else:
            raise RuntimeError("The guard did not report a healthy startup.")
    except Exception:
        # The installation was verified absent above; only newly created owned paths are removed.
        # If OFF cannot be verified, retain the guard and grant for recovery.
        restore_verified()
        if loaded:
            run(["/bin/launchctl", "bootout", "gui/" + str(uid) + "/" + GUARD_ID], check=False)
        restore_verified()
        p["agent"].unlink(missing_ok=True)
        if p["app"].exists():
            shutil.rmtree(p["app"])
        if p["base"].exists():
            shutil.rmtree(p["base"])
        run(["/bin/bash", str(ROOT / "grant.sh"), "--revoke"], check=False, timeout=None)
        raise
    print("Installed. The guard is running; keep-awake and GUI login launch remain off.")
    print("Open the app when needed: open " + repr(str(p["app"])))


def uninstall(p, uid):
    verify_owned(p, uid)
    # Do not remove the guard or its grant until normal sleep has been requested successfully.
    restore_verified()
    app = p["app"] / "Contents/MacOS/SleeplessCN"
    if app.exists():
        run([str(app), "--unregister-login"])
    # This only sends Quit if this exact bundle is running; it never opens an absent app.
    script = 'if application id "' + APP_ID + '" is running then tell application id "' + APP_ID + '" to quit'
    run(["/usr/bin/osascript", "-e", script], check=False)
    # A nonresponsive app must not outlive the grant/guard being removed.
    result = subprocess.run(["/bin/ps", "-axo", "comm="], capture_output=True, text=True, check=True)
    if str(app) in {line.strip() for line in result.stdout.splitlines()}:
        raise RuntimeError("The app is still running. Quit it and retry; protection has been retained.")
    run(["/bin/launchctl", "bootout", "gui/" + str(uid) + "/" + GUARD_ID], check=False)
    restore_verified()
    run(["/bin/bash", str(ROOT / "grant.sh"), "--revoke"], timeout=None)
    p["agent"].unlink(missing_ok=True)
    if p["app"].exists():
        shutil.rmtree(p["app"])
    # Delete only known files. Preserve unexpected user-created data in the support directory.
    for name in ("guard.py", "diagnostics.py", "app-heartbeat.json", "guard.lock", "status.json", "status.tmp", "events.log", "events.previous.log", "launch.log", "error.log", "installation.json"):
        item = p["base"] / name
        if item.is_file() or item.is_symlink():
            item.unlink()
    try:
        p["base"].rmdir()
    except OSError:
        print("Extra files remain in the support directory; they were preserved.")
    print("Removed this application and its grant. Upstream or unrelated grants were not changed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("install", "uninstall"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    uid = os.getuid()
    home = Path.home()
    p = paths(home, uid)
    if args.dry_run:
        print(json.dumps({"action": args.action, "paths": {k: str(v) for k, v in p.items()},
                          "guard_launches_at_login": True, "gui_launches_at_login": False,
                          "enables_keep_awake": False}, indent=2))
        return
    if sys.platform != "darwin" or uid == 0:
        raise RuntimeError("Run this script as your regular macOS desktop user, without sudo.")
    refuse_symlinks(p, home)
    if args.action == "install":
        install(p, uid)
    else:
        uninstall(p, uid)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
        print("Stopped: " + str(error), file=sys.stderr)
        sys.exit(1)
