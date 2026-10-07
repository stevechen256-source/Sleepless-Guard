# v0.1.0-beta.1 — first source beta

Sleepless Guard is an independent MIT-licensed derivative of Aboudjem/Sleepless v1.2.7, with English, Simplified Chinese, and Traditional Chinese controls and an independent guard for explicit keep-awake sessions.

- Battery sessions end after two hours or at 30% charge; AC sessions end after twelve hours or when unplugged.
- App exit and guard restart request normal sleep. No previous session is automatically resumed.
- Separate application identifiers, a per-user installer, and UID-specific sudoers authorization avoid replacing the upstream installation or deleting its grant.
- A fresh guard heartbeat is required to enable keep-awake. No account, runtime network service, or paid subscription is required.

This release distributes source. Build locally on Apple Silicon with macOS 26+ and Apple Command Line Tools. The application is ad-hoc signed, not Developer ID signed or notarized. Full GUI acceptance and a physical lid-close test of this published derivative remain pending. See `docs/VALIDATION.md` and `SECURITY.md` before depending on it.
