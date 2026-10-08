# Sleepless Guard

**A multilingual macOS keep-awake utility with an independent exit guard, battery limits, and explicit opt-in sessions.**

Keep a local AI job or another long-running task active when you intentionally close your MacBook. Keep display sleep available. Return to ordinary sleep behavior when the session ends, the app exits, or the battery needs protection.

This is an independent derivative of [Aboudjem/Sleepless](https://github.com/Aboudjem/Sleepless) by Adam Boudjemaa, based on **v1.2.7**. The menu-bar application supports **English, Simplified Chinese, and Traditional Chinese**, following the system language. English is the main documentation language; a [Simplified Chinese guide](README.zh-CN.md) is available. See [NOTICE.md](NOTICE.md) for attribution.

> **Unreleased development revision — 0.2.0-dev.** This branch improves observed state and failure reporting; the published `v0.1.0-beta.1` release is unchanged. Clean installation/removal, full GUI acceptance, and physical close/reopen-lid tests remain pending. Build and mocked tests do not establish successful closed-lid automation.

## What the status actually means

The popover separates **App request**, **macOS readback (ON / OFF / UNKNOWN)**, and **Guard status**. A successful command is verified by a second `pmset` read. An empty, malformed, failed, or missing readback is **UNKNOWN**, never OFF. A failure remains visible in the status, notification, and diagnostic code; an orange warning replaces the ordinary active indicator.

The guard uses a versioned status protocol, verifies a main-run-loop app heartbeat, and records every reset's exit code, bounded attempt count, and post-action observation. The app checks the guard's schema, UID, LaunchAgent PID, interpreter/script identity, freshness, and reset outcome. A stale, reused, mismatched, or faulted heartbeat cannot enable a session. See [the state protocol](docs/STATE_PROTOCOL.md).

**Keep-awake is not proof of a usable desktop or a completed task.** This project does not schedule AI tasks, wake a sleeping Mac, capture screenshots, send clicks, manage website sessions, or bypass lock screens, passwords, CAPTCHA, Passkeys, or MFA. The screen, desktop/login, network, and actual automation must be validated separately. Lock/login and network state are deliberately labeled **not checked**; task completion is **not verified**.

The **Checks** button opens a read-only, scrollable preflight report with app/guard versions, observed power state, display count, diagnostic codes, and observed sleep/display assertion types with process names and PIDs. Display count does not prove capture is available. The report's separate **Request normal sleep** button explicitly requests OFF and verifies it. A CLI version is available with `python3 scripts/diagnostics.py`; it does not make network requests or end other applications.

## What it does

- A native menu-bar switch explicitly starts and ends a keep-awake session.
- A separate user-level guard polls power and application state. It can **only turn keep-awake off**.
- Battery sessions are limited to **2 hours** and stop at **30%** battery or below. The app's battery floor can be raised to 50%.
- AC sessions are limited to **12 hours**. Unplugging power ends a session that started on AC; start a new battery session deliberately if needed.
- Optional app timers shorten a session to **1 or 2 hours**. “Default” means the guard's limits still apply.
- Normal app exit requests sleep restoration. If the app crashes, the independent guard observes its absence and requests restoration.
- The guard starts again after a crash and requests restoration before monitoring. It never restores a previous keep-awake session.
- GUI launch at login is optional and off by default. The guard runs at login once installed.
- No account, analytics, cloud service, runtime downloads, or subscription. Project price: **¥0 CNY**. MIT licensed.

The normal polling interval is 5 seconds. Command timeouts, OS scheduling, or failures can delay a response. Each guard reset round makes at most two OFF attempts and reads back after each attempt; later rounds may retry a persistent failure. The previous failure remains until restoration is verified. A completed request cannot silently resume; a new explicit switch action generates a new request ID. Both the app timer and guard deadline contribute to the visible remaining time.

## Understand the system-level behavior

This tool uses `pmset -a disablesleep 1`, the same undocumented macOS switch used by upstream. It affects **system sleep globally**, including ordinary lid-close sleep. It does not create a virtual display or change display resolution. The guard restores `disablesleep 0`; it does not alter your display timeout or keep the panel lit with a display assertion.

Turning the switch off **allows normal sleep; it does not immediately put the computer to sleep**. Applications such as meeting software can independently keep the display or Mac awake. This utility does not override those applications.

Do not run it alongside another controller of `disablesleep`, including another Sleepless installation. The global flag has no owner, so one controller can undo another controller's choice. The separate application and authorization files prevent accidental file removal, not conflicting system commands.

The guard conservatively ends its session when it observes another known controller, a different console user, multiple console users, or an unknown controller check. Detection covers known process identities, not all possible writers of this global switch. External assertions, including `caffeinate`, are listed for diagnosis; they are never automatically terminated.

**Never put a running MacBook in a closed bag.** Keep ventilation clear, check the workload, and manually choose Apple menu → Sleep before packing up. There is **no temperature-sensor monitor or thermal shutdown feature in this project**. Battery and elapsed-time limits are useful safeguards, not a guarantee against heat, data loss, or a stuck operating system.

## Requirements

- An **Apple Silicon MacBook**. The compile target is `arm64-apple-macos26.0`. The app currently admits macOS major versions **26 and 27** for local evaluation, with **hardware/GUI acceptance still pending**; other major versions refuse new sessions until revalidated. Intel Macs and multi-user operation are not supported by this development revision.
- Apple's **Command Line Tools**, including `swiftc`, `codesign`, and `/usr/bin/python3`.
- An administrator-authorized setup for the two exact `pmset` commands below.
- A normal logged-in desktop session for the menu bar and the per-user LaunchAgent.

No Homebrew, Xcode project, or third-party Python package is required. Install Command Line Tools if necessary:

```sh
xcode-select --install
```

## Build and install

Download the source or clone this repository, then inspect the installation plan:

```sh
git clone https://github.com/stevechen256-source/Sleepless-Guard.git
cd Sleepless-Guard
git switch improve-observed-state  # unreleased development branch
./install.sh --dry-run
```

The dry run does not build, install, invoke `sudo`, start an application, or change sleep settings. The real installation is explicit:

```sh
./install.sh
```

The script builds locally with an **ad-hoc signature**, asks before installing its dedicated administrator grant, installs the app and guard for the current user, and checks for a guard heartbeat. It does **not** start a keep-awake session or open the GUI. Do not run the whole installer with `sudo`.

The beta is not Developer ID signed or notarized. Do not disable Gatekeeper or System Integrity Protection. Build from source you have reviewed.

Open the installed app when ready:

```sh
open "$HOME/Applications/SleeplessCN.app"
```

Click its coffee-cup menu icon, choose a timer if appropriate, and enable the switch. Before depending on it, run the [manual acceptance checklist](docs/VALIDATION.md) on your own Mac with a disposable task.

For a build only, with no install or system changes:

```sh
./build.sh
```

The generated app requires the installed guard before its switch can enable keep-awake.

## Languages

The app ships with **English (`en`), Simplified Chinese (`zh-Hans`), and Traditional Chinese (`zh-Hant`)**. It follows macOS's preferred application/system languages, with English as the fallback for unsupported languages. Relaunch the app after changing its language in macOS settings. Terminal installation messages and primary documentation are in English.

Translations live in `locales/<language>.lproj/Localizable.strings`. Each locale includes the same 54 keys, including UNKNOWN and failure states; preserve `%d`, `%@`, and `%%` format markers when contributing a translation. `InfoPlist.strings` localizes the app's display name. Adding a language also requires adding it to `CFBundleLocalizations` in `Info.plist`; the build copies all `.lproj` resource folders automatically.

After building, this read-only command checks language selection without starting the GUI or changing sleep settings:

```sh
build/SleeplessCN.app/Contents/MacOS/SleeplessCN --localization-check -AppleLanguages '(zh-Hant)'
```

## Installed files and permission scope

| Item | Location or identity |
| --- | --- |
| App | `~/Applications/SleeplessCN.app` |
| Bundle identifier | `io.github.sleeplesscn.app` |
| Guard and local status | `~/Library/Application Support/SleeplessCN/` |
| User LaunchAgent | `~/Library/LaunchAgents/io.github.sleeplesscn.guard.plist` |
| Dedicated authorization | `/etc/sudoers.d/sleeplesscn-<numeric-user-id>` |

The grant permits the current user to run exactly these commands as root without another password prompt:

```text
/usr/bin/pmset -a disablesleep 0
/usr/bin/pmset -a disablesleep 1
```

It does not grant an arbitrary shell or unrestricted `pmset`. Any process already running as that user can use these two commands while the grant exists. See [SECURITY.md](SECURITY.md).

The installer refuses pre-existing destinations. For this beta, uninstall the prior **Sleepless Guard** copy before reinstalling; there is no automatic upgrade or migration. Original Sleepless installations are not replaced, and their shared authorization file is never removed by this project. Internal filenames retain the `SleeplessCN` prefix to keep this derivative distinct from upstream.

## Stop, recover, and uninstall

Use the menu switch or **Quit and allow sleep** to end a session. To request normal sleep behavior from Terminal:

```sh
./restore-sleep.sh
```

This recovery command does not immediately sleep the Mac. To pack the computer away, choose **Apple menu → Sleep** after ending the session and verify it is no longer running.

Uninstall from the source directory:

```sh
./uninstall.sh --dry-run
./uninstall.sh
```

The uninstaller validates its ownership markers, restores normal sleep, unregisters its GUI login item, quits this app, stops its guard, and removes its own app, known support files, LaunchAgent, and per-user grant. It preserves unexpected files in the support directory and leaves upstream/other applications' grants alone. If it cannot restore sleep or the app will not quit, it stops instead of reporting a clean removal. UserDefaults may remain as harmless local preferences.

Keep the source directory until uninstall is complete. If you have manually removed or altered installation files, see the recovery notes in [SECURITY.md](SECURITY.md).

## Test and contribute

```sh
/usr/bin/python3 scripts/guard.py --self-test
/usr/bin/python3 -m unittest discover -s tests -v
mkdir -p build
swiftc -parse-as-library PowerState.swift tests/PowerStateTests.swift -o build/power-state-tests
build/power-state-tests
```

These tests exercise decisions, input parsing, and installation ownership rules without writing power settings or running a real installer. Build verification and the limits of prior testing are recorded in [docs/VALIDATION.md](docs/VALIDATION.md).

There is no scheduler or task-completion API. Time limits start when the guard observes an explicit active session, not at a future AI task's start time. Expiry can interrupt a task; task failure does not automatically end an otherwise valid session. A brief unplug ends an AC session and plugging back in does not renew it. Do not expect an overnight wait to fit beyond the 2-hour battery or 12-hour AC hard cap.

Bug reports should include macOS version, chip family, power source, and reproduction steps. Remove usernames, home-directory paths, machine identifiers, tokens, and private application logs before posting. Please do not upload an entire system diagnostic bundle.

## License

[MIT](LICENSE). Original Sleepless copyright © 2026 Adam Boudjemaa. This software is provided **as is, without warranty**. See [NOTICE.md](NOTICE.md) for the upstream baseline and the derivative's scope.
