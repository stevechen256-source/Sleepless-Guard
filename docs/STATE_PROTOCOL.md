# Observed state and failure protocol

Development version: `0.2.0-dev`. This is an internal local protocol, not a task scheduler or supported automation API.

## Three separate facts

1. **Request:** what this app last asked for. An ON request alone never means the operation succeeded.
2. **Observation:** a timestamped `pmset -g` sample with `state` (`on`, `off`, `unknown`), `exit_code`, and a short `error` classification. Empty output, duplicate/malformed/missing flags, nonzero exits, and timeouts are unknown. OFF allows sleep; it does not prove the Mac is asleep.
3. **Guard:** its live identity and heartbeat, app responsiveness, decision, and verified reset outcome. Failure cannot be hidden by a fresh timestamp.

Every app request is followed by a readback. Every guard reset round has at most two attempts, with a readback after each attempt. Only command exit zero **and** observed OFF is `verified`. The next cycle may retry a failed round. A failure stays in `last_reset` until a later round verifies OFF. Only fixed diagnostic classes and exit codes are persisted; command stderr is not copied into status/events.

## Guard status, schema 2

`status.json` is atomically replaced in the current user's private support directory. Fields:

| Field | Meaning |
| --- | --- |
| `schema_version`, `version` | Exact protocol and application revision |
| `updated`, `pid`, `uid` | Heartbeat timestamp and process identity |
| `launch_agent`, `executable`, `script_path` | Expected LaunchAgent label and runtime interpreter/script identities |
| `observation` | The **post-action** observation when a reset occurred |
| `source`, `battery_percent` | AC/battery/unknown and measured percentage (`-1` means unknown) |
| `app_running`, `app_responsive` | Exact-path/UID process presence and validated main-run-loop heartbeat |
| `health`, `reason` | Healthy, fault, or conflict; concise decision/failure reason |
| `remaining_seconds`, `session` | Remaining hard limit and in-memory session; absent when inactive |
| `last_reset` | Request time, exit code, error class, verified flag, post-action observation, attempts |
| `controller_diagnostics` | Known controllers, console UID, and conflict/unknown result |

The app rejects missing/truncated/old status, a heartbeat older than 30 seconds or more than one second in the future, mismatched UID/LaunchAgent/script, a missing or different live LaunchAgent PID, incorrect process arguments, failed resets, unknown observations, and nonresponsive app reports. The Python interpreter may appear via the Apple launcher or its resolved developer-tools executable.

These identity checks address stale data and PID reuse; **they do not protect against malicious code already running as the same user**. That user owns the app, scripts and state and can use the two scoped sudoers commands. Do not treat local JSON as a security boundary against that account.

## App heartbeat, schema 1

The app's main run loop atomically writes `app-heartbeat.json` every five seconds, including during modal panels. It contains `schema_version`, `version`, `pid`, `uid`, `updated`, `executable`, `instance_id`, `request_id`, and `requested_state` (`none`, `on`, `off`). A command action creates a fresh request ID. The guard validates exact process path/UID/PID and a timestamp no older than 20 seconds or more than one second in the future.

A process that exists but no longer updates this heartbeat is not responsive. App instance changes end the old session. Resetting or observing an ended session consumes its ON request; the same request cannot adopt a later external ON value. A fresh user action is required. No heartbeat, startup, restart, login event or time change automatically writes ON.

## Failure and conflict behavior

- State-file write failure requests OFF and reports a fixed error to stderr. A logging failure cannot prevent restoration attempts. Existing status becomes stale, which the app rejects.
- Duplicate guard starts are excluded by a file lock. LaunchAgent restart starts with an OFF request, not session resumption.
- Known alternative controllers or ambiguous console/controller observations end the session. Detection is conservative and incomplete; a process name is not proof of exclusive ownership. Extra foreign-Python probes are bounded in number and time.
- External sleep assertions are **observations only**. Diagnostics expose PID, process basename, and assertion type, excluding assertion text, arguments, usernames and full paths. Nothing is terminated.
- The app displays unknown/failure in a warning state and provides an explicit recovery action. Recovery and uninstall verify OFF before reporting restoration or removing protection. If verification fails, uninstall/rollback retains recovery files and the grant.

The two-hour battery, 30% floor, twelve-hour AC, and unplug rules remain unchanged. Commands and scheduling have nonzero latency, so neither polling intervals nor cutoffs are instantaneous guarantees. Keep the Mac ventilated; there is no thermal monitoring. Network access, lock-screen state, website authentication, screenshots/clicks, and task success remain unchecked or unverified. Scheduling and task APIs require a separate design and are not implemented here.
