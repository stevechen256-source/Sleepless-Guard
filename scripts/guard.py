#!/usr/bin/python3
"""Fail-safe companion to Sleepless CN Guard. No network or display control.
Only privileged operation: the exact pmset -a disablesleep 0 grant.
The guard NEVER enables sleep prevention. The app remains the explicit switch.
"""
import atexit
import fcntl
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
import uuid

try:
    from diagnostics import controller_check
except ImportError:
    controller_check = None

BASE = Path.home() / 'Library/Application Support/SleeplessCN'
APP = str(Path.home() / 'Applications/SleeplessCN.app/Contents/MacOS/SleeplessCN')
BATTERY_FLOOR = 30
POLL_SECONDS = 5
VERSION = '0.2.0-dev'
SCHEMA_VERSION = 2
LAUNCH_AGENT = 'io.github.sleeplesscn.guard'
HEARTBEAT_MAX_AGE = 20
RESET_COMMAND = ['/usr/bin/sudo', '-n', '/usr/bin/pmset', '-a', 'disablesleep', '0']

def command(args):
    try:
        env = dict(os.environ, LC_ALL='C', LANG='C')
        r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=4, env=env)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return -1, ''

def observe_sleep():
    """A failed command or ambiguous output is UNKNOWN, never OFF."""
    code, text = command(['/usr/bin/pmset', '-g'])
    flags = [line.split() for line in text.splitlines()
             if line.split() and line.split()[0].lower() == 'sleepdisabled']
    error = 'pmset_command_failed' if code else None
    if not error and (len(flags) != 1 or len(flags[0]) != 2 or flags[0][1] not in ('0', '1')):
        error = 'pmset_output_invalid'
    return {'state': ('on' if flags[0][1] == '1' else 'off') if not error else 'unknown',
            'exit_code': code, 'error': error, 'sampled_at': time.time()}


def read_power():
    code, text = command(['/usr/bin/pmset', '-g', 'batt'])
    if code:
        return 'unknown', -1
    source = 'ac' if "'AC Power'" in text else 'battery' if "'Battery Power'" in text else 'unknown'
    m = re.search(r'(\d+)%;', text)
    percent = int(m[1]) if m else -1
    return source, percent if 0 <= percent <= 100 else -1


def app_processes():
    code, text = command(['/bin/ps', '-axo', 'pid=,uid=,comm='])
    if code:
        return []
    matches = []
    for line in text.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            if int(fields[1]) == os.getuid() and fields[2] == APP:
                matches.append(int(fields[0]))
    return matches


def read_app(now):
    """Heartbeat comes from the App's main runloop, not merely a live PID."""
    pids = app_processes()
    result = {'running': bool(pids), 'responsive': False, 'instance_id': None,
              'request_id': None,
              'requested_state': 'none', 'error': 'app_missing', 'conflict': len(pids) > 1,
              'pid': pids[0] if len(pids) == 1 else None}
    if len(pids) != 1:
        if pids:
            result['error'] = 'multiple_app_processes'
        return result
    result['error'] = 'app_heartbeat_invalid'
    try:
        path = BASE / 'app-heartbeat.json'
        if path.stat().st_size > 16384:
            return result
        beat = json.loads(path.read_text())
        if not isinstance(beat, dict):
            return result
        stamp = beat.get('updated')
        valid_time = (type(stamp) in (int, float) and math.isfinite(stamp)
                      and -1 <= now - stamp <= HEARTBEAT_MAX_AGE)
        valid = (type(beat.get('schema_version')) is int and beat['schema_version'] == 1
                 and beat.get('version') == VERSION
                 and type(beat.get('uid')) is int and beat['uid'] == os.getuid()
                 and type(beat.get('pid')) is int and beat['pid'] == pids[0]
                 and beat.get('executable') == APP and valid_time
                 and beat.get('requested_state') in ('none', 'on', 'off')
                 and isinstance(beat.get('instance_id'), str)
                 and isinstance(beat.get('request_id'), str))
        if not valid:
            return result
        uuid.UUID(beat['instance_id'])
        uuid.UUID(beat['request_id'])
        result.update(responsive=True, instance_id=beat['instance_id'], error=None,
                      request_id=beat['request_id'], requested_state=beat['requested_state'])
    except (OSError, ValueError, TypeError, OverflowError):
        pass
    return result


def read_state():
    """Compatibility helper for the pure policy API; the loop uses full observations."""
    observation = observe_sleep()
    source, percent = read_power()
    disabled = {'on': True, 'off': False, 'unknown': None}[observation['state']]
    return disabled, source, percent, bool(app_processes())

