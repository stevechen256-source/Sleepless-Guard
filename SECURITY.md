# Security and operational limits

Sleepless Guard changes one global macOS power flag. It is a local convenience tool, not a security boundary, a workload scheduler, a thermal controller, or a guarantee of uninterrupted execution.

## Privilege model

The menu-bar app and Python guard run as the logged-in user. The only passwordless privilege is the two fully specified commands `pmset -a disablesleep 0` and `pmset -a disablesleep 1`. The guard invokes only the `0` command. The app invokes `1` only in response to the user's switch, after checking a recent guard heartbeat. All command calls use argument arrays; the one native authorization command shell-quotes its user and script path.

`grant.sh` writes a separately named file for the user's numeric UID. It validates the existing file's ownership marker, refuses symlink destinations, validates the generated rule with `visudo`, installs it as `root:wheel` with mode `0440`, then validates the full sudoers configuration. It refuses system accounts and does not modify `/etc/sudoers` or another tool's authorization file.

The grant is a permission for the **user**, not only this app. Other software running as the same user can invoke those exact two commands. A person who can already modify your user-owned app or scripts can affect their behavior; administrator credentials and the OS remain part of the trust boundary.

## Global-state conflicts

`disablesleep` has no per-application ownership. Guard startup, app quit, error recovery, and uninstall request `disablesleep 0`. These actions may cancel a session created by another tool. Do not operate multiple controllers at the same time, including upstream Sleepless or another logged-in user's controller. The original upstream `/etc/sudoers.d/sleepless-disablesleep` file is intentionally never removed. Its continued presence may still authorize `pmset` after this derivative is uninstalled.

There is no continuous privileged root daemon and no networking code in the guard. The guard runs once per logged-in user via LaunchAgent and writes local status, timestamps, power percentage, and short event reasons. Local log files are not meant for publication. The event log is rotated around 128 KiB; OS/Python errors may also appear in the local launch/error logs.

## Failure behavior

The guard requests normal sleep if the app disappears, the power status cannot be read, battery charge reaches 30%, the session deadline arrives, or an AC-started session is unplugged. It also resets the flag when it starts or receives a normal termination signal. `SIGKILL` cannot run cleanup; launchd is expected to restart the guard, whose startup resets the flag. These are best-effort mechanisms dependent on scheduling, working permissions, a functioning OS, and an enabled LaunchAgent.

This does not add temperature monitoring, disk protection, battery-health prediction, lid sensors, or guaranteed screen darkness. Another application may hold its own display assertion. End the task and verify sleep before carrying the Mac in a bag. The undocumented `disablesleep` behavior can change with macOS updates.

## Recovery

Run `./restore-sleep.sh`, or request the same change directly:

```sh
sudo /usr/bin/pmset -a disablesleep 0
```

This allows normal sleep; it does not immediately sleep the computer. If a leftover process keeps enabling the setting, quit the keep-awake applications before repeating the recovery command. Do not remove a guard's authorization while relying on it for cleanup.

The uninstaller aborts if ownership checks or sleep restoration fail. Inspect that error instead of using broad recursive deletion or removing shared sudoers files. If the installation was changed manually, preserve unrelated files and restore the original source checkout before retrying. If you need to edit sudoers manually, use `visudo` and remove only the exact UID-specific file created by this project after normal sleep has been restored.

## Reporting a problem

For ordinary bugs, open a GitHub issue containing a minimal reproduction and redacted diagnostics. Do not include passwords, API keys, home-directory paths, private reports, vaults, backups, or full system logs. For a security-sensitive finding, use a private reporting channel if the repository provides one; otherwise open an issue asking for a private contact without exposing exploit details or personal data.
