#!/usr/bin/env bash
set -euo pipefail

# v34 is kept as normal UTF-8 source: no encoded transport, so CI can syntax-check exactly what it builds.
python3 -m py_compile scripts/patch_v23334_style_context_recovery.py scripts/audit_v23334_style_context_recovery.py

# Reuse the proven v2.33.33 reconstruction/ABI chain, then apply v34 immediately before Gradle.
# v34 deliberately does not touch the AudioTrack patch/hook or neural payload transport.
python3 - <<'PY'
from pathlib import Path
src = Path('scripts/build_v23333_driver.sh').read_text(encoding='utf-8')

old = '''python3 scripts/patch_v23333_identity_stabilization.py upstream .\npython3 scripts/audit_v23333_identity_stabilization.py upstream\n\n(\n  cd upstream\n'''
new = '''python3 scripts/patch_v23333_identity_stabilization.py upstream .\npython3 scripts/audit_v23333_identity_stabilization.py upstream\npython3 scripts/patch_v23334_style_context_recovery.py upstream .\npython3 scripts/audit_v23334_style_context_recovery.py upstream\n\n(\n  cd upstream\n'''
if src.count(old) != 1:
    raise SystemExit('v23334 driver: pre-build v33 anchor mismatch')
src = src.replace(old, new, 1)

old = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23333_identity_stabilization.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
new = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\npython3 scripts/audit_v23334_style_context_recovery.py upstream\n\nrm -rf dist && mkdir -p dist\n'''
if src.count(old) != 1:
    raise SystemExit('v23334 driver: post-build audit anchor mismatch')
src = src.replace(old, new, 1)

src = src.replace('youtube-v23333-source-compiled.mpe', 'youtube-v23334-source-compiled.mpe')
src = src.replace('patches-v23333-classes.dex', 'patches-v23334-classes.dex')
src = src.replace('spanish-dub-v23333-source-build-NOT-INSTALL.mpp', 'spanish-dub-v23334-source-build-NOT-INSTALL.mpp')
src = src.replace('dist/patches-v23333-classes.dex', 'dist/patches-v23334-classes.dex')
src = src.replace('dist/youtube-v23333-source-compiled.mpe', 'dist/youtube-v23334-source-compiled.mpe')
src = src.replace(
    'Spanish Dub Study v2.33.33 near-live ERes2Net identity-stabilization diagnostics',
    'Spanish Dub Study v2.33.34 context-aware human/style identity diagnostics')
src = src.replace(
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23333',
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23334')
src = src.replace(
    'speakerLiveImpressionPolicy=high-confidence-multi-prototype-only',
    'speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype')
src = src.replace(
    'speakerLiveIdentityPolicy=coherent-candidate-cluster+known-profile-rescue+bounded-inertia',
    'speakerLiveIdentityPolicy=human-vs-style-hypothesis+vad-boundary-evidence+known-rescue')
src = src.replace(
    'speakerLiveUnknownPolicy=uncommitted-candidate-until-human-evidence-is-stable',
    'speakerLiveUnknownPolicy=unknown-before-false-human-split')

needle = "strings dist/youtube-v23334-source-compiled.mpe | grep 'speakerLiveProfileFormat=label:prototypes/support'\n"
if needle not in src:
    raise SystemExit('v23334 driver: v33 runtime grep anchor missing')
src = src.replace(needle, needle
    + "strings dist/youtube-v23334-source-compiled.mpe | grep 'speakerLiveStyleExcursionsStarted='\n"
    + "strings dist/youtube-v23334-source-compiled.mpe | grep 'speakerLiveStylePrototypeConfirms='\n"
    + "strings dist/youtube-v23334-source-compiled.mpe | grep 'speakerLiveNewProfileBoundaryPromotions='\n"
    + "strings dist/youtube-v23334-source-compiled.mpe | grep 'OpenRouter recovery action=retry-once'\n"
    + "strings dist/youtube-v23334-source-compiled.mpe | grep 'OpenRouter recovery action=google-batch-fallback-success'\n", 1)

Path('/tmp/build_v23334_driver_expanded.sh').write_text(src, encoding='utf-8')
PY
chmod +x /tmp/build_v23334_driver_expanded.sh
exec /tmp/build_v23334_driver_expanded.sh
