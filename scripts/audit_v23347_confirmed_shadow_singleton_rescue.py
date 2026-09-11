#!/usr/bin/env python3
from pathlib import Path
import hashlib, sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'upstream')
base = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot'
files = {
    'LiveSpeakerOnline.java': '39330657f9c991d23bdeb483b52f7496dcb1c02bca1a071e2628e9a98535391b',
    'SherpaNeuralShadow.java': '2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626',
    'SpanishStudyController.java': '7c3f375bcd4c59177d1b699851956fe734d25a0538234e7416549bfca49f94c7',
}
for name, expected in files.items():
    p = base / name
    data = p.read_bytes()
    got = hashlib.sha256(data).hexdigest()
    assert got == expected, f'{name} sha mismatch: {got} != {expected}'

live = (base / 'LiveSpeakerOnline.java').read_text()
controller = (base / 'SpanishStudyController.java').read_text()
required = [
    'v2.33.47 confirmed-shadow singleton-rescue speaker identity tracker',
    'speakerIdentityAuthority=confirmed-shadow-singleton-rescue-statistical-v23347',
    'speakerStatShadowBridgePolicy=singleton-only+same-confirmed-shadow-raw-profile+prior-confirmed-stat-human+no-repeated-negative;never-bootstraps-new-human',
    'speakerStatShadowSingletonCandidates=',
    'speakerStatShadowSingletonUnions=',
    'speakerStatShadowSingletonSuppressed=',
    'private static int statConfirmedShadowRawForSpanLocked(long startMs, long endMs)',
    '!HUMAN_ACTIVE[human] || !HUMAN_CONFIRMED[human]',
    'if (singleton == null || singleton.count != 1) continue;',
    'if (b == m || rawByMode[b] != raw || !statPriorHumanConfirmedForModeLocked(b)) continue;',
    'if (statPairEvidence(STAT_DIFF_EVIDENCE, m, b) >= 2 || STAT_PAIR_NEGATIVE[idx] >= 2) continue;',
    'if (affinity < 0.20f) continue;',
    'applyConfirmedShadowSingletonRescueLocked(parent);',
    'speakerStatCalibrationPolicy=raw-within-clean-episode-measurement-positive+turn-separated-negative;no-selected-mode-split-bias;bounded-session-adaptive-floor',
]
for needle in required:
    assert needle in live, f'missing LiveSpeakerOnline marker: {needle}'
assert 'Spanish Dub Study v2.33.47 confirmed-shadow singleton-rescue statistical speaker identity diagnostics' in controller
assert 'pcmAdmission=exact-android-accepted-postwrite-slice-v23330-threadlocal-bridge' in controller
# v47 must not alter the sherpa implementation; its SHA above is the stronger byte-level check.
# Guard the safety shape: rescue happens after structural must-link and before ordinary graph merges.
struct = live.index('statStructuralGroupUnions++;')
rescue = live.index('applyConfirmedShadowSingletonRescueLocked(parent);', struct)
merge_loop = live.index('while (true) {', rescue)
assert struct < rescue < merge_loop
print('v2.33.47 confirmed-shadow singleton-rescue source audit PASS')
