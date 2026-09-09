#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/patch_v23336_streaming_context.py scripts/audit_v23336_streaming_context.py \
  scripts/patch_v23337_two_level_identity.py scripts/audit_v23337_two_level_identity.py

python3 - <<'PY'
from pathlib import Path
src = Path('scripts/build_v23331_driver.sh').read_text(encoding='utf-8')
src = src.replace(
    'python3 scripts/patch_v23331_live_speaker.py upstream .',
    'python3 scripts/patch_v23331_live_speaker_r3.py upstream .', 1)

old = '''python3 scripts/patch_v23331_live_speaker_r3.py upstream .\npython3 scripts/audit_v23331_live_speaker.py upstream\n\n(\n  cd upstream\n'''
new = '''python3 scripts/patch_v23331_live_speaker_r3.py upstream .\npython3 scripts/audit_v23331_live_speaker.py upstream\npython3 scripts/patch_v23332_live_identity_collapse_fix.py upstream .\npython3 scripts/audit_v23332_live_identity_collapse_fix.py upstream\npython3 scripts/patch_v23333_identity_stabilization.py upstream .\npython3 scripts/audit_v23333_identity_stabilization.py upstream\npython3 scripts/patch_v23334_style_context_recovery.py upstream .\npython3 scripts/audit_v23334_style_context_recovery.py upstream\npython3 scripts/patch_v23335_badge_translation_integrity.py upstream .\npython3 scripts/audit_v23335_badge_translation_integrity.py upstream\npython3 scripts/patch_v23336_streaming_context.py upstream .\npython3 scripts/audit_v23336_streaming_context.py upstream\npython3 scripts/patch_v23337_two_level_identity.py upstream .\npython3 scripts/audit_v23337_two_level_identity.py upstream\n\n(\n  cd upstream\n'''
if src.count(old) != 1:
    raise SystemExit('v23337 driver: pre-build v31-r3 anchor mismatch')
src = src.replace(old, new, 1)

old = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23331_live_speaker.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
new = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23337_two_level_identity.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
if src.count(old) != 1:
    raise SystemExit('v23337 driver: post-build audit anchor mismatch')
src = src.replace(old, new, 1)

src = src.replace('youtube-v23331-source-compiled.mpe', 'youtube-v23337-source-compiled.mpe')
src = src.replace('patches-v23331-classes.dex', 'patches-v23337-classes.dex')
src = src.replace('spanish-dub-v23331-source-build-NOT-INSTALL.mpp', 'spanish-dub-v23337-source-build-NOT-INSTALL.mpp')
src = src.replace('dist/patches-v23331-classes.dex', 'dist/patches-v23337-classes.dex')
src = src.replace('dist/youtube-v23331-source-compiled.mpe', 'dist/youtube-v23337-source-compiled.mpe')
src = src.replace(
    'Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics',
    'Spanish Dub Study v2.33.37 two-level acoustic-profile + human-identity diagnostics')
src = src.replace(
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23331',
    'speakerLiveMode=eres2net-two-level-acoustic-human-identity-v23337')
src = src.replace(
    'speakerLiveImpressionPolicy=continuous-style-change-stays-human-and-may-add-prototype',
    'speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype')

needle = "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype'\n"
if needle not in src:
    raise SystemExit('v23337 driver: runtime grep anchor missing')
src = src.replace(needle, needle
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveArchitecture=raw-acoustic-profile-cache->persistent-human-map'\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveIdentityPolicy=raw-voice-state-is-not-a-person'\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveHumans='\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveAcousticProfilesLinkedToExistingHuman='\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveSameHumanRawTransitions='\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'speakerLiveAdjacentComparisons='\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'OpenRouter zero-parsed-output failure'\n"
    + "strings dist/youtube-v23337-source-compiled.mpe | grep 'OpenRouter language-guard preserve-prefix='\n", 1)

Path('/tmp/build_v23337_driver_expanded.sh').write_text(src, encoding='utf-8')
PY
chmod +x /tmp/build_v23337_driver_expanded.sh
exec /tmp/build_v23337_driver_expanded.sh
