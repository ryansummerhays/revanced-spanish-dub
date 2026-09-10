#!/usr/bin/env python3
"""Hard source audit for v2.33.41 clean-episode statistical identity."""
from pathlib import Path
import hashlib, sys

EXPECTED = {
    "LiveSpeakerOnline.java": "390fe802672a109106d2650198ad66e740d3414b90128f16d3bc655904137f99",
    "SherpaNeuralShadow.java": "2b4012c4e5353769b1d1d1927aeca3b6bcee482a3d12d2411693fbd539de5626",
    "SpanishStudyController.java": "81364bfe7a86ccdcbd3840b880420945ac3fa76987341a4ac66b4bc91d759868",
}

def must(text, needle, label):
    if needle not in text: raise RuntimeError(f"{label}: missing {needle!r}")

def exactly(text, needle, n, label):
    got=text.count(needle)
    if got != n: raise RuntimeError(f"{label}: expected {n}, found {got}: {needle!r}")

def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if len(sys.argv) < 2: raise SystemExit("usage: audit_v23341_clean_episode_statistics.py <morphe-root>")
    root=Path(sys.argv[1]).resolve()
    d=root/"extensions/youtube/src/main/java/app/spanishstudy/vot"
    paths={n:d/n for n in EXPECTED}
    for n,p in paths.items():
        if sha(p) != EXPECTED[n]: raise RuntimeError(f"exact v41 source hash mismatch: {n}: {sha(p)}")
    live=paths["LiveSpeakerOnline.java"].read_text(encoding="utf-8")
    sherpa=paths["SherpaNeuralShadow.java"].read_text(encoding="utf-8")
    ctl=paths["SpanishStudyController.java"].read_text(encoding="utf-8")

    # Proven clock/PCM and live embedding foundation stays present.
    must(live, "AudioVideoSyncProbe.projectTrackFrameToVideoMs", "video-master mapping")
    must(live, "WINDOW_SAMPLES = 32_000", "2s shadow window")
    must(live, "HOP_SAMPLES = 9_600", "600ms shadow hop")
    must(live, "SpeakerEmbeddingExtractor", "ERes2Net")
    must(sherpa, "DIARIZER_PROCESS_LOCK", "serialized diarizer JNI")

    # Statistical authority and explicit abstention.
    must(live, "speakerIdentityAuthority=clean-episode-statistical-v23341", "authority marker")
    must(live, "PURITY_EVIDENCE_STAT_SLOT = 4", "stat context job")
    must(live, "STAT_CONTEXT_HOP_SAMPLES = 16_000", "1s context cadence")
    must(live, "STAT_CORE_START_SAMPLE = 72_000", "centered core start")
    must(live, "STAT_CORE_END_SAMPLE = 88_000", "centered core end")
    must(live, "slot.cleanVotes < 2", "three-context consensus gate")
    must(live, "one-contiguous-clean-episode-one-vote", "independence diagnostic")
    must(live, "return human < 0 ? \"?\" : statHumanLabel(human) + \"?\"", "provisional abstention")
    must(live, 'return "?";', "unknown output")

    # Clean data definition: strict single source, boundary trim, exact clean span, no overlap learning.
    must(live, "isStrictStatCoreClean", "strict clean-core gate")
    must(live, "STAT_BOUNDARY_TRIM_SAMPLES = 4_800", "300ms boundary trim")
    must(live, "STAT_MIN_EMBED_SAMPLES = 24_000", "minimum clean embedding span")
    must(live, "result.cleanSpanStartSample", "clean span consumption")
    must(sherpa, "cleanSingleSpeakerSpanAroundCore", "single-source span extraction")
    must(sherpa, "activeCount == 1 && dominantActive", "exactly one local source")
    must(sherpa, "cleanSpanStartSample", "clean span result")

    # Exact source-audio provenance and stateful analysis resampling.
    must(live, "recordSampleSpanLocked", "sample provenance")
    must(live, "videoForTargetSampleLocked", "sample to video mapping")
    must(live, "copyAbsoluteRangeLocked", "absolute sample extraction")
    must(live, "configureAnalysisResamplerLocked", "persistent anti-alias resampler")
    must(live, "resampleZ1", "persistent filter state")
    must(live, "resamplePhase += TARGET_RATE", "persistent rational phase")

    # Independent evidence / robust statistics.
    must(live, "independenceGroup", "independence group")
    must(live, "if (ma.groups[i] == mb.groups[j]) continue", "correlated evidence exclusion")
    must(live, "medoidForCluster", "episode medoid")
    must(live, "return n == 0 ? -1f : median(values, n)", "robust median affinity")
    must(live, "statComparisonPenalty", "multiple comparison penalty")
    must(live, "recomputeStatHumansLocked", "reversible global partition")
    must(live, "STAT_MODE_REUSE_SINGLE = 0.82f", "conservative singleton reuse")
    must(live, "STAT_MODE_REUSE_ESTABLISHED = 0.72f", "established mode reuse")
    must(live, "STAT_MODE_REUSE_MARGIN = 0.080f", "mode reuse margin")

    # v40 biological-authority paths are explicitly shadow-only/no-op.
    must(live, "v41 invariant: a local diarizer id can never directly assign a biological human", "no local-id human assignment")
    must(live, "shadow-new-raw-profile-no-identity-authority", "shadow raw creation")
    must(live, "maybeCommitContextRelationMergeLocked", "legacy relation function retained")
    must(live, "no v40 relation may mutate biological identity", "legacy relation no-op")
    must(live, "v41 shadow-only. Same-run sandwiches remain diagnostic proposals but cannot merge humans", "legacy style no-op")
    exactly(live, "purityRelationLinkedAtCreation++", 0, "no v40 creation-time human link counter")

    # User-facing identity lookup reads statistical timeline, not v40 raw timeline.
    must(live, "String finalized = statFinalizedLabelAtVideoMsLocked(videoMs);", "final statistical timeline")
    must(live, "String provisional = statLiveLabelAtVideoMsLocked(videoMs);", "read-only provisional timeline")
    must(live, "appendStatLiveClassificationLocked(job, embedding);", "shadow embedding classifier")

    # Diagnostics correlate episodes with source transcript but transcript is never identity evidence.
    must(ctl, "Spanish Dub Study v2.33.41 clean-episode statistical speaker identity diagnostics", "v41 header")
    must(ctl, "sourceTextForSpan", "source context helper")
    must(ctl, "lastSource", "source context retention")
    must(live, "SpanishStudyController.sourceTextForSpan", "episode source diagnostic")
    must(live, "speakerStatRejectOverlap=", "rejection telemetry")
    must(live, "speakerStatIndependentGroups=", "independence telemetry")
    must(live, "speakerStatModeMap=", "mode/human telemetry")

    print("v2.33.41 source audit: PASS")
    print("- exact v41 overlay hashes verified")
    print("- accepted PCM/video-master foundation retained")
    print("- 10s centered consensus defines clean single-source data before identity embedding")
    print("- one contiguous episode/evidence-group prevents overlapping-window vote inflation")
    print("- medoid/median statistics + conservative reuse + recomputed human partition")
    print("- v40 local-diarizer biological merge paths are shadow-only/no-op")
    print("- user-facing labels come only from statistical authority with explicit abstention")

if __name__ == "__main__": main()
