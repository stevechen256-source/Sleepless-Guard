#!/bin/bash
# Explicit recovery; this allows sleep but does NOT immediately put the Mac to sleep.
set -euo pipefail
/usr/bin/sudo /usr/bin/pmset -a disablesleep 0
echo 'Requested normal sleep behavior. This command does not immediately put the Mac to sleep.'
/usr/bin/pmset -g | /usr/bin/grep -i SleepDisabled || true
