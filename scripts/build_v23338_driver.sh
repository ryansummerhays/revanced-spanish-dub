#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/patch_v23338_episode_evidence_identity.py scripts/audit_v23338_episode_evidence_identity.py

python3 - <<'PY'
from pathlib import Path
p = Path('scripts/build_v23337_driver.sh')
src = p.read_text(encoding='utf-8')

# Ensure the v38 scripts are syntax checked by the inherited driver too.
old = "  scripts/patch_v23337_two_level_identity.py scripts/audit_v23337_two_level_identity.py\n\npython3 - <<'PY'"
new = "  scripts/patch_v23337_two_level_identity.py scripts/audit_v23337_two_level_identity.py \\\n  scripts/patch_v23338_episode_evidence_identity.py scripts/audit_v23338_episode_evidence_identity.py\n\npython3 - <<'PY'"
if src.count(old) != 1:
    raise SystemExit('v23338 driver: compile anchor mismatch')
src = src.replace(old, new, 1)

# Insert v38 after the complete v37 source transformation and before Gradle.
old = "python3 scripts/patch_v23337_two_level_identity.py upstream .\\npython3 scripts/audit_v23337_two_level_identity.py upstream\\n\\n(\\n  cd upstream\\n"
new = "python3 scripts/patch_v23337_two_level_identity.py upstream .\\npython3 scripts/audit_v23337_two_level_identity.py upstream\\npython3 scripts/patch_v23338_episode_evidence_identity.py upstream .\\npython3 scripts/audit_v23338_episode_evidence_identity.py upstream\\n\\n(\\n  cd upstream\\n"
if src.count(old) != 1:
    raise SystemExit('v23338 driver: pre-build v37 anchor mismatch')
src = src.replace(old, new, 1)

# Final source audit should assert v38, not merely v37.
old = "python3 scripts/audit_v23327_neural_payload_source.py upstream\\npython3 scripts/audit_v23337_two_level_identity.py upstream\\n\\nrm -rf dist && mkdir -p dist\\n"
new = "python3 scripts/audit_v23327_neural_payload_source.py upstream\\npython3 scripts/audit_v23338_episode_evidence_identity.py upstream\\n\\nrm -rf dist && mkdir -p dist\\n"
if src.count(old) != 1:
    raise SystemExit('v23338 driver: post-build audit anchor mismatch')
src = src.replace(old, new, 1)

# Only rename deliverables/expected runtime markers; keep v37 patch filenames intact.
src = src.replace('youtube-v23337-source-compiled.mpe', 'youtube-v23338-source-compiled.mpe')
src = src.replace('patches-v23337-classes.dex', 'patches-v23338-classes.dex')
src = src.replace('spanish-dub-v23337-source-build-NOT-INSTALL.mpp', 'spanish-dub-v23338-source-build-NOT-INSTALL.mpp')
src = src.replace(
    'Spanish Dub Study v2.33.37 two-level acoustic-profile + human-identity diagnostics',
    'Spanish Dub Study v2.33.38 provisional-human + episode-evidence identity diagnostics')
src = src.replace(
    'speakerLiveMode=eres2net-two-level-acoustic-human-identity-v23337',
    'speakerLiveMode=eres2net-episode-evidence-human-identity-v23338')

# Add hard runtime-string gates for the new architecture.
needle = "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveSameHumanRawTransitions='\\n"
if needle not in src:
    raise SystemExit('v23338 driver: runtime grep anchor missing')
src = src.replace(needle, needle
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveIdentityPolicy=provisional-human-first;merge-requires-repeated-must-link+zero-cannot-link'\\n"
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveAdmissionPolicy=symmetric-human-admission-no-inventory-penalty'\\n"
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveConfirmedHumans='\\n"
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveProvisionalHumans='\\n"
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveStyleMergeCommitted='\\n"
    + "strings dist/youtube-v23338-source-compiled.mpe | grep 'speakerLiveTurnBoundaryEvidence='\\n", 1)

Path('/tmp/build_v23338_driver_from_v37.sh').write_text(src, encoding='utf-8')
PY
chmod +x /tmp/build_v23338_driver_from_v37.sh
exec /tmp/build_v23338_driver_from_v37.sh
