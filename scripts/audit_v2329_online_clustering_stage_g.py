#!/usr/bin/env python3
"""Audit v2.32.9 Stage G: diagnostic fixed-size online speaker clustering only."""
from pathlib import Path
import sys


def need(text: str, token: str, label: str) -> None:
    if token not in text:
        raise RuntimeError(f"missing {label}: {token}")
    print("ok:", label)


def forbid(text: str, token: str, label: str) -> None:
    if token in text:
        raise RuntimeError(f"forbidden {label}: {token}")
    print("ok absent:", label)


def between(text: str, start: str, end: str, label: str) -> str:
    a = text.find(start)
    if a < 0:
        raise RuntimeError(f"missing {label} start anchor")
    b = text.find(end, a + len(start))
    if b < 0:
        raise RuntimeError(f"missing {label} end anchor")
    return text[a:b]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2329_online_clustering_stage_g.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.9 Stage-G online-clustering diagnostics", "Stage-G header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmVoiceAnalysis=direct-pcm16-energy-peak-zcr-voice-candidate-stage-e", "Stage-E analyzer retained")
    need(controller, "speakerFeatureBackend=pcm16-autocorrelation+7point-goertzel-diagnostic-only", "Stage-F feature backend retained")
    need(controller, "speakerPcmDiarizationStatus=diagnostic-online-clustering-no-label-routing", "Stage-G status")
    need(controller, "speakerFeatureClustering=online-fixed-centroid-stage-g-diagnostic-only", "Stage-G clustering diagnostic")
    need(controller, "speakerFeatureAssignment=cluster-window-only-no-subtitle-labels-stage-g", "no subtitle assignment")

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "Stage-D track callback retained")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "proven direct PCM callback retained")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    feature_helpers = between(
        player_volume,
        "private static void studyAnalyzeSpeakerFeatureSample",
        "public static long getPcmHookCallsForStudy()",
        "Stage-F/G feature and clustering helpers",
    )
    need(feature_helpers, "studySpeakerFeatureValidWindows++", "Stage-F valid windows retained")
    need(feature_helpers, "studyAssignSpeakerCluster(pitchHz, pitchConfidencePermille, centroidHz, zcrPermille);", "cluster only valid windows")
    need(feature_helpers, "private static void studyAssignSpeakerCluster", "Stage-G assignment helper")
    need(feature_helpers, "private static double studySpeakerClusterDistance", "Stage-G distance helper")
    need(feature_helpers, "studySpeakerClusterCentroids", "fixed centroid arrays")
    need(feature_helpers, "STUDY_SPEAKER_CLUSTER_NEW_DISTANCE", "new-cluster threshold")
    need(feature_helpers, "STUDY_SPEAKER_CLUSTER_MIN_SEED_GAP", "cluster seed cooldown")
    need(feature_helpers, "STUDY_SPEAKER_CLUSTER_STABLE_RUN", "temporal stabilization gate")
    need(feature_helpers, "studySpeakerClusterRawSwitches++", "raw switch count")
    need(feature_helpers, "studySpeakerClusterCommittedSwitches++", "committed switch count")
    need(feature_helpers, "Math.min(63L, oldCount)", "bounded centroid adaptation memory")
    need(feature_helpers, "pitchReliability", "confidence-weighted pitch distance")

    need(player_volume, "STUDY_SPEAKER_CLUSTER_MAX = 4", "four anonymous clusters max")
    need(player_volume, "STUDY_SPEAKER_CLUSTER_DIMS = 10", "ten-dimensional fixed feature vector")
    need(player_volume, "new double[STUDY_SPEAKER_CLUSTER_MAX][STUDY_SPEAKER_CLUSTER_DIMS]", "static centroid storage")
    need(player_volume, "new double[STUDY_SPEAKER_CLUSTER_DIMS]", "static feature scratch")

    for token, label in (
        ("new byte", "byte-array PCM copy"),
        ("System.arraycopy", "array copying"),
        ("Thread(", "worker thread creation"),
        ("ThreadPoolExecutor", "thread pool"),
        ("ExecutorService", "executor service"),
        ("LocalSpeakerDiarizer", "old diarizer class"),
        ("PcmSpeakerFeature", "old helper class"),
        ("SpanishStudyDiagnostics", "audio-thread diagnostic logging"),
        ("labelForSegment", "subtitle speaker label lookup"),
        ("setVoice", "speaker voice routing"),
    ):
        forbid(feature_helpers, token, label)

    for getter in (
        "getSpeakerClusterMaxForStudy()", "getSpeakerClusterMinSeedGapForStudy()",
        "getSpeakerClusterStableRunForStudy()", "getSpeakerClusterNewDistancePermilleForStudy()",
        "getSpeakerClusterCountForStudy()", "getSpeakerClusterWindowsForStudy()",
        "getSpeakerClusterCreatesForStudy()", "getSpeakerClusterAssignmentsForStudy()",
        "getSpeakerClusterRawSwitchesForStudy()", "getSpeakerClusterCommittedSwitchesForStudy()",
        "getSpeakerClusterLastRawForStudy()", "getSpeakerClusterCommittedForStudy()",
        "getSpeakerClusterLastDistancePermilleForStudy()", "getSpeakerClusterLastMarginPermilleForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "Stage-G diagnostic publication " + getter)
    need(controller, "getSpeakerClusterCountForStudy(cluster)", "cluster window counts")
    need(controller, "getSpeakerClusterAveragePitchHzForStudy(cluster)", "cluster average pitch")
    need(controller, "getSpeakerClusterAverageCentroidHzForStudy(cluster)", "cluster average centroid")
    need(controller, "getSpeakerClusterAverageZcrPermilleForStudy(cluster)", "cluster average ZCR")
    need(controller, "getSpeakerClusterAverageBandPermilleForStudy(cluster, band)", "cluster band profile")

    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack observation retained")

    print("v2.32.9 Stage-G audit passed")
    print("Runtime target: stable playback + clusterWindows tracks valid feature windows + 2-4 clusters emerge without runaway switching.")
    print("Do not enable subtitle labels or voice routing from Stage G alone; first inspect cluster balance, centroid separation, distance/margin, and switch rates.")


if __name__ == "__main__":
    main()
