# Validation record and manual acceptance

Release candidate: **v0.1.0-beta.1**. Date: **2026-10-07**.

## Automated checks

- Guard self-test: **18 policy cases passed**. These cover normal-off state, unavailable app, unknown power data, the inclusive battery floor, battery and AC deadlines, unplugging, plugging in without extending a battery session, and wall/monotonic clock changes.
- Python unit suite: **26 test methods passed**. These cover the policy, power-output parsing, timeouts, failed reset reporting, distinct app identity, path handling, ownership checks, destination conflicts, symlink rejection, and aborting removal when sleep restoration fails.
- Installer and uninstaller dry-run tests do not execute external commands. All subprocess/power operations in unit tests are mocked.
- Shell scripts are syntax checked separately. The sudoers rule format can be validated with `visudo -cf` against an isolated temporary sample without installing it.

- The final multilingual application compiled successfully for `arm64-apple-macos26.0`; its local ad-hoc code signature passed strict verification.
- All three language tables contain the same **27 used keys**, with no missing or unused keys and matching format placeholders.
- The built executable's read-only `--localization-check` loaded English, Simplified Chinese, and Traditional Chinese as requested. An unsupported French preference fell back to English. Formatted battery percentages and countdowns were checked in each language. These checks exit before creating the GUI or invoking power commands.

No automated check in this document should be interpreted as a physical lid test or a successful installation on another user's computer.

## What remains unverified

- A full real installation and removal of this published derivative with its new identifiers and authorization filename.
- GUI layout, permission prompts, login toggles, and all three UI languages during actual use.
- Physical close/reopen-lid behavior on battery and AC power with this derivative.
- Real battery depletion, long-duration 2/12-hour sessions, heat, travel, reboot, and macOS upgrades.
- Intel Macs, older macOS releases, desktops, and multi-user concurrent sessions.

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

If any step fails, stop depending on closed-lid operation and report a minimal, redacted reproduction. Use the recovery command in [SECURITY.md](../SECURITY.md) when normal sleep needs to be restored.
