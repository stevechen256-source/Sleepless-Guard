#!/bin/bash
# Explicit recovery; this allows sleep but does NOT immediately put the Mac to sleep.
set -euo pipefail
/usr/bin/sudo -n /usr/bin/pmset -a disablesleep 0
if ! sleep_snapshot="$(/usr/bin/pmset -g)"; then
  echo 'The request ran, but reading the system state failed. Sleep is not verified.' >&2
  exit 1
fi
if ! /usr/bin/awk 'tolower($1)=="sleepdisabled" { count++; valid=(NF==2 && $2=="0") } END { exit !(count==1 && valid) }' <<< "$sleep_snapshot"; then
  echo 'The request ran, but OFF was not verified. Inspect the grant and diagnostics.' >&2
  exit 1
fi
echo 'Verified SleepDisabled=0. Other applications may still prevent sleep; the Mac has not been put to sleep.'
