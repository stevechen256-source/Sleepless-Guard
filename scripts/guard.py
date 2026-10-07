#!/usr/bin/python3
"""Fail-safe companion to Sleepless CN Guard. No network or display control.
Only privileged operation: the exact pmset -a disablesleep 0 grant.
The guard NEVER enables sleep prevention. The app remains the explicit switch.
"""
import atexit
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

BASE = Path.home() / 'Library/Application Support/SleeplessCN'
APP = str(Path.home() / 'Applications/SleeplessCN.app/Contents/MacOS/SleeplessCN')
BATTERY_FLOOR = 30
POLL_SECONDS = 5

def command(args):
    try:
        env = dict(os.environ, LC_ALL='C', LANG='C')
        r = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True,
                           text=True, timeout=4, env=env)
        return r.returncode, r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return -1, ''

def read_state():
    code, text = command(['/usr/bin/pmset', '-g'])
    m = re.search(r'SleepDisabled\s+([01])', text)
    disabled = bool(int(m[1])) if code == 0 and m else None
    code, text = command(['/usr/bin/pmset', '-g', 'batt'])
    source = 'ac' if "'AC Power'" in text else 'battery' if "'Battery Power'" in text else 'unknown'
    m = re.search(r'(\d+)%;', text)
    percent = int(m[1]) if code == 0 and m else -1
    code, text = command(['/bin/ps', '-axo', 'comm='])
    running = code == 0 and APP in [line.strip() for line in text.splitlines()]
    return disabled, source, percent, running

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
    path = BASE / 'events.log'
    if path.exists() and path.stat().st_size > 128 * 1024:
        path.replace(BASE / 'events.previous.log')
    with path.open('a') as f:
        f.write(time.strftime('%Y-%m-%d %H:%M:%S%z ') + message + '\n')

def reset_sleep(reason):
    code, _ = command(['/usr/bin/sudo', '-n', '/usr/bin/pmset', '-a', 'disablesleep', '0'])
    log('reset=' + str(code == 0) + ' reason=' + reason)
    return code == 0

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
    BASE.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = (BASE / 'guard.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    atexit.register(reset_sleep, 'guard exit')
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda *_: sys.exit(0))
    reset_sleep('guard startup; never resume a previous session')
    session = None
    previous = None
    while True:
        try:
            state = read_state()
            reset, session, reason = decision(*state[:3], state[3], session, time.time(), time.monotonic())
            if reset:
                reset_sleep(reason)
            elif reason != previous:
                log(reason)
            previous = reason
            status = {'updated': time.time(), 'pid': os.getpid(), 'reason': reason, 'sleep_disabled_observed': state[0],
                      'source': state[1], 'battery_percent': state[2], 'app_running': state[3],
                      'session': session}
            temp = BASE / 'status.tmp'
            temp.write_text(json.dumps(status, indent=2))
            temp.replace(BASE / 'status.json')
        except Exception as e:
            reset_sleep('guard exception ' + type(e).__name__)
            session = None
        time.sleep(POLL_SECONDS)

if __name__ == '__main__':
    if sys.argv[1:] == ['--self-test']:
        self_test()
    else:
        main()
