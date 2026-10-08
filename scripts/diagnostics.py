#!/usr/bin/python3
"""Read-only, privacy-limited diagnostics. Importing performs no observations.

Known-controller detection is a conservative check, not proof that no other
software changes the global power flag. No command here changes system state.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time

VERSION = '0.2.0-dev'
APP = str(Path.home() / 'Applications/SleeplessCN.app/Contents/MacOS/SleeplessCN')
CONTROLLER_NAMES = frozenset(('Sleepless', 'SleeplessCN', 'Amphetamine'))
BLOCKING_TYPES = frozenset(('PreventUserIdleSystemSleep', 'PreventSystemSleep',
                            'PreventUserIdleDisplaySleep', 'NoDisplaySleepAssertion',
                            'PreventDiskIdle'))


def command(args):
    """Never return stderr, exception text or command arguments to a report."""
    try:
        result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, timeout=4,
                                env=dict(os.environ, LC_ALL='C', LANG='C'))
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        return -2, ''
    except (OSError, UnicodeError):
        return -1, ''


def _parse_processes(text):
    result = []
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.strip().split(None, 2)
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit():
            raise ValueError('invalid_process_output')
        result.append((int(fields[0]), int(fields[1]), fields[2]))
    if not result:
        raise ValueError('empty_process_output')
    return result


def _is_guard_path(path):
    # Fixed installed location only: a random script named guard.py is unrelated.
    return re.fullmatch(r'/Users/[^/\r\n]+/Library/Application Support/SleeplessCN/guard\.py', path) is not None


def _other_user_guard(args):
    # ps args does not quote paths with spaces. Accept the exact installed script
    # as the sole Python argument; do not match a path inside -c code or flags.
    match = re.fullmatch(r'\s*(?:\S*/)?python(?:3(?:\.\d+)?)?\s+(/Users/[^/\r\n]+/Library/Application Support/SleeplessCN/guard\.py)\s*', args, re.IGNORECASE)
    return match is not None


def controller_check(expected_app_path, expected_pid=None):
    """Return true=conflict, false=no *known* conflict, None=observation unknown.

    Names and numeric IDs only leave this function. Full paths, usernames and
    process arguments are used internally and are never included in the result.
    Other-user Python argv is inspected only to recognize the exact installed
    guard script; arbitrary scripts and same-user Python are not inspected.
    """
    current_uid = os.getuid()
    result = {'conflict': None, 'reason': 'observation_unknown', 'console_uid': None,
              'controller_count': 0, 'controllers': []}
    problems = []
    unknown = []
    try:
        result['console_uid'] = os.stat('/dev/console').st_uid
        if result['console_uid'] != current_uid:
            problems.append('console_user_mismatch')
    except OSError:
        unknown.append('console_stat_failed')

    code, who = command(['/usr/bin/who'])
    if code:
        unknown.append('who_command_failed')
    else:
        users = set()
        invalid = False
        for line in who.splitlines():
            fields = line.split()
            if fields and len(fields) < 2:
                invalid = True
            elif len(fields) >= 2 and fields[1] == 'console':
                users.add(fields[0])
        if len(users) > 1:
            problems.append('multiple_console_users')
        if invalid or not users:
            unknown.append('who_output_invalid')

    code, text = command(['/bin/ps', '-axo', 'pid=,uid=,comm='])
    processes = None
    if code:
        unknown.append('ps_command_failed')
    else:
        try:
            processes = _parse_processes(text)
        except ValueError:
            unknown.append('ps_output_invalid')
    if processes is not None:
        expected = []
        extra_probes = 0
        probe_deadline = time.monotonic() + 4
        for pid, uid, path in processes:
            name = Path(path).name
            is_guard = _is_guard_path(path) and uid != current_uid
            if uid != current_uid and re.fullmatch(r'python(?:3(?:\.\d+)?)?', name, re.IGNORECASE):
                if extra_probes >= 4 or time.monotonic() >= probe_deadline:
                    unknown.append('controller_probe_budget_exceeded')
                else:
                    extra_probes += 1
                    code, args = command(['/bin/ps', '-p', str(pid), '-o', 'args='])
                    if code or not args.strip():
                        unknown.append('guard_process_unknown')
                    else:
                        is_guard = _other_user_guard(args)
            if name not in CONTROLLER_NAMES and not is_guard:
                continue
            result['controllers'].append({'pid': pid, 'uid': uid,
                                          'name': 'SleeplessCN Guard' if is_guard else name})
            if not is_guard and path == str(expected_app_path) and uid == current_uid:
                expected.append(pid)
            else:
                problems.append('other_controller_detected')
        if len(expected) > 1:
            problems.append('multiple_app_instances')
        if expected_pid is not None and expected != [expected_pid]:
            problems.append('expected_app_mismatch')
    result['controller_count'] = len(result['controllers'])
    if problems:
        result.update(conflict=True, reason=problems[0])
    elif unknown:
        result.update(conflict=None, reason=unknown[0])
    else:
        result.update(conflict=False, reason='no_known_conflict')
    return result


def parse_assertions(text):
    """Extract only PID, sanitized process basename and blocking assertion type."""
    if not text.strip() or not re.search(r'Assertions status system-wide:|No assertions\.', text):
        return {'available': False, 'entries': [], 'error': 'assertions_output_invalid'}
    entries = []
    seen = set()
    for line in text.splitlines():
        match = re.match(r'\s*pid\s+(\d+)\(([^)\r\n]+)\):\s+\S+\s+\S+\s+(\w+)\b', line)
        if not match or match[3] not in BLOCKING_TYPES:
            continue
        name = Path(match[2]).name
        name = re.sub(r'[^\w .+\-]', '_', name)[:80]
        key = (int(match[1]), name, match[3])
        if key not in seen:
            seen.add(key)
            entries.append({'pid': key[0], 'process': name, 'type': key[2]})
    return {'available': True, 'entries': entries, 'error': None}


def assertions_check():
    code, text = command(['/usr/bin/pmset', '-g', 'assertions'])
    if code:
        return {'available': False, 'entries': [], 'error': 'assertions_command_failed',
                'exit_code': code}
    return dict(parse_assertions(text), exit_code=0)


def report(expected_app_path=APP):
    version = platform.mac_ver()[0]
    major = int(version.split('.')[0]) if version and version.split('.')[0].isdigit() else None
    return {'schema_version': 1, 'app_version': VERSION,
            'compatibility': {'macos_major': major, 'status': 'not_verified'},
            'controllers_check': controller_check(expected_app_path),
            'assertions': assertions_check(), 'gui_automation': 'not_verified',
            'task': 'not_monitored', 'lock_state': 'not_checked',
            'network': 'not_checked', 'displays': 'not_checked'}


def main():
    parser = argparse.ArgumentParser(description='Print read-only, privacy-limited JSON diagnostics.')
    parser.parse_args()
    print(json.dumps(report(), ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
