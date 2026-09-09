#!/usr/bin/env bash
set -euo pipefail

python3 -m py_compile scripts/patch_v23335_badge_translation_integrity.py scripts/audit_v23335_badge_translation_integrity.py

python3 - <<'PY'
from pathlib import Path
src = Path('scripts/build_v23334_driver.sh').read_text(encoding='utf-8')

old = '''python3 scripts/patch_v23334_style_context_recovery.py upstream .\\npython3 scripts/audit_v23334_style_context_recovery.py upstream\\n\\n(\\n  cd upstream\\n'''
new = '''python3 scripts/patch_v23334_style_context_recovery.py upstream .\\npython3 scripts/audit_v23334_style_context_recovery.py upstream\\npython3 scripts/patch_v23335_badge_translation_integrity.py upstream .\\npython3 scripts/audit_v23335_badge_translation_integrity.py upstream\\n\\n(\\n  cd upstream\\n'''
if src.count(old) != 1:
    raise SystemExit('v23335 driver: v34 pre-build insertion anchor mismatch')
src = src.replace(old, new, 1)

old = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\\npython3 scripts/audit_v23334_style_context_recovery.py upstream\\n\\nrm -rf dist && mkdir -p dist\\n'''
new = '''python3 scripts/audit_v23327_neural_payload_source.py upstream\\npython3 scripts/audit_v23335_badge_translation_integrity.py upstream\\n\\nrm -rf dist && mkdir -p dist\\n'''
if src.count(old) != 1:
    raise SystemExit('v23335 driver: v34 post-build audit anchor mismatch')
src = src.replace(old, new, 1)

src = src.replace('youtube-v23334-source-compiled.mpe', 'youtube-v23335-source-compiled.mpe')
src = src.replace('patches-v23334-classes.dex', 'patches-v23335-classes.dex')
src = src.replace('spanish-dub-v23334-source-build-NOT-INSTALL.mpp', 'spanish-dub-v23335-source-build-NOT-INSTALL.mpp')
src = src.replace('dist/patches-v23334-classes.dex', 'dist/patches-v23335-classes.dex')
src = src.replace('dist/youtube-v23334-source-compiled.mpe', 'dist/youtube-v23335-source-compiled.mpe')

src = src.replace(
    'Spanish Dub Study v2.33.34 context-aware human/style identity diagnostics',
    'Spanish Dub Study v2.33.35 persistent speaker badge + translation integrity diagnostics')
src = src.replace(
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23334',
    'speakerLiveMode=eres2net-short-window-online-human-identity-v23335')
src = src.replace(
    'speakerLiveUnknownPolicy=unknown-before-false-human-split',
    'speakerLiveUnknownPolicy=visible-provisional-parent-or-explicit-unknown-before-false-human-split')

needle = "strings dist/youtube-v23335-source-compiled.mpe | grep 'speakerLiveImpressionPolicy=same-run-style-excursion+three-bridge-quarantine-before-prototype'\\n"
if needle not in src:
    raise SystemExit('v23335 driver: runtime grep insertion anchor missing')
src = src.replace(needle, needle
    + "strings dist/youtube-v23335-source-compiled.mpe | grep 'speakerLiveBadgePolicy=confirmed-A-B;provisional-A?-B?;unassigned-?;never-blank-for-live-uncertainty'\\n"
    + "strings dist/youtube-v23335-source-compiled.mpe | grep 'speakerLiveStyleBridgeMinWindows=2'\\n"
    + "strings dist/youtube-v23335-source-compiled.mpe | grep 'speakerLiveMaxPrototypesPerHuman=4'\\n"
    + "strings dist/youtube-v23335-source-compiled.mpe | grep 'OpenRouter zero-parsed-output failure'\\n"
    + "strings dist/youtube-v23335-source-compiled.mpe | grep 'OpenRouter language-guard preserve-prefix='\\n", 1)

Path('/tmp/build_v23335_driver_from_v34.sh').write_text(src, encoding='utf-8')
PY
chmod +x /tmp/build_v23335_driver_from_v34.sh
exec /tmp/build_v23335_driver_from_v34.sh
