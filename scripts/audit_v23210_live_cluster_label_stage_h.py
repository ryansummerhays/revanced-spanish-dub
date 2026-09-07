#!/usr/bin/env python3
"""Audit v2.32.10 Stage H: display-only live committed A/B/C/D cluster badge."""
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


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23210_live_cluster_label_stage_h.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    subtitle = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.10 Stage-H live-cluster-label diagnostics", "Stage-H header")
    need(controller, "speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing", "Stage-H status")
    need(controller, "speakerFeatureClustering=online-fixed-centroid-stage-g-diagnostic-only", "Stage-G clustering retained")
    need(controller, "speakerFeatureAssignment=committed-cluster-live-subtitle-badge-stage-h", "Stage-H assignment status")
    need(controller, "speakerLabelClock=live-source-pcm-committed-cluster", "live label clock")
    need(controller, "speakerLabelPersistence=none-live-diagnostic-only", "no persisted assignments")

    need(subtitle, "import app.morphe.extension.youtube.patches.PlayerVolumePatch;", "Stage-H PlayerVolume import")
    need(subtitle, "getSpeakerClusterCommittedForStudy()", "committed Stage-G cluster lookup")
    need(subtitle, "getSpeakerClusterCountForStudy()", "cluster range check")
    need(subtitle, "String.valueOf((char) ('A' + committedCluster))", "anonymous A/B/C/D badge")
    need(subtitle, "detail=stage-h-live-committed-cluster", "speaker badge diagnostic detail")
    need(subtitle, "getSpeakerClusterLastDistancePermilleForStudy()", "badge-change distance diagnostic")
    need(subtitle, "getSpeakerClusterLastMarginPermilleForStudy()", "badge-change margin diagnostic")
    forbid(subtitle, "LocalSpeakerDiarizer.labelForSegment(index)", "legacy Visualizer label lookup")
    forbid(subtitle, "LocalSpeakerDiarizer.assignmentDetails(index)", "legacy Visualizer assignment details")

    # Stage H must consume Stage-G state, not modify the clustering algorithm.
    need(player_volume, "STUDY_SPEAKER_CLUSTER_NEW_DISTANCE = 0.255", "Stage-G new-cluster threshold retained")
    need(player_volume, "STUDY_SPEAKER_CLUSTER_STABLE_RUN = 2", "Stage-G two-window commit retained")
    need(player_volume, "private static void studyAssignSpeakerCluster", "Stage-G clustering helper retained")
    need(player_volume, "studySpeakerClusterCommitted = best", "Stage-G committed state retained")
    need(player_volume, "getSpeakerClusterCommittedForStudy()", "Stage-G committed getter retained")

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "proven direct PCM callback retained")
    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "AudioTrack metadata callback retained")

    for token, label in (
        ("setVoice", "speaker TTS voice routing"),
        ("ThreadPoolExecutor", "new worker pool"),
        ("ExecutorService", "new executor"),
        ("new Thread", "new thread"),
        ("onPcmBuffer", "legacy diarizer PCM path"),
    ):
        forbid(subtitle, token, label)

    print("v2.32.10 Stage-H audit passed")
    print("Runtime target: stable playback + visible [A]/[B]/[C]/[D] badge changes that track the actual person speaking.")
    print("Do not route TTS voices yet. First visually validate whether clusters represent people rather than acoustic states/outliers.")


if __name__ == "__main__":
    main()
