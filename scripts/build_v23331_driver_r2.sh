#!/usr/bin/env bash
set -euo pipefail
cp scripts/build_v23331_driver.sh /tmp/build_v23331_driver_r2.sh
sed -i 's#python3 scripts/patch_v23331_live_speaker.py upstream \.#python3 scripts/patch_v23331_live_speaker_r2.py upstream .#' /tmp/build_v23331_driver_r2.sh
grep -q 'patch_v23331_live_speaker_r2.py upstream' /tmp/build_v23331_driver_r2.sh
bash /tmp/build_v23331_driver_r2.sh
