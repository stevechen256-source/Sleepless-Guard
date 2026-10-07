#!/bin/bash
# Isolated, per-UID grant. Never alters the upstream Sleepless sudoers file.
set -euo pipefail
export PATH=/usr/bin:/bin:/usr/sbin:/sbin
USER_NAME="${SLEEPLESS_USER:-${SUDO_USER:-$(id -un)}}"
if [ -z "$USER_NAME" ] || [ "$USER_NAME" = root ]; then
  echo 'Run for a regular desktop user; refusing to grant access to root.' >&2; exit 1
fi
USER_UID="$(id -u "$USER_NAME")"
case "$USER_UID" in ''|*[!0-9]*) echo 'Invalid user ID.' >&2; exit 1 ;; esac
[ "$USER_UID" -ge 500 ] || { echo 'Refusing a system account.' >&2; exit 1; }
DST="/etc/sudoers.d/sleeplesscn-$USER_UID"
MARKER="# Managed by SleeplessCN; uid=$USER_UID"
MODE="${1:-}"
case "$MODE" in ''|--yes|--revoke) ;; *) echo 'Usage: grant.sh [--yes|--revoke]' >&2; exit 1 ;; esac
if [ "$(id -u)" -ne 0 ]; then
  echo "Manage the dedicated Sleepless CN Guard grant: $DST (mode: ${MODE:-install})"
  echo "It allows only pmset -a disablesleep 0 and 1. Other applications' grants are not changed."
  if [ "$MODE" != --yes ]; then
    read -r -p 'Continue? Type y: ' reply
    [ "$reply" = y ] || { echo 'Cancelled.'; exit 1; }
  fi
  exec /usr/bin/sudo /usr/bin/env SLEEPLESS_USER="$USER_NAME" /bin/bash "$0" "${MODE:---yes}"
fi
[ ! -L "$DST" ] || { echo 'Grant destination is a symlink; refusing.' >&2; exit 1; }
if [ -e "$DST" ] && [ "$(head -n 1 "$DST")" != "$MARKER" ]; then
  echo 'Existing file is not owned by this application; refusing to overwrite or delete.' >&2; exit 1
fi
if [ "$MODE" = --revoke ]; then
  rm -f "$DST"
  /usr/sbin/visudo -c >/dev/null
  echo "Removed this application's dedicated grant. Other grants were preserved."
  exit 0
fi
[ -d /etc/sudoers.d ] || { echo 'Missing /etc/sudoers.d; no changes made.' >&2; exit 1; }
/usr/sbin/visudo -c >/dev/null
TMP="$(mktemp /private/tmp/sleeplesscn-grant.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
printf '%s\n#%s ALL=(root) NOPASSWD: /usr/bin/pmset -a disablesleep 0, /usr/bin/pmset -a disablesleep 1\n' "$MARKER" "$USER_UID" > "$TMP"
chmod 600 "$TMP"
/usr/sbin/visudo -cf "$TMP" >/dev/null
if [ -e "$DST" ]; then
  if /usr/bin/cmp -s "$TMP" "$DST"; then
    echo 'The matching grant is already installed; no file was replaced.'
    exit 0
  fi
  echo 'The existing managed grant differs; inspect it before replacing it.' >&2
  exit 1
fi
/usr/bin/install -m 0440 -o root -g wheel "$TMP" "$DST"
if ! /usr/sbin/visudo -c >/dev/null; then
  rm -f "$DST"
  echo 'Global sudoers validation failed; the just-written application grant was removed.' >&2; exit 1
fi
echo 'Grant installed and syntax validated. Keep-awake is still off.'
