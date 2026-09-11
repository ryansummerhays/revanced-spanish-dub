#!/usr/bin/env python3
from pathlib import Path
import sys
root = Path(sys.argv[1] if len(sys.argv) > 1 else 'upstream')
live = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java'
controller = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java'
sherpa = root / 'extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java'
s = live.read_text()
c = controller.read_text()
sh = sherpa.read_text()
required = [
    'v2.33.45 calibrated-neighborhood speaker identity tracker.',
    'private static final int STAT_MAX_MODES = 64;',
    'private static final float STAT_CALIBRATION_MIN_SEED = 0.34f;',
    'speakerIdentityAuthority=calibrated-neighborhood-statistical-v23345',
    'speakerStatCrossEpisodePolicy=disjoint-group-affinity+calibrated-neighborhood-clustering;each-group-at-most-once-per-mode-pair',
    'speakerStatSeedPolicy=empirical-gap-neighborhood-edge;singleton-bootstrap-stricter;established-cluster-needs-multiple-member-support;recomputed-and-reversible',
    'speakerStatAdaptiveModeReuseFloorPermille=',
    'speakerStatAdaptiveBootstrapFloorPermille=',
    'speakerStatAdaptiveNegativeCeilingPermille=',
    'speakerStatCalibratedNeighborhoodEdges=',
    'speakerStatBootstrapSupportEdges=',
    'speakerStatPairVetoEdges=',
    'speakerStatClusterSupportedMerges=',
    'statCalibrationPositiveLower >= statCalibrationNegativeUpper + 0.080f',
    'float fromPositive = statCalibrationPositiveLower - 0.050f;',
    'float fromNegative = statCalibrationNegativeUpper + 0.080f;',
    'statAdaptiveModeReuseFloor = calibratedGap',
    'boolean calibratedNeighborhood = matched >= 1',
    'boolean singletonPair = sizeA == 1 && sizeB == 1;',
    '|| (!singletonPair && seed >= 2);',
    'if (sizeA == 1 && sizeB == 1) return vetoEdges >= 1;',
    'return vetoEdges >= 2;',
    'int bestHuman = best < STAT_MODE_HUMAN.length ? STAT_MODE_HUMAN[best] : -1;',
    'decisionMargin = bestScore - otherHumanBest;',
    'chunked-continuation-reuses-group-and-is-structural-must-link',
    'raw-within-clean-episode-measurement-positive+turn-separated-negative',
]
missing=[x for x in required if x not in s]
if missing:
    raise SystemExit('missing v45 markers: ' + repr(missing))
if 'adaptive-reciprocal-nearest-with-margin-or-adaptive-very-strong' in s:
    raise SystemExit('old reciprocal-nearest policy marker remains')
if 'Spanish Dub Study v2.33.45 calibrated neighborhood statistical speaker identity diagnostics' not in c:
    raise SystemExit('controller diagnostics version missing')
for marker, haystack in [
    ('postwrite-return-value+threadlocal-prewrite-buffer-reference+advanced-position', sh),
    ('stateful-biquad-antialias+rational-phase+accepted-slice-sample-provenance', s),
    ('central+two-overlapping-context-probes-majority;not-independent-votes', s),
]:
    if marker not in haystack:
        raise SystemExit('preservation marker missing: ' + marker)
print('v2.33.45 calibrated-neighborhood source audit PASS')