def decision(disabled, source, percent, running, session, now, monotonic):
    if disabled is False:
        return False, None, 'normal sleep allowed'
    if disabled is None:
        return True, None, 'cannot verify global sleep flag'
    if not running:
        return True, None, 'Sleepless exited or unavailable'
    if source not in ('ac', 'battery') or not 0 <= percent <= 100:
        return True, None, 'power status unknown'
    if source == 'battery' and percent <= BATTERY_FLOOR:
        return True, None, 'battery at or below 30 percent'
    if session is None:
        session = {'source': source, 'start': now, 'monotonic': monotonic,
                   'limit': 7200 if source == 'battery' else 43200}
    if session['source'] == 'ac' and source == 'battery':
        return True, None, 'charger removed; AC session ended'
    elapsed = max(now - session['start'], monotonic - session['monotonic'])
    if elapsed < 0 or elapsed >= session['limit']:
        return True, None, 'session time limit reached or clock invalid'
    return False, session, 'guarding ' + session['source'] + ' session'

def log(message):
    try:
        path = BASE / 'events.log'
        if path.exists() and path.stat().st_size > 128 * 1024:
            path.replace(BASE / 'events.previous.log')
        with path.open('a') as f:
            f.write(time.strftime('%Y-%m-%d %H:%M:%S%z ') + message + '\n')
    except OSError:
        # Never echo command stderr, exception paths, or heartbeat content.
        print('Sleepless Guard: log_write_failed', file=sys.stderr)


def safe_log(message):
    try:
        log(message)
    except Exception:
        print('Sleepless Guard: log_write_failed', file=sys.stderr)

def reset_sleep(reason):
    """At most two attempts per round, each followed by an independent readback."""
    requested = time.time()
    for attempt in (1, 2):
        code, _ = command(RESET_COMMAND)
        observation = observe_sleep()
        verified = code == 0 and observation['state'] == 'off'
        error = None if verified else ('reset_command_failed' if code else
                                       'reset_readback_' + observation['state'])
        result = {'requested_at': requested, 'exit_code': code, 'error': error,
                  'verified': verified, 'observation': observation, 'attempts': attempt}
        if verified:
            break
    safe_log('reset_verified=' + str(verified) + ' reason=' + reason +
             ' error=' + str(error) + ' exit_code=' + str(code))
    return result


def write_status(status):
    temp = BASE / 'status.tmp'
    temp.write_text(json.dumps(status, indent=2, allow_nan=False))
    temp.replace(BASE / 'status.json')


def check_controllers(app):
    if controller_check is not None:
        try:
            result = controller_check(APP, expected_pid=app.get('pid'))
            if (isinstance(result, dict) and 'conflict' in result
                    and type(result['conflict']) in (bool, type(None))
                    and isinstance(result.get('reason'), str)):
                return result
        except Exception:
            pass
    return {'conflict': None, 'reason': 'controller_diagnostics_unavailable',
            'console_uid': None, 'controller_count': 0, 'controllers': []}


