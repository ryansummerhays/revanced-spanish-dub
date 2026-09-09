#!/usr/bin/env python3
"""v2.33.36: production-inspired streaming speaker cache + acoustic change-point gating.

Applies after v2.33.35. Preserves the proven accepted-PCM/video-master clock and native
ERes2Net extractor. This revision adopts the useful architecture of production streaming
speaker diarizers without adding a cloud dependency:
- use a longer rolling identity view while retaining the 600 ms update cadence;
- treat adjacent embeddings as a change-point signal, not independent identities;
- require stronger entry/boundary evidence as the persistent speaker inventory grows;
- keep established speaker profiles as a multi-prototype cache and avoid profile poisoning;
- keep the last committed human visible while a provisional observation resolves;
- allow candidate promotion to retroactively fill its interval, as before.

This intentionally does not claim to run Sortformer/diart or pyannote segmentation live. It
implements the same streaming principles using the local signals already proven on Android.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def req(path: Path, needle: str, label: str) -> None:
    if needle not in path.read_text(encoding="utf-8"):
        raise RuntimeError(f"{label}: missing {needle!r}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: patch_v23336_streaming_context.py <morphe-root> [repo-root]")
    root = Path(sys.argv[1]).resolve()
    live = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LiveSpeakerOnline.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for p in (live, controller):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.35 source: {p}")

    rep(live,
        '''    private static final int WINDOW_SAMPLES = 24_000;          // 1.5 s\n    private static final int HOP_SAMPLES = 9_600;              // 0.60 s\n    private static final int RING_SAMPLES = 40_000;            // 2.5 s\n''',
        '''    private static final int WINDOW_SAMPLES = 32_000;          // 2.0 s identity context\n    private static final int HOP_SAMPLES = 9_600;              // 0.60 s update cadence\n    private static final int RING_SAMPLES = 48_000;            // 3.0 s rolling context\n''',
        "restore contextual 2.0s identity window at 600ms cadence")

    rep(live,
        '''    private static final float STYLE_PENDING_MATCH = 0.60f;\n    private static final float STYLE_MIN_COHESION = 0.54f;\n''',
        '''    private static final float STYLE_PENDING_MATCH = 0.60f;\n    private static final float STYLE_MIN_COHESION = 0.54f;\n    private static final float ADJACENT_CHANGE_POINT = 0.44f;\n    private static final long ADJACENT_MAX_GAP_MS = 1_200L;\n    private static final long CANDIDATE_BOUNDARY_LOOKBACK_MS = 1_100L;\n    private static final int THIRD_SPEAKER_MIN_SUPPORT = 7;\n    private static final int LATER_SPEAKER_MIN_SUPPORT = 9;\n    private static final long THIRD_SPEAKER_MIN_SPAN_MS = 2_700L;\n    private static final long LATER_SPEAKER_MIN_SPAN_MS = 3_600L;\n''',
        "add sequential change-point and inventory-complexity gates")

    rep(live,
        '''    private static int lastCandidateParent = -1;\n    private static float lastBestSimilarity;\n''',
        '''    private static int lastCandidateParent = -1;\n    private static float[] lastObservationEmbedding;\n    private static long lastObservationEndVideoMs = -1L;\n    private static long lastAcousticBoundaryVideoMs = -1L;\n    private static float lastAdjacentSimilarity = -1f;\n    private static int adjacentComparisons;\n    private static int adjacentChangePoints;\n    private static int inventoryComplexityBlocks;\n    private static int badgeCommittedHolds;\n    private static float lastBestSimilarity;\n''',
        "add streaming observation/change-point state")

    rep(live,
        '''            lastCandidateParent = -1;\n            lastBestSimilarity = 0f;\n''',
        '''            lastCandidateParent = -1;\n            lastObservationEmbedding = null;\n            lastObservationEndVideoMs = -1L;\n            lastAcousticBoundaryVideoMs = -1L;\n            lastAdjacentSimilarity = -1f;\n            adjacentComparisons = 0;\n            adjacentChangePoints = 0;\n            inventoryComplexityBlocks = 0;\n            badgeCommittedHolds = 0;\n            lastBestSimilarity = 0f;\n''',
        "reset sequential state on a genuinely new video")

    rep(live,
        '''        clearStylePendingLocked();\n        lastCommittedSpeechRunSerial = -1L;\n        lastCommittedEndVideoMs = -1L;\n''',
        '''        clearStylePendingLocked();\n        lastCommittedSpeechRunSerial = -1L;\n        lastObservationEmbedding = null;\n        lastObservationEndVideoMs = -1L;\n        lastAcousticBoundaryVideoMs = -1L;\n        lastAdjacentSimilarity = -1f;\n        lastCommittedEndVideoMs = -1L;\n''',
        "invalidate sequential context on seek")

    rep(live,
        '''    private static void assignLocked(Job job, float[] embedding) {\n        if (embedding == null || embedding.length == 0) return;\n''',
        '''    private static void assignLocked(Job job, float[] embedding) {\n        if (embedding == null || embedding.length == 0) return;\n\n        boolean acousticChangePoint = job.firstInSpeechRun;\n        float adjacent = -1f;\n        if (lastObservationEmbedding != null && lastObservationEndVideoMs >= 0L\n                && job.startVideoMs <= lastObservationEndVideoMs + ADJACENT_MAX_GAP_MS) {\n            adjacent = cosine(lastObservationEmbedding, embedding);\n            adjacentComparisons++;\n            if (adjacent < ADJACENT_CHANGE_POINT) {\n                acousticChangePoint = true;\n                adjacentChangePoints++;\n            }\n        }\n        lastAdjacentSimilarity = adjacent;\n        lastObservationEmbedding = embedding.clone();\n        lastObservationEndVideoMs = job.endVideoMs;\n        if (acousticChangePoint) lastAcousticBoundaryVideoMs = job.endVideoMs;\n''',
        "derive acoustic change points from sequential embeddings")

    rep(live,
        '''        int dynamicMinSupport = profileCount <= 1 ? NEW_PROFILE_MIN_SUPPORT\n                : (profileCount == 2 ? 4 : 5);\n        boolean boundaryEvidence = candidate.distinctSpeechRuns >= 2\n                && candidate.count >= dynamicMinSupport;\n        boolean exceptionalLongRun = candidate.parentSpeaker < 0\n                && candidate.distinctSpeechRuns == 1\n                && candidate.count >= NEW_PROFILE_LONG_RUN_SUPPORT\n                && candidateSpanMs >= NEW_PROFILE_LONG_RUN_MS\n                && avgCohesion >= NEW_PROFILE_LONG_RUN_COHESION\n                && candidateKnownBest < NEW_PROFILE_LONG_RUN_MAX_KNOWN;\n        boolean coherentEnough = avgCohesion >= CANDIDATE_MIN_AVG_COHESION;\n        boolean clearlyNovel = candidateKnownBest < CANDIDATE_AMBIGUOUS_KNOWN;\n        boolean highCohesionOverride = candidate.count >= 6\n                && avgCohesion >= CANDIDATE_HIGH_COHESION\n                && candidateKnownBest < CANDIDATE_RESCUE_MATCH;\n        boolean readyNew = candidate.count >= dynamicMinSupport\n                && candidateSpanMs >= CANDIDATE_MIN_SPAN_MS\n                && coherentEnough\n                && (boundaryEvidence || exceptionalLongRun)\n                && (clearlyNovel || highCohesionOverride);\n''',
        '''        int dynamicMinSupport = profileCount <= 1 ? NEW_PROFILE_MIN_SUPPORT\n                : (profileCount == 2 ? THIRD_SPEAKER_MIN_SUPPORT : LATER_SPEAKER_MIN_SUPPORT);\n        long dynamicMinSpanMs = profileCount <= 1 ? CANDIDATE_MIN_SPAN_MS\n                : (profileCount == 2 ? THIRD_SPEAKER_MIN_SPAN_MS : LATER_SPEAKER_MIN_SPAN_MS);\n        boolean recentAcousticBoundary = lastAcousticBoundaryVideoMs >= 0L\n                && lastAcousticBoundaryVideoMs + CANDIDATE_BOUNDARY_LOOKBACK_MS >= candidate.startVideoMs;\n        boolean vadBoundaryEvidence = candidate.distinctSpeechRuns >= 2;\n        boolean boundaryEvidence = profileCount <= 1\n                ? (vadBoundaryEvidence || recentAcousticBoundary)\n                : (vadBoundaryEvidence && recentAcousticBoundary);\n        boolean exceptionalLongRun = candidate.parentSpeaker < 0\n                && candidate.distinctSpeechRuns == 1\n                && candidate.count >= NEW_PROFILE_LONG_RUN_SUPPORT\n                && candidateSpanMs >= NEW_PROFILE_LONG_RUN_MS\n                && avgCohesion >= NEW_PROFILE_LONG_RUN_COHESION\n                && candidateKnownBest < NEW_PROFILE_LONG_RUN_MAX_KNOWN\n                && profileCount <= 1;\n        boolean coherentEnough = avgCohesion >= CANDIDATE_MIN_AVG_COHESION;\n        boolean clearlyNovel = candidateKnownBest < CANDIDATE_AMBIGUOUS_KNOWN;\n        boolean highCohesionOverride = candidate.count >= Math.max(6, dynamicMinSupport)\n                && avgCohesion >= CANDIDATE_HIGH_COHESION\n                && candidateKnownBest < CANDIDATE_RESCUE_MATCH;\n        boolean readyNew = candidate.count >= dynamicMinSupport\n                && candidateSpanMs >= dynamicMinSpanMs\n                && coherentEnough\n                && (boundaryEvidence || exceptionalLongRun)\n                && (clearlyNovel || highCohesionOverride);\n        if (!readyNew && profileCount >= 2 && candidate.count >= 4\n                && coherentEnough && (clearlyNovel || highCohesionOverride)) {\n            inventoryComplexityBlocks++;\n        }\n''',
        "add production-style boundary gate and complexity penalty for C+")

    rep(live,
        '''            if (candidate != null && videoMs >= candidate.startVideoMs\n                    && videoMs <= candidate.endVideoMs + 700L) {\n                if (candidate.parentSpeaker >= 0 && candidate.parentSpeaker < profileCount) {\n                    return labelFor(candidate.parentSpeaker) + "?";\n                }\n                return "?";\n            }\n''',
        '''            if (candidate != null && videoMs >= candidate.startVideoMs\n                    && videoMs <= candidate.endVideoMs + 900L) {\n                if (candidate.parentSpeaker >= 0 && candidate.parentSpeaker < profileCount) {\n                    return labelFor(candidate.parentSpeaker);\n                }\n                boolean candidateHasBoundary = lastAcousticBoundaryVideoMs >= 0L\n                        && lastAcousticBoundaryVideoMs + CANDIDATE_BOUNDARY_LOOKBACK_MS\n                                >= candidate.startVideoMs;\n                if (!candidateHasBoundary && lastCommittedSpeaker >= 0\n                        && lastCommittedSpeaker < profileCount) {\n                    badgeCommittedHolds++;\n                    return labelFor(lastCommittedSpeaker);\n                }\n                if (lastCommittedSpeaker >= 0 && lastCommittedSpeaker < profileCount) {\n                    return labelFor(lastCommittedSpeaker) + "?";\n                }\n                return "?";\n            }\n''',
        "hold last committed human through provisional uncertainty")

    rep(live,
        '''                    return labelFor(TL_SPEAKER[i]) + "?";\n                }\n                if (videoMs > TL_END[i] + LIVE_HOLD_MS) break;\n''',
        '''                    return labelFor(TL_SPEAKER[i]);\n                }\n                if (videoMs > TL_END[i] + LIVE_HOLD_MS) break;\n''',
        "do not turn ordinary live-lag hold into A?/B? flicker")

    rep(live,
        '''            return "speakerLiveMode=eres2net-short-window-online-human-identity-v23335\\n"\n                    + "speakerLiveWindowMs=1500\\n"\n                    + "speakerLiveHopMs=600\\n"\n''',
        '''            return "speakerLiveMode=eres2net-contextual-streaming-human-identity-v23336\\n"\n                    + "speakerLiveWindowMs=2000\\n"\n                    + "speakerLiveHopMs=600\\n"\n                    + "speakerLiveArchitecture=sequential-change-point+multi-prototype-speaker-cache+provisional-retrofill\\n"\n                    + "speakerLiveBoundaryPolicy=vad-run+adjacent-embedding-change;Cplus-requires-both\\n"\n''',
        "publish contextual streaming architecture")

    rep(live,
        '''                    + "speakerLiveStyleBridgeMinWindows=2\\n"\n                    + "speakerLiveMaxPrototypesPerHuman=4\\n"\n''',
        '''                    + "speakerLiveStyleBridgeMinWindows=2\\n"\n                    + "speakerLiveMaxPrototypesPerHuman=4\\n"\n                    + "speakerLiveThirdSpeakerMinSupport=" + THIRD_SPEAKER_MIN_SUPPORT + "\\n"\n                    + "speakerLiveLaterSpeakerMinSupport=" + LATER_SPEAKER_MIN_SUPPORT + "\\n"\n''',
        "publish inventory complexity policy")

    rep(live,
        '''                    + "speakerLiveNewProfileLongRunPromotions=" + newProfileLongRunPromotions + "\\n"\n                    + "speakerLiveCandidateParent=" + lastCandidateParent + "\\n"\n''',
        '''                    + "speakerLiveNewProfileLongRunPromotions=" + newProfileLongRunPromotions + "\\n"\n                    + "speakerLiveAdjacentComparisons=" + adjacentComparisons + "\\n"\n                    + "speakerLiveAdjacentChangePoints=" + adjacentChangePoints + "\\n"\n                    + "speakerLiveLastAdjacentSimilarityPermille=" + permille(lastAdjacentSimilarity) + "\\n"\n                    + "speakerLiveInventoryComplexityBlocks=" + inventoryComplexityBlocks + "\\n"\n                    + "speakerLiveBadgeCommittedHolds=" + badgeCommittedHolds + "\\n"\n                    + "speakerLiveCandidateParent=" + lastCandidateParent + "\\n"\n''',
        "publish streaming change-point counters")

    rep(controller,
        'report.append("Spanish Dub Study v2.33.35 persistent speaker badge + translation integrity diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.36 streaming speaker-cache + change-point diagnostics\\n");',
        "update diagnostics header")

    rep(controller,
        '        report.append("speakerLiveGoal=human-identity-first;voice-style-is-not-a-new-human-without-boundary-evidence\\n");\n',
        '        report.append("speakerLiveGoal=production-style-streaming-human-identity;sequence+boundary+speaker-cache\\n");\n',
        "update live goal marker")

    req(live, "speakerLiveMode=eres2net-contextual-streaming-human-identity-v23336", "v36 live marker")
    req(live, "speakerLiveArchitecture=sequential-change-point+multi-prototype-speaker-cache+provisional-retrofill", "streaming architecture marker")
    req(live, "ADJACENT_CHANGE_POINT = 0.44f", "adjacent change detector")
    req(live, "THIRD_SPEAKER_MIN_SUPPORT = 7", "third speaker complexity gate")
    req(live, "speakerLiveBadgeCommittedHolds=", "persistent badge counter")
    req(controller, "v2.33.36 streaming speaker-cache + change-point", "v36 controller marker")

    print("v2.33.36 production-inspired streaming diarization revision complete")
    print("PRESERVED: video-ms master clock, exact accepted PCM, verifier-safe postwrite hook, local ERes2Net, latest-wins worker")
    print("CHANGED: 2.0s rolling context / 0.6s cadence, sequential change-point gating, C+ complexity penalty, persistent committed badge")


if __name__ == "__main__":
    main()
