"""Installation planning and ownership checks; no sudo, launchctl, or real user paths."""
import importlib.util
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("manage", ROOT / "scripts/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name) / "Example User's Home"
        self.home.mkdir()
        self.uid = 501
        self.p = manage.paths(self.home, self.uid)

    def tearDown(self):
        self.temp.cleanup()

    def marker(self):
        self.p["base"].mkdir(parents=True, exist_ok=True)
        self.p["manifest"].write_text(json.dumps({"schema": 1, "application_id": manage.APP_ID, "uid": self.uid}))

    def test_runtime_paths_preserve_spaces_and_apostrophe(self):
        agent = plistlib.loads(plistlib.dumps(manage.guard_plist(self.p)))
        self.assertEqual(agent["ProgramArguments"], ["/usr/bin/python3", str(self.p["base"] / "guard.py")])
        self.assertNotIn("~", agent["ProgramArguments"][1])

    def test_grant_name_is_separate_from_upstream(self):
        self.assertEqual(self.p["grant"].name, "sleeplesscn-501")
        self.assertNotEqual(self.p["grant"].name, "sleepless-disablesleep")

    def test_unknown_installation_is_never_removed(self):
        with self.assertRaises(RuntimeError):
            manage.verify_owned(self.p, self.uid)

    def test_foreign_user_marker_is_rejected(self):
        self.marker()
        with self.assertRaises(RuntimeError):
            manage.verify_owned(self.p, self.uid + 1)

    def test_foreign_app_identity_is_rejected(self):
        self.marker()
        info = self.p["app"] / "Contents/Info.plist"
        info.parent.mkdir(parents=True)
        info.write_bytes(plistlib.dumps({"CFBundleIdentifier": "example.other.app"}))
        with self.assertRaises(RuntimeError):
            manage.verify_owned(self.p, self.uid)

    def test_foreign_launch_agent_is_rejected(self):
        self.marker()
        self.p["agent"].parent.mkdir(parents=True)
        self.p["agent"].write_bytes(plistlib.dumps({"Label": "example.other.guard"}))
        with self.assertRaises(RuntimeError):
            manage.verify_owned(self.p, self.uid)

    def test_owned_marker_is_accepted(self):
        self.marker()
        manage.verify_owned(self.p, self.uid)

    def test_symlink_parent_is_rejected(self):
        actual = self.home / "actual"
        actual.mkdir()
        (self.home / "Applications").symlink_to(actual)
        with self.assertRaises(RuntimeError):
            manage.refuse_symlinks(self.p, self.home)

    def test_existing_destination_stops_before_admin_command(self):
        self.p["app"].mkdir(parents=True)
        with patch.object(manage, "run") as run:
            with self.assertRaises(RuntimeError):
                manage.install(self.p, self.uid)
        run.assert_not_called()

    def test_failed_sleep_restoration_keeps_installation(self):
        self.marker()
        with patch.object(manage, "run", side_effect=subprocess.CalledProcessError(1, "mock")) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                manage.uninstall(self.p, self.uid)
        self.assertTrue(self.p["manifest"].exists())
        self.assertEqual(run.call_count, 1)

    def test_dry_run_never_executes_commands(self):
        for action in ("install", "uninstall"):
            with patch("sys.argv", ["manage.py", action, "--dry-run"]), \
                 patch.object(manage, "run") as run, \
                 patch("builtins.print"):
                manage.main()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
