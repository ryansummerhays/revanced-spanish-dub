#!/usr/bin/env bash
set -euo pipefail

# Keep the proven v2.33.31-r3 Android ABI reconstruction/build chain. Apply v32's separation fix,
# then v33's identity-stabilization policy immediately before Gradle. No audio/clock hooks change.
python3 - <<'PY'
from pathlib import Path
src = Path('scripts/build_v23331_driver.sh').read_text(encoding='utf-8')
src = src.replace(
    'python3 scripts/patch_v23331_live_speaker.py upstream .',
    'python3 scripts/patch_v23331_live_speaker_r3.py upstream .', 1)

old = '''python3 scripts/patch_v23331_live_speaker_r3.py upstream .\npython3 scripts/audit_v23331_live_speaker.py upstream\n\n(\n  cd upstream\n'''
new = '''python3 scripts/patch_v23331_live_speaker_r3.py upstream .\npython3 scripts/audit_v23331_live_speaker.py upstream\npython3 scripts/patch_v23332_live_identity_collapse_fix.py upstream .\npython3 scripts/audit_v23332_live_identity_collapse_fix.py upstream\npython3 scripts/patch_v23333_identity_stabilization.py upstream .\npython3 scripts/audit_v23333_identity_stabilization.py upstream\n\n(\n  cd upstream\n'''
if src.count(old) != 1:
    raise SystemExit('v23333 driver: pre-build v31-r3 anchor mismatch')
src = src.replace(old, new, 1)

old = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23331_live_speaker.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
new = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23333_identity_stabilization.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
if src.count(old) != 1:
    raise SystemExit('v23333 driver: post-build audit anchor mismatch')
src = src.replace(old, new, 1)

src = src.replace('youtube-v23331-source-compiled.mpe', 'youtube-v23333-source-compiled.mpe')
src = src.replace('patches-v23331-classes.dex', 'patches-v23333-classes.dex')
src = src.replace('spanish-dub-v23331-source-build-NOT-INSTALL.mpp', 'spanish-dub-v23333-source-build-NOT-INSTALL.mpp')
src = src.replace('dist/patches-v23331-classes.dex', 'dist/patches-v23333-classes.dex')
src = src.replace('dist/youtube-v23331-source-compiled.mpe', 'dist/youtube-v23333-source-compiled.mpe')
src = src.replace(
    'Spanish Dub Study v2.33.31 near-live ERes2Net human-speaker diagnostics',
    'Spanish Dub Study v2.33.33 near-live ERes2Net identity-stabilization diagnostics')
src = src.replace(
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23331',
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23333')
src = src.replace(
    'speakerLiveImpressionPolicy=continuous-style-change-stays-human-and-may-add-prototype',
    'speakerLiveImpressionPolicy=high-confidence-multi-prototype-only')
needle = "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveImpressionPolicy=high-confidence-multi-prototype-only'\n"
if needle not in src:
    raise SystemExit('v23333 driver: runtime grep anchor missing')
src = src.replace(needle, needle
    + "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveIdentityPolicy=coherent-candidate-cluster+known-profile-rescue+bounded-inertia'\n"
    + "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveUnknownPolicy=uncommitted-candidate-until-human-evidence-is-stable'\n"
    + "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveCandidateRescues='\n"
    + "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveCandidateCohesionPermille='\n"
    + "strings dist/youtube-v23333-source-compiled.mpe | grep 'speakerLiveProfileFormat=label:prototypes/support'\n", 1)

Path('/tmp/build_v23333_driver_expanded.sh').write_text(src, encoding='utf-8')
PY
chmod +x /tmp/build_v23333_driver_expanded.sh
exec /tmp/build_v23333_driver_expanded.sh
