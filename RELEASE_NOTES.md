# Unreleased — 0.2.0-dev

- Separate app requests, three-state macOS observations, and guard health; read back every power-setting request before reporting verification.
- Versioned guard/app heartbeats with live identity checks, app responsiveness, retained reset failures, bounded retries, and consumed request IDs.
- Read-only external-assertion/controller diagnostics, explicit automation limits, and visible guard deadlines in all three languages.
- Installation, removal and manual recovery require OFF readback; grants and protection are retained if restoration cannot be verified.
- 95 Python tests, 18 guard policy cases, 48 Swift checks, and build/localization checks pass. Clean installation/removal, GUI layout and physical-lid/task acceptance are still pending.

This development work has not replaced the existing release or the locally installed predecessor. There is no scheduling, task API, or GUI automation runtime.

# v0.1.0-beta.1 — first source beta

Sleepless Guard is an independent MIT-licensed derivative of Aboudjem/Sleepless v1.2.7, with English, Simplified Chinese, and Traditional Chinese controls and an independent guard for explicit keep-awake sessions.

- Battery sessions end after two hours or at 30% charge; AC sessions end after twelve hours or when unplugged.
- App exit and guard restart request normal sleep. No previous session is automatically resumed.
- Separate application identifiers, a per-user installer, and UID-specific sudoers authorization avoid replacing the upstream installation or deleting its grant.
- A fresh guard heartbeat is required to enable keep-awake. No account, runtime network service, or paid subscription is required.

This release distributes source. Build locally on Apple Silicon with macOS 26+ and Apple Command Line Tools. The application is ad-hoc signed, not Developer ID signed or notarized. Full GUI acceptance and a physical lid-close test of this published derivative remain pending. See `docs/VALIDATION.md` and `SECURITY.md` before depending on it.
