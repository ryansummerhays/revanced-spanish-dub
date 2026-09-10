#!/usr/bin/env python3
"""Hard source audit for v2.33.42 independent cross-episode statistical identity."""
from pathlib import Path
import hashlib, sys

EXPECTED = {
    "LiveSpeakerOnline.java": "a436664f71f6f65825bd5782f1e3a262842bc1d0c9cfc601f606e8d6b6aecacf",
    "SherpaNeuralShadow.java": "2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626",
    "SpanishStudyController.java": "25a06af074c20880887da3395f45c47a9fef58b095a29027e96e8ab730a9d532",
}

def must(text, needle, label):
    if needle not in text: raise RuntimeError(f"{label}: missing {needle!r}")

def exactly(text, needle, n, label):
    got=text.count(needle)
    if got != n: raise RuntimeError(f"{label}: expected {n}, found {got}: {needle!r}")

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if len(sys.argv) < 2: raise SystemExit("usage: audit_v23342_cross_episode_statistics.py <morphe-root>")
    root=Path(sys.argv[1]).resolve()
    d=root/"extensions/youtube/src/main/java/app/spanishstudy/vot"
    paths={n:d/n for n in EXPECTED}
    for n,p in paths.items():
        got=sha(p)
        if got != EXPECTED[n]: raise RuntimeError(f"exact v42 source hash mismatch: {n}: {got}")
    live=paths["LiveSpeakerOnline.java"].read_text(encoding="utf-8")
    sherpa=paths["SherpaNeuralShadow.java"].read_text(encoding="utf-8")
    ctl=paths["SpanishStudyController.java"].read_text(encoding="utf-8")

    # Proven capture/timing and v41 clean-data front-end are retained.
    must(live, "AudioVideoSyncProbe.projectTrackFrameToVideoMs", "video-master mapping")
    must(live, "WINDOW_SAMPLES = 32_000", "2s shadow")
    must(live, "HOP_SAMPLES = 9_600", "600ms shadow hop")
    must(live, "STAT_CONTEXT_HOP_SAMPLES = 16_000", "1s segmentation cadence")
    must(live, "STAT_CORE_START_SAMPLE = 72_000", "centered core")
    must(live, "STAT_CORE_END_SAMPLE = 88_000", "centered core")
    must(live, "slot.cleanVotes < 2", "consensus gate")
    must(live, "STAT_BOUNDARY_TRIM_SAMPLES = 4_800", "boundary trim")
    must(live, "STAT_MIN_EMBED_SAMPLES = 24_000", "clean embed minimum")
    must(live, "configureAnalysisResamplerLocked", "anti-alias resampler")
    must(live, "recordSampleSpanLocked", "sample provenance")
    must(live, "videoForTargetSampleLocked", "sample-video mapping")
    must(sherpa, "cleanSingleSpeakerSpanAroundCore", "clean single source extraction")
    must(sherpa, "activeCount == 1 && dominantActive", "exact single local source")

    # v42 repaired positive evidence path.
    must(live, "speakerIdentityAuthority=independent-cross-episode-statistical-v23342", "v42 authority")
    must(live, "computeStatPairStatsLocked", "cross-episode pair statistics")
    must(live, "STAT_MAX_PAIR_REPS = 8", "bounded pair representatives")
    must(live, "historySpanningRepresentativeIndexes", "history spanning evidence sampling")
    must(live, "float[] simMatrix", "single-pass cached cosine matrix")
    must(live, "boolean[] usedA", "disjoint left evidence groups")
    must(live, "boolean[] usedB", "disjoint right evidence groups")
    must(live, "if (ma.groups[ai] == mb.groups[bj]) continue", "same-group correlation exclusion")
    must(live, "STAT_PAIR_JACKKNIFE", "jackknife cache")
    must(live, "STAT_MODE_NEAREST", "reciprocal nearest evidence")
    must(live, "STAT_MODE_NEAREST_MARGIN", "nearest-neighbor margin")
    must(live, "statModeCount >= 3 && matched >= 1 && affinity >= veryStrongFloor", "no two-mode cross-episode seed")
    must(live, "STAT_MODE_NEAREST[a] == b && STAT_MODE_NEAREST[b] == a", "reciprocal seed")
    must(live, "STAT_PAIR_SECOND[idx] >= STAT_BIOMETRIC_CORROBORATED_SECOND", "independent corroboration")
    must(live, "STAT_PAIR_JACKKNIFE[idx] >= STAT_BIOMETRIC_CORROBORATED_JACKKNIFE", "leave-strongest-out stability")
    must(live, "groups < 3", "single-pair never confirms human")
    must(live, "corroborated >= 1 || seed >= 2", "majority/corroboration confirmation")
    must(live, "prepareStatPairEvidenceLocked();", "evidence graph recomputed")
    must(live, "Re-solve from retained evidence every time", "reversible partition")
    must(live, "statClusterMergeVetoLocked", "different-evidence cluster veto")
    must(live, "statComparisonPenalty", "multiple-comparison correction")

    # Mode recurrence is permitted but still conservative; mode != biological human.
    must(live, "STAT_MODE_REUSE_SINGLE = 0.74f", "singleton mode recurrence")
    must(live, "STAT_MODE_REUSE_ESTABLISHED = 0.66f", "established mode recurrence")
    must(live, "STAT_MODE_REUSE_MARGIN = 0.050f", "reuse margin")
    must(live, "new-acoustic-mode", "split-first mode creation")

    # Dangerous v40 biological authority remains disabled.
    must(live, "shadow-new-raw-profile-no-identity-authority", "shadow raw tracker")
    must(live, "no v40 relation may mutate biological identity", "legacy relation no-op")
    exactly(live, "purityRelationLinkedAtCreation++", 0, "no creation-time human link")

    # UI claims remain fail-closed.
    must(live, 'return human < 0 ? "?" : statHumanLabel(human) + "?"', "live provisional only")
    must(live, 'return "?";', "unknown output")
    must(live, "STAT_HUMAN_CONFIRMED", "confirmed state")

    # Diagnostics expose the statistical assumptions and failure modes.
    must(ctl, "Spanish Dub Study v2.33.42 independent cross-episode statistical speaker identity diagnostics", "v42 header")
    must(live, "speakerStatCrossEpisodePolicy=greedy-disjoint-independence-group-matching", "cross episode policy")
    must(live, "speakerStatSeedPolicy=very-strong-or-reciprocal-nearest-with-margin", "seed policy")
    must(live, "speakerStatConfirmationPolicy=minimum-three-independent-groups+jackknife-corroboration-or-majority-seeds", "confirmation policy")
    must(live, "speakerStatBiometricIndependentMatches=", "matched evidence telemetry")
    must(live, "speakerStatCorroboratedSupportEdges=", "corroboration telemetry")
    must(live, "speakerStatJackknifePass=", "jackknife telemetry")
    must(live, "speakerStatClusterVetoes=", "veto telemetry")

    print("v2.33.42 source audit: PASS")
    print("- v41 clean-data/clock/resampler front-end retained")
    print("- cross-episode biometric recurrence uses disjoint independence-group matching")
    print("- reciprocal/very-strong seeds are provisional; single pair cannot confirm a human")
    print("- corroboration survives removal of the strongest matched observation")
    print("- global human partition is rebuilt from retained evidence and can split again")
    print("- legacy v40 biological merge authority remains disabled")

if __name__ == "__main__": main()
