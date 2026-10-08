"""Mocked diagnostics tests; never inspect the host or change power settings."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SPEC = importlib.util.spec_from_file_location('diagnostics_under_test',
    Path(__file__).resolve().parents[1] / 'scripts/diagnostics.py')
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)
APP = '/Users/example/Applications/SleeplessCN.app/Contents/MacOS/SleeplessCN'
BASE_PS = '100 501 ' + APP + '\n200 501 /usr/bin/caffeinate\n'


class ControllerTests(unittest.TestCase):
    def check(self, ps=BASE_PS, who='example console Oct 7 10:00\n', console=501,
              failures=None, args=None, expected_pid=100):
        failures = failures or {}
        args = args or {}
        calls = []

        def command(argv):
            calls.append(argv)
            if argv[0] in failures:
                return failures[argv[0]], ''
            if argv == ['/usr/bin/who']:
                return 0, who
            if argv == ['/bin/ps', '-axo', 'pid=,uid=,comm=']:
                return 0, ps
            if argv[:2] == ['/bin/ps', '-p']:
                return args.get(int(argv[2]), (1, ''))
            raise AssertionError('unexpected observation')

        with patch.object(d.os, 'getuid', return_value=501), \
             patch.object(d.os, 'stat', side_effect=console if isinstance(console, Exception) else None,
                          return_value=SimpleNamespace(st_uid=console)), \
             patch.object(d, 'command', side_effect=command):
            result = d.controller_check(APP, expected_pid)
        self.calls = calls
        return result

    def test_expected_app_and_caffeinate_are_not_conflict(self):
        r = self.check()
        self.assertIs(r['conflict'], False)
        self.assertEqual(r['reason'], 'no_known_conflict')
        self.assertEqual(r['controller_count'], 1)

    def test_does_not_return_usernames_or_paths(self):
        r = self.check(who='private-name console Oct 7 10:00\n')
        self.assertNotIn('private-name', json.dumps(r))
        self.assertNotIn('/Users/', json.dumps(r))

    def test_console_mismatch(self):
        self.assertEqual(self.check(console=502)['reason'], 'console_user_mismatch')

    def test_multiple_console_users(self):
        self.assertEqual(self.check(who='one console date\ntwo console date\n')['reason'],
                         'multiple_console_users')

    def test_repeated_console_row_is_not_multiple_users(self):
        self.assertIs(self.check(who='one console date\none console date\n')['conflict'], False)

    def test_terminal_users_are_not_console_users(self):
        self.assertIs(self.check(who='one console date\ntwo ttys000 date\n')['conflict'], False)

    def test_empty_who_unknown(self):
        self.assertIsNone(self.check(who='')['conflict'])

    def test_invalid_who_unknown(self):
        self.assertIsNone(self.check(who='malformed')['conflict'])

    def test_stat_failure_unknown(self):
        self.assertEqual(self.check(console=OSError('private path'))['reason'], 'console_stat_failed')

    def test_who_failure_unknown(self):
        self.assertIsNone(self.check(failures={'/usr/bin/who': 1})['conflict'])

    def test_ps_failure_unknown(self):
        self.assertIsNone(self.check(failures={'/bin/ps': 1})['conflict'])

    def test_invalid_and_empty_ps_unknown(self):
        for text in ('', 'pid uid comm', '12 invalid comm'):
            with self.subTest(text=text):
                self.assertIsNone(self.check(ps=text)['conflict'])

    def test_known_app_path_with_spaces(self):
        r = self.check(ps=BASE_PS + '333 501 /Applications/Personal Tools/Amphetamine.app/Contents/MacOS/Amphetamine\n')
        self.assertIs(r['conflict'], True)
        self.assertEqual(r['controllers'][-1], {'pid':333, 'uid':501, 'name':'Amphetamine'})

    def test_known_controller_other_uid(self):
        self.assertIs(self.check(ps=BASE_PS + '333 502 /Applications/Sleepless.app/Contents/MacOS/Sleepless\n')['conflict'], True)

    def test_expected_path_other_uid(self):
        self.assertIs(self.check(ps='100 502 ' + APP)['conflict'], True)

    def test_duplicate_expected_app(self):
        self.assertEqual(self.check(ps=BASE_PS+'101 501 '+APP)['reason'], 'multiple_app_instances')

    def test_expected_pid_missing(self):
        self.assertEqual(self.check(expected_pid=900)['reason'], 'expected_app_mismatch')

    def test_cli_without_running_app_is_no_known_conflict(self):
        self.assertIs(self.check(ps='200 501 /usr/bin/caffeinate', expected_pid=None)['conflict'], False)

    def test_other_user_guard_exact_path(self):
        r = self.check(ps=BASE_PS + '300 502 /usr/bin/python3', args={300:(0,
            '/usr/bin/python3 /Users/another person/Library/Application Support/SleeplessCN/guard.py\n')})
        self.assertIs(r['conflict'], True)
        self.assertEqual(r['controllers'][-1]['name'], 'SleeplessCN Guard')
        self.assertNotIn('another person', json.dumps(r))

    def test_other_python_unrelated_or_path_inside_code_not_controller(self):
        for args in ('/usr/bin/python3 /tmp/guard.py',
                     '/usr/bin/python3 -c "/Users/person/Library/Application Support/SleeplessCN/guard.py"'):
            with self.subTest(args=args):
                self.assertIs(self.check(ps=BASE_PS+'300 502 /usr/bin/python3',
                                        args={300:(0,args)})['conflict'], False)

    def test_same_user_python_arguments_not_requested(self):
        self.check(ps=BASE_PS+'300 501 /usr/bin/python3')
        self.assertEqual(len(self.calls), 2)

    def test_other_user_python_query_failure_unknown(self):
        self.assertIsNone(self.check(ps=BASE_PS+'300 502 /usr/bin/python3')['conflict'])

    def test_explicit_conflict_takes_precedence_over_failed_observation(self):
        self.assertIs(self.check(console=502, failures={'/bin/ps':1})['conflict'], True)


class AssertionsTests(unittest.TestCase):
    def test_empty_and_unrecognized_output_unknown(self):
        for text in ('', 'unexpected format'):
            self.assertFalse(d.parse_assertions(text)['available'])

    def test_no_assertions_available_empty(self):
        self.assertEqual(d.parse_assertions('No assertions.')['entries'], [])
        self.assertTrue(d.parse_assertions('No assertions.')['available'])

    def test_process_type_only_sensitive_description_not_returned(self):
        text = '''Assertions status system-wide:
   pid 200(caffeinate): [0x00000001] 00:01:20 PreventUserIdleSystemSleep named: "private-token /Users/private/secret"
   pid 201(/Users/private/Meeting App): [0x00000002] 00:01:20 PreventUserIdleDisplaySleep named: "secret-meeting"
   pid 1(powerd): [0x003] 00:00:01 UserIsActive named: "mouse"
'''
        result = d.parse_assertions(text)
        self.assertTrue(result['available'])
        self.assertEqual(result['entries'], [
            {'pid':200, 'process':'caffeinate', 'type':'PreventUserIdleSystemSleep'},
            {'pid':201, 'process':'Meeting App', 'type':'PreventUserIdleDisplaySleep'}])
        for forbidden in ('private', 'secret', 'named:', 'mouse', '/Users/'):
            self.assertNotIn(forbidden, json.dumps(result))

    def test_duplicate_assertions_deduplicate(self):
        line = ' pid 1(powerd): [0x1] 00:00:01 PreventSystemSleep named: "a"\n'
        self.assertEqual(len(d.parse_assertions('Assertions status system-wide:\n'+line+line)['entries']), 1)

    def test_assertions_command_failure(self):
        with patch.object(d, 'command', return_value=(1, 'private stderr or output')):
            r = d.assertions_check()
        self.assertFalse(r['available'])
        self.assertEqual(r['exit_code'], 1)
        self.assertNotIn('private', json.dumps(r))


class CommandAndReportTests(unittest.TestCase):
    def test_command_timeout_does_not_leak_arguments(self):
        with patch.object(d.subprocess, 'run', side_effect=subprocess.TimeoutExpired(['private'],4)):
            self.assertEqual(d.command(['/usr/bin/who']), (-2,''))

    def test_command_uses_timeout_read_only_pipe_and_c_locale(self):
        with patch.object(d.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='ok')) as run:
            self.assertEqual(d.command(['/usr/bin/who']), (0,'ok'))
        self.assertEqual(run.call_args.kwargs['timeout'], 4)
        self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertEqual(run.call_args.kwargs['env']['LC_ALL'], 'C')

    def test_report_honest_unobserved_states_and_major(self):
        with patch.object(d, 'controller_check', return_value={'conflict':False}), \
             patch.object(d, 'assertions_check', return_value={'available':True, 'entries':[]}), \
             patch.object(d.platform, 'mac_ver', return_value=('27.0.1', (), 'arm64')):
            r = d.report()
        self.assertEqual(r['schema_version'], 1)
        self.assertEqual(r['compatibility'], {'macos_major':27, 'status':'not_verified'})
        self.assertEqual(r['gui_automation'], 'not_verified')
        self.assertEqual(r['task'], 'not_monitored')
        self.assertEqual(r['lock_state'], 'not_checked')
        self.assertEqual(r['network'], 'not_checked')
        self.assertEqual(r['displays'], 'not_checked')


if __name__ == '__main__':
    unittest.main()
