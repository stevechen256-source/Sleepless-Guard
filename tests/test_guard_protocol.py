"""Failure injection for the guard protocol. All command execution is mocked.

No test calls main(), installs a service, or changes any macOS power setting.
"""
import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('guard_protocol', ROOT / 'scripts/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def observation(state='off', code=0):
    return {'state': state, 'exit_code': code,
            'error': None if state != 'unknown' else 'pmset_output_invalid', 'sampled_at': 100.0}


def reset_result(verified=True):
    return {'requested_at': 100.0, 'exit_code': 0 if verified else 1,
            'error': None if verified else 'reset_command_failed', 'verified': verified,
            'observation': observation('off' if verified else 'on'), 'attempts': 1 if verified else 2}


def app(responsive=True, instance='11111111-1111-4111-8111-111111111111'):
    return {'running': True, 'responsive': responsive, 'instance_id': instance,
            'request_id': '33333333-3333-4333-8333-333333333333',
            'requested_state': 'on', 'error': None if responsive else 'app_heartbeat_invalid',
            'conflict': False}


class IsolatedGuardCase(unittest.TestCase):
    def setUp(self):
        # Guard against accidental real power/process calls in new or changed tests.
        self.command = patch.object(guard, 'command', side_effect=AssertionError('unmocked command')).start()
        self.addCleanup(patch.stopall)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        patch.object(guard, 'BASE', Path(self.temp.name)).start()
        patch.object(guard, 'log').start()


class ObservationTests(IsolatedGuardCase):
    def test_valid_zero_is_off(self):
        self.command.side_effect = None
        self.command.return_value = (0, 'System-wide power settings:\n SleepDisabled 0\n')
        result = guard.observe_sleep()
        self.assertEqual(result['state'], 'off')
        self.assertEqual(result['exit_code'], 0)
        self.assertIsNone(result['error'])

    def test_empty_missing_malformed_and_duplicate_flags_are_unknown(self):
        self.command.side_effect = None
        for text in ('', 'sleep 0', 'SleepDisabled 10', 'SleepDisabled -1',
                     'SleepDisabled 0\nSleepDisabled 1', 'SleepDisabled 0\nSleepDisabled 7', 'prefix SleepDisabled 0'):
            with self.subTest(text=text):
                self.command.return_value = (0, text)
                result = guard.observe_sleep()
                self.assertEqual(result['state'], 'unknown')
                self.assertEqual(result['error'], 'pmset_output_invalid')

    def test_nonzero_exit_does_not_trust_valid_looking_stdout(self):
        self.command.side_effect = None
        self.command.return_value = (1, 'SleepDisabled 0')
        self.assertEqual(guard.observe_sleep()['state'], 'unknown')

    def test_failed_power_query_does_not_trust_stdout(self):
        self.command.side_effect = None
        self.command.return_value = (1, "'AC Power' 80%;")
        self.assertEqual(guard.read_power(), ('unknown', -1))

    def test_out_of_range_percentage_is_unknown(self):
        self.command.side_effect = None
        self.command.return_value = (0, "'Battery Power' 101%;")
        self.assertEqual(guard.read_power(), ('battery', -1))

    def test_wrong_uid_and_other_paths_do_not_match(self):
        self.command.side_effect = None
        self.command.return_value = (0, f'100 {os.getuid()+1} {guard.APP}\n101 {os.getuid()} {guard.APP}.other')
        self.assertEqual(guard.app_processes(), [])


class ResetTests(IsolatedGuardCase):
    def test_success_requires_off_readback(self):
        self.command.side_effect = [(0, ''), (0, 'SleepDisabled 0')]
        result = guard.reset_sleep('test')
        self.assertTrue(result['verified'])
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(self.command.call_count, 2)

    def test_success_exit_but_still_on_is_failure_with_two_attempts(self):
        self.command.side_effect = [(0, ''), (0, 'SleepDisabled 1')] * 2
        result = guard.reset_sleep('test')
        self.assertFalse(result['verified'])
        self.assertEqual(result['error'], 'reset_readback_on')
        self.assertEqual(result['attempts'], 2)
        self.assertEqual(self.command.call_count, 4)

    def test_sudo_denied_is_failure_even_if_observed_off(self):
        self.command.side_effect = [(1, 'secret must not be logged'), (0, 'SleepDisabled 0')] * 2
        result = guard.reset_sleep('test')
        self.assertFalse(result['verified'])
        self.assertEqual(result['error'], 'reset_command_failed')
        self.assertNotIn('secret', json.dumps(result))

    def test_retry_can_recover(self):
        self.command.side_effect = [(1, ''), (0, 'SleepDisabled 1'), (0, ''), (0, 'SleepDisabled 0')]
        result = guard.reset_sleep('test')
        self.assertTrue(result['verified'])
        self.assertEqual(result['attempts'], 2)

    def test_unknown_readback_never_verified(self):
        self.command.side_effect = [(0, ''), (0, '')] * 2
        self.assertFalse(guard.reset_sleep('test')['verified'])

    def test_log_disk_full_cannot_abort_reset(self):
        self.command.side_effect = [(0, ''), (0, 'SleepDisabled 0')]
        with patch.object(guard, 'log', side_effect=OSError(errno.ENOSPC, 'secret-path')), contextlib.redirect_stderr(io.StringIO()) as stderr:
            result = guard.reset_sleep('test')
        self.assertTrue(result['verified'])
        self.assertIn('log_write_failed', stderr.getvalue())
        self.assertNotIn('secret-path', stderr.getvalue())


class HeartbeatTests(IsolatedGuardCase):
    def setUp(self):
        super().setUp()
        patch.object(guard, 'app_processes', return_value=[123]).start()
        self.beat = {'schema_version': 1, 'version': guard.VERSION, 'pid': 123,
                     'uid': os.getuid(), 'updated': 100.0,
                     'instance_id': '11111111-1111-4111-8111-111111111111',
                     'request_id': '33333333-3333-4333-8333-333333333333',
                     'executable': guard.APP, 'requested_state': 'on'}

    def read(self, **changes):
        self.beat.update(changes)
        (guard.BASE / 'app-heartbeat.json').write_text(json.dumps(self.beat))
        return guard.read_app(100)

    def test_current_matching_heartbeat_is_responsive(self):
        self.assertTrue(self.read()['responsive'])

    def test_old_future_nonfinite_and_non_numeric_time_rejected(self):
        for stamp in (79, 101.1, float('nan'), float('inf'), '100', True):
            with self.subTest(stamp=stamp):
                self.assertFalse(self.read(updated=stamp)['responsive'])

    def test_pid_uid_path_version_schema_and_instance_are_checked(self):
        changes = ({'pid': 124}, {'uid': os.getuid()+1}, {'executable': '/wrong'},
                   {'version': '0.1.0'}, {'schema_version': 0}, {'schema_version': True},
                   {'instance_id': 'invalid'}, {'request_id': 'invalid'}, {'requested_state': 'maybe'})
        for change in changes:
            saved = self.beat.copy()
            with self.subTest(change=change):
                self.assertFalse(self.read(**change)['responsive'])
            self.beat = saved

    def test_missing_truncated_and_nonobject_json_rejected(self):
        self.assertFalse(guard.read_app(100)['responsive'])
        for data in ('{', '[]', 'null'):
            (guard.BASE / 'app-heartbeat.json').write_text(data)
            self.assertFalse(guard.read_app(100)['responsive'])

    def test_multiple_app_processes_are_conflict(self):
        with patch.object(guard, 'app_processes', return_value=[123, 124]):
            result = self.read()
        self.assertTrue(result['conflict'])
        self.assertFalse(result['responsive'])


class LoopTests(IsolatedGuardCase):
    def setUp(self):
        super().setUp()
        self.observe = patch.object(guard, 'observe_sleep', return_value=observation('on')).start()
        patch.object(guard, 'read_power', return_value=('battery', 80)).start()
        self.read_app = patch.object(guard, 'read_app', return_value=app()).start()
        self.controllers = patch.object(guard, 'check_controllers', return_value={
            'conflict': False, 'reason': 'no_known_conflict', 'console_uid': os.getuid(),
            'controller_count': 1, 'controllers': []}).start()
        self.reset = patch.object(guard, 'reset_sleep', return_value=reset_result()).start()
        self.write = patch.object(guard, 'write_status').start()
        self.loop = guard.GuardLoop()
        self.loop.startup = False

    def cycle(self):
        return self.loop.cycle(now=100, monotonic=50)

    def test_schema_identity_and_remaining_are_present(self):
        status = self.cycle()
        self.assertEqual(status['schema_version'], 2)
        self.assertEqual(status['version'], guard.VERSION)
        self.assertEqual(status['uid'], os.getuid())
        self.assertEqual(status['script_path'], str((ROOT / 'scripts/guard.py').resolve()))
        self.assertEqual(status['remaining_seconds'], 7200)
        self.assertEqual(status['health'], 'healthy')
        self.reset.assert_not_called()

    def test_startup_resets_and_never_resumes(self):
        self.loop.startup = True
        status = self.cycle()
        self.reset.assert_called_once_with('guard_startup')
        self.assertIsNone(status['session'])
        self.assertEqual(status['observation']['state'], 'off')

    def test_reset_failure_retained_when_later_initial_sample_is_off(self):
        self.loop.startup = True
        self.reset.return_value = reset_result(False)
        first = self.cycle()
        self.assertEqual(first['health'], 'fault')
        self.observe.return_value = observation('off')
        second = self.cycle()
        self.assertFalse(second['last_reset']['verified'])
        self.assertEqual(second['health'], 'fault')
        self.assertEqual(self.reset.call_count, 2)
        self.reset.return_value = reset_result(True)
        third = self.cycle()
        self.assertTrue(third['last_reset']['verified'])
        self.assertEqual(third['health'], 'healthy')
        self.cycle()
        self.assertEqual(self.reset.call_count, 3)

    def test_expired_heartbeat_with_live_process_stops_session(self):
        self.read_app.return_value = app(False)
        status = self.cycle()
        self.reset.assert_called_once_with('app_heartbeat_invalid')
        self.assertTrue(status['app_running'])
        self.assertFalse(status['app_responsive'])
        self.assertEqual(status['health'], 'fault')

    def test_instance_change_ends_old_session(self):
        self.cycle()
        self.read_app.return_value = app(instance='22222222-2222-4222-8222-222222222222')
        status = self.cycle()
        self.reset.assert_called_once_with('app_instance_changed')
        self.assertIsNone(status['session'])

    def test_no_app_request_cannot_adopt_external_on(self):
        for requested in ('none', 'off'):
            self.read_app.return_value = dict(app(), requested_state=requested)
            self.cycle()
        self.assertEqual(self.reset.call_count, 2)

    def test_completed_request_cannot_silently_resume(self):
        self.cycle()
        self.observe.return_value = observation('off')
        self.cycle()
        self.observe.return_value = observation('on')
        self.assertEqual(self.cycle()['reason'], 'completed_request_cannot_resume')
        self.read_app.return_value = dict(app(), request_id='44444444-4444-4444-8444-444444444444')
        self.assertIsNotNone(self.cycle()['session'])

    def test_status_disk_full_forces_off_without_extra_retry_round(self):
        self.write.side_effect = OSError(errno.ENOSPC, 'secret-path')
        with contextlib.redirect_stderr(io.StringIO()) as stderr:
            status = self.cycle()
        self.reset.assert_called_once_with('status_write_failed')
        self.assertEqual(status['health'], 'fault')
        self.assertIsNone(status['session'])
        self.assertNotIn('secret-path', stderr.getvalue())
        self.loop.startup = True
        self.reset.reset_mock()
        with contextlib.redirect_stderr(io.StringIO()):
            self.cycle()
        self.reset.assert_called_once_with('guard_startup')

    def test_unknown_snapshot_and_failed_readback_remain_fault(self):
        self.observe.return_value = observation('unknown')
        self.reset.return_value = dict(reset_result(False), observation=observation('unknown'))
        status = self.cycle()
        self.assertEqual(status['observation']['state'], 'unknown')
        self.assertEqual(status['health'], 'fault')

    def test_duplicate_process_conflict_never_guards(self):
        self.read_app.return_value = dict(app(False), conflict=True, error='multiple_app_processes')
        status = self.cycle()
        self.assertEqual(status['health'], 'conflict')
        self.assertIsNone(status['session'])

    def test_multiuser_or_controller_conflict_stops_session(self):
        self.controllers.return_value = {'conflict': True, 'reason': 'controller_conflict'}
        status = self.cycle()
        self.assertEqual(status['health'], 'conflict')
        self.assertIsNone(status['session'])
        self.reset.assert_called_once_with('controller_conflict')

    def test_unknown_controller_status_fails_closed(self):
        self.controllers.return_value = {'conflict': None, 'reason': 'controller_diagnostics_unavailable'}
        status = self.cycle()
        self.assertEqual(status['health'], 'fault')
        self.assertIsNone(status['session'])
        self.reset.assert_called_once_with('controller_diagnostics_unavailable')


class StorageTests(IsolatedGuardCase):
    def test_duplicate_lock_does_not_touch_power_or_status(self):
        owner = guard.acquire_lock()
        try:
            self.assertIsNotNone(owner)
            self.assertIsNone(guard.acquire_lock())
            self.command.assert_not_called()
            self.assertFalse((guard.BASE / 'status.json').exists())
        finally:
            owner.close()
        successor = guard.acquire_lock()
        self.assertIsNotNone(successor)
        successor.close()

    def test_atomic_status_written_as_valid_json(self):
        guard.write_status({'schema_version': 2, 'health': 'fault'})
        self.assertEqual(json.loads((guard.BASE / 'status.json').read_text())['health'], 'fault')
        self.assertFalse((guard.BASE / 'status.tmp').exists())


class FullCycleTests(IsolatedGuardCase):
    def setUp(self):
        super().setUp()
        patch.object(guard, 'read_power', return_value=('battery', 80)).start()
        patch.object(guard, 'read_app', return_value=app()).start()
        patch.object(guard, 'check_controllers', return_value={
            'conflict': False, 'reason': 'no_known_conflict'}).start()
        self.loop = guard.GuardLoop()

    def test_status_contains_action_readback_not_pre_action_snapshot(self):
        self.command.side_effect = [(0, 'SleepDisabled 1'), (0, ''), (0, 'SleepDisabled 0')]
        result = self.loop.cycle(now=100, monotonic=50)
        stored = json.loads((guard.BASE / 'status.json').read_text())
        self.assertEqual(stored['observation']['state'], 'off')
        self.assertEqual(stored['last_reset']['observation'], stored['observation'])
        self.assertTrue(result['last_reset']['verified'])
        self.assertEqual(self.command.call_count, 3)

    def test_failed_reset_plus_failed_storage_remains_bounded(self):
        self.command.side_effect = [(0, 'SleepDisabled 1'),
                                    (1, ''), (0, 'SleepDisabled 1'),
                                    (1, ''), (0, 'SleepDisabled 1')]
        with patch.object(guard, 'write_status', side_effect=OSError(errno.ENOSPC, 'full')), \
             contextlib.redirect_stderr(io.StringIO()):
            result = self.loop.cycle(now=100, monotonic=50)
        self.assertFalse(result['last_reset']['verified'])
        self.assertEqual(result['health'], 'fault')
        self.assertEqual(self.command.call_count, 5)
        mutations = [call.args[0] for call in self.command.call_args_list if call.args[0][0] == '/usr/bin/sudo']
        self.assertEqual(mutations, [guard.RESET_COMMAND, guard.RESET_COMMAND])



if __name__ == '__main__':
    unittest.main()
