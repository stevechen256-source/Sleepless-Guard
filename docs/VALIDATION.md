# Validation record and manual acceptance

Unreleased development revision: **0.2.0-dev**. Date: **2026-10-08**. Previous public baseline: `f09e0b7` / `v0.1.0-beta.1`; that release has not been replaced.

## Automated checks

- Guard self-test: **18 policy cases passed**. These cover normal-off state, unavailable app, unknown power data, the inclusive battery floor, battery and AC deadlines, unplugging, plugging in without extending a battery session, and wall/monotonic clock changes.
- Python unit suite: **95 test methods** cover policy, three-state parsing, ambiguous/missing flags, nonzero exits, timeouts and invalid encoding, reset refusal/unchanged readback, bounded retries, lost/malformed/future/expired app heartbeats, app instance changes, consumed request IDs, disk-full/state/log failures, lock conflicts, known-controller/console conflicts, assertion privacy, installation ownership and verified restoration.
- Swift suite: **48 checks** cover three-state parsing, accepted commands with wrong readbacks, old/truncated status, timestamps, UID/PID/LaunchAgent/script mismatches, guard/reset faults, unknown observations, invalid deadlines, and bounded command launch/timeout behavior.
- Python subprocess/power operations are mocked, including installer/uninstaller tests. Swift tests use synthetic protocol data plus harmless owned shell/sleep fixtures for command timeouts; they never invoke sudo, pmset, a LaunchAgent, or the application GUI.
- Shell scripts are syntax checked separately. The sudoers rule format can be validated with `visudo -cf` against an isolated temporary sample without installing it.

- The final multilingual application compiled successfully for `arm64-apple-macos26.0`; its local ad-hoc code signature passed strict verification.
- All three language tables contain the same **54 used keys**, with no missing or unused keys and matching format placeholders.
- The built executable's read-only `--localization-check` loaded English, Simplified Chinese, and Traditional Chinese as requested. An unsupported French preference fell back to English. Formatted battery percentages and countdowns were checked in each language. These checks exit before creating the GUI or invoking power commands.

No automated check in this document should be interpreted as a physical lid test or a successful installation on another user's computer.

## What remains unverified

- A full real installation and removal of this published derivative with its new identifiers and authorization filename.
- GUI layout, permission prompts, login toggles, and all three UI languages during actual use.
- Physical close/reopen-lid behavior on battery and AC power with this derivative.
- Real battery depletion, long-duration 2/12-hour sessions, heat, travel, reboot, and macOS upgrades.
- Intel Macs, older macOS releases, desktops, and multi-user concurrent sessions.

The allowed macOS 26/27 major-version check is an explicit evaluation boundary, not certification. Pure tests for failures, process identity and power switching are not hardware acceptance. The prior approximately one-minute lid observation did not validate screenshots/clicks or an actual sign-in task and was not an isolated power test.

The earlier local predecessor's guard policy had 18 passing checks, and its abnormal-app-exit cleanup was exercised on one development Mac. That evidence does not establish end-to-end acceptance of this portable derivative. The published version changes app identity, installation paths, authorization isolation, and language resources.

## Manual acceptance on your Mac

Use a disposable task and keep the computer open and ventilated until the ordinary controls work. Do not conduct tests while carrying it in a bag.

1. Inspect `./install.sh --dry-run`. Install, open the app, and confirm keep-awake is off and GUI login launch is off.
2. Start a short noncritical task on AC power. Enable the switch and verify `pmset -g` reports `SleepDisabled 1`.
3. End the session and verify `SleepDisabled 0`. Confirm that this allows sleep without forcibly sleeping the Mac.
4. Enable, then quit normally. Repeat once with an app crash simulation only after you understand the guard behavior. Check that the flag returns to `0`; retain power and keep the lid open during this step.
5. Start on AC and unplug. Verify that the AC session ends. Deliberately start a new battery session with sufficient charge and check ordinary switch/timer behavior.
6. After these checks, close the lid for about one minute with the disposable task running, then reopen. Check actual task progress. Repeat for the power source you intend to use. Do not infer success merely from the menu-bar switch.
7. End the session before packing up. Choose Apple menu → Sleep and confirm it actually sleeps. Check for independent meeting/video/display assertions if it does not.
8. Test GUI launch-at-login separately; it must show the app without automatically enabling keep-awake. Inspect System Settings → Login Items if macOS requires approval.
9. Test the uninstaller before relying on the package for long-term use. Check that this app's files and UID-specific grant are removed while other applications' files remain.
10. Confirm all three status rows and warning states in each UI language. In a disposable test environment, remove the scoped grant and verify that command failure, UNKNOWN readback, and failed recovery never display success. Restore only that test grant afterwards.
11. Separately test screen off, external-display mode, lock screen, real sleep, and network loss. If GUI automation matters, test a harmless screenshot and click using the actual chosen task runner and verify its result. A cup icon or `SleepDisabled=1` is not acceptance.

If any step fails, stop depending on closed-lid operation and report a minimal, redacted reproduction. Use the recovery command in [SECURITY.md](../SECURITY.md) when normal sleep needs to be restored.