class GuardLoop:
    """One injectable iteration; construction never executes any power command."""
    def __init__(self):
        self.session = None
        self.last_reset = None
        self.previous_reason = None
        self.startup = True
        self.consumed_request = None

    def cycle(self, now=None, monotonic=None):
        now = time.time() if now is None else now
        monotonic = time.monotonic() if monotonic is None else monotonic
        observation = observe_sleep()
        source, percent = read_power()
        app = read_app(now)
        request_id = app.get('request_id')
        controllers = check_controllers(app)
        disabled = {'on': True, 'off': False, 'unknown': None}[observation['state']]
        reset, session, reason = decision(disabled, source, percent, app['responsive'],
                                          self.session, now, monotonic)
        pending_failure = self.last_reset is not None and not self.last_reset['verified']
        if self.startup:
            reset, session, reason = True, None, 'guard_startup'
            self.startup = False
        elif pending_failure:
            reset, session, reason = True, None, 'retry_unverified_reset'
        elif app['conflict']:
            reset, session, reason = True, None, 'multiple_app_processes'
        elif controllers['conflict'] is not False:
            reset, session, reason = True, None, controllers['reason']
        elif observation['state'] == 'on':
            if not app['responsive']:
                reset, session, reason = True, None, app['error']
            elif self.session and self.session.get('instance_id') != app['instance_id']:
                reset, session, reason = True, None, 'app_instance_changed'
            elif app['requested_state'] != 'on':
                reset, session, reason = True, None, 'no_app_on_request'
            elif request_id is not None and self.consumed_request == request_id:
                reset, session, reason = True, None, 'completed_request_cannot_resume'
        if observation['state'] == 'off' and self.session is not None:
            self.consumed_request = request_id
        if reset:
            if app['responsive'] and app['requested_state'] == 'on':
                self.consumed_request = request_id
            self.last_reset = reset_sleep(reason)
            observation = self.last_reset['observation']
            session = None
        if session is not None:
            session['instance_id'] = app['instance_id']
        self.session = session
        health = 'healthy'
        if (observation['state'] == 'unknown' or source not in ('ac', 'battery') or not 0 <= percent <= 100 or
                (self.last_reset is not None and not self.last_reset['verified'])):
            health = 'fault'
        elif app['running'] and not app['responsive']:
            health, reason = 'fault', app['error']
        if app['conflict']:
            health = 'conflict'
        if controllers['conflict'] is True:
            health, reason = 'conflict', controllers['reason']
        elif controllers['conflict'] is None:
            health, reason = 'fault', controllers['reason']
        remaining = None
        if session:
            remaining = max(0, session['limit'] - max(now - session['start'],
                                                     monotonic - session['monotonic']))
        status = {'schema_version': SCHEMA_VERSION, 'version': VERSION, 'updated': time.time(),
                  'pid': os.getpid(), 'uid': os.getuid(), 'launch_agent': LAUNCH_AGENT,
                  'executable': sys.executable, 'script_path': str(Path(__file__).resolve()),
                  'observation': observation, 'source': source, 'battery_percent': percent,
                  'app_running': app['running'], 'app_responsive': app['responsive'],
                  'health': health, 'reason': reason, 'remaining_seconds': remaining,
                  'last_reset': self.last_reset, 'session': session,
                  'controller_diagnostics': controllers}
        if reason != self.previous_reason:
            safe_log(reason)
            self.previous_reason = reason
        try:
            write_status(status)
        except (OSError, ValueError, TypeError):
            # A fresh status cannot reach the App. Stop immediately, even if event logging fails.
            self.session = None
            if not reset:
                self.consumed_request = request_id
                self.last_reset = reset_sleep('status_write_failed')
            status.update(health='fault', reason='status_write_failed', session=None,
                          remaining_seconds=None, last_reset=self.last_reset,
                          observation=self.last_reset['observation'])
            print('Sleepless Guard: status_write_failed', file=sys.stderr)
        return status


def acquire_lock():
    lock = (BASE / 'guard.lock').open('a')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return None
    return lock

def self_test():
    n, m = 100000.0, 20000.0
    cases = 0
    def check(expected, *args):
        nonlocal cases
        result = decision(*args)
        assert result[0] is expected, (expected, args, result)
        cases += 1
        return result
    check(False, False, 'battery', 80, False, None, n, m)
    check(True, None, 'ac', 80, True, None, n, m)
    check(True, True, 'ac', 80, False, None, n, m)
    check(True, True, 'unknown', 80, True, None, n, m)
    check(True, True, 'battery', -1, True, None, n, m)
    check(True, True, 'battery', 30, True, None, n, m)
    check(True, True, 'battery', 5, True, None, n, m)
    _, b, _ = check(False, True, 'battery', 31, True, None, n, m)
    check(False, True, 'battery', 80, True, b, n+7199, m+7199)
    check(True, True, 'battery', 80, True, b, n+7200, m+7200)
    check(True, True, 'battery', 80, True, b, n-100, m+7200)
    check(True, True, 'battery', 80, True, b, n+7200, m+1)
    _, a, _ = check(False, True, 'ac', 80, True, None, n, m)
    check(True, True, 'battery', 80, True, a, n+1, m+1)
    check(False, True, 'ac', 80, True, a, n+43199, m+43199)
    check(True, True, 'ac', 80, True, a, n+43200, m+43200)
    check(False, True, 'ac', 80, True, b, n+600, m+600)
    check(True, True, 'ac', 80, True, b, n+7200, m+7200)
    print('PASS', cases, 'policy cases; no system settings changed')

def main():
    os.umask(0o077)
    try:
        BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = acquire_lock()
    except OSError:
        reset_sleep('guard_storage_unavailable')
        return
    if lock is None:
        # The active owner alone operates power state; duplicate startup must not interrupt it.
        print('Sleepless Guard: lock_already_held', file=sys.stderr)
        return
    atexit.register(reset_sleep, 'guard exit')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))
    loop = GuardLoop()
    while True:
        try:
            loop.cycle()
        except Exception:
            loop.last_reset = reset_sleep('guard_exception')
            loop.session = None
            print('Sleepless Guard: guard_exception', file=sys.stderr)
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        main()
