"""All process/power calls are mocked; these tests never change macOS settings."""
import importlib.util
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("guard", ROOT / "scripts/guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class GuardPolicyTests(unittest.TestCase):
    def decide(self, disabled=True, source="battery", percent=80, running=True,
               session=None, now=100000.0, monotonic=20000.0):
        return guard.decision(disabled, source, percent, running, session, now, monotonic)

    def test_disabled_flag_clears_session_without_command(self):
        result = self.decide(disabled=False, session={"source": "ac"})
        self.assertEqual(result[:2], (False, None))

    def test_missing_app_or_unknown_state_fails_closed(self):
        for kwargs in ({"running": False}, {"disabled": None}, {"source": "unknown"},
                       {"percent": -1}, {"percent": 101}):
            with self.subTest(kwargs=kwargs):
                self.assertTrue(self.decide(**kwargs)[0])

    def test_battery_floor_is_inclusive(self):
        for percent in (0, 1, 29, 30):
            self.assertTrue(self.decide(percent=percent)[0])
        self.assertFalse(self.decide(percent=31)[0])

    def test_ac_does_not_use_battery_floor(self):
        self.assertFalse(self.decide(source="ac", percent=20)[0])

    def test_battery_session_boundary(self):
        _, session, _ = self.decide()
        self.assertEqual(session["limit"], 7200)
        self.assertFalse(self.decide(session=session, now=107199, monotonic=27199)[0])
        self.assertTrue(self.decide(session=session, now=107200, monotonic=27200)[0])

    def test_ac_session_boundary(self):
        _, session, _ = self.decide(source="ac")
        self.assertEqual(session["limit"], 43200)
        self.assertFalse(self.decide(source="ac", session=session, now=143199, monotonic=63199)[0])
        self.assertTrue(self.decide(source="ac", session=session, now=143200, monotonic=63200)[0])

    def test_unplugging_ac_session_ends_it(self):
        _, session, _ = self.decide(source="ac")
        self.assertTrue(self.decide(source="battery", session=session)[0])

    def test_plugging_in_does_not_extend_battery_deadline(self):
        _, session, _ = self.decide()
        reset, preserved, _ = self.decide(source="ac", session=session, now=100600, monotonic=20600)
        self.assertFalse(reset)
        self.assertEqual(preserved["limit"], 7200)
        self.assertTrue(self.decide(source="ac", session=session, now=107200, monotonic=27200)[0])

    def test_clock_changes_cannot_extend_session(self):
        _, session, _ = self.decide()
        self.assertTrue(self.decide(session=session, now=99900, monotonic=27200)[0])
        self.assertTrue(self.decide(session=session, now=107200, monotonic=20001)[0])
        self.assertTrue(self.decide(session=session, now=99900, monotonic=19999)[0])


class GuardReaderTests(unittest.TestCase):
    def test_reads_expected_macos_output(self):
        outputs = [(0, "System-wide power settings:\n SleepDisabled 1\n"),
                   (0, "Now drawing from 'Battery Power'\n -InternalBattery-0 61%; discharging;"),
                   (0, guard.APP + "\n/usr/bin/python3\n")]
        with patch.object(guard, "command", side_effect=outputs):
            self.assertEqual(guard.read_state(), (True, "battery", 61, True))

    def test_other_application_does_not_count_as_our_app(self):
        outputs = [(0, "SleepDisabled 1"), (0, "'AC Power' 85%;"),
                   (0, "/Applications/Sleepless.app/Contents/MacOS/Sleepless\n")]
        with patch.object(guard, "command", side_effect=outputs):
            self.assertEqual(guard.read_state(), (True, "ac", 85, False))

    def test_missing_power_data_is_unknown(self):
        with patch.object(guard, "command", return_value=(1, "")):
            self.assertEqual(guard.read_state(), (None, "unknown", -1, False))

    def test_command_timeout_is_nonfatal(self):
        with patch.object(guard.subprocess, "run", side_effect=subprocess.TimeoutExpired("test", 4)):
            self.assertEqual(guard.command(["placeholder"]), (-1, ""))

    def test_reset_can_only_disable_keep_awake(self):
        with patch.object(guard, "command", return_value=(0, "")) as command, patch.object(guard, "log"):
            self.assertTrue(guard.reset_sleep("test"))
        command.assert_called_once_with(["/usr/bin/sudo", "-n", "/usr/bin/pmset", "-a", "disablesleep", "0"])

    def test_failed_reset_is_not_reported_successful(self):
        with patch.object(guard, "command", return_value=(1, "")), patch.object(guard, "log"):
            self.assertFalse(guard.reset_sleep("test"))


if __name__ == "__main__":
    unittest.main()
