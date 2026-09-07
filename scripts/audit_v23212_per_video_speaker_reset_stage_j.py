#!/usr/bin/env python3
"""Audit v2.32.12 Stage-J per-video speaker-analysis reset."""
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v23212_per_video_speaker_reset_stage_j.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pv = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    vot = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    tr = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java").read_text(encoding="utf-8")
    fetcher = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java").read_text(encoding="utf-8")
    controller = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.12 Stage-J per-video-speaker-reset diagnostics", "Stage-J header")
    need(controller, "speakerAnalysisScope=per-video-reset-stage-j", "per-video diagnostic scope")
    need(controller, "speakerAnalysisEpoch=", "analysis epoch diagnostic")
    need(controller, "speakerAnalysisResetCount=", "reset count diagnostic")

    need(pv, "public static void resetSpeakerAnalysisForStudy()", "reset method")
    need(pv, "studySpeakerAnalysisResetInProgress", "audio-thread reset guard")
    need(pv, "studySpeakerClusterCount = 0;", "cluster count reset")
    need(pv, "studySpeakerClusterCommitted = -1;", "committed label reset")
    need(pv, "studySpeakerFeatureWindowElapsedMs = 0L;", "partial feature window reset")
    need(pv, "studyPcmVoiceNoiseFloorPermille = 4;", "per-video voice floor reset")
    need(pv, "studySpeakerAnalysisEpoch++;", "reset epoch increment")

    method_start = vot.index("public static void newVideoLoaded(String videoId)")
    method_end = vot.index("\n    /**", method_start + 20)
    new_video = vot[method_start:method_end]
    need(new_video, "if (videoId.equals(currentVideoId)) return;", "existing same-video guard")
    need(new_video, "PlayerVolumePatch.resetSpeakerAnalysisForStudy();", "new-video reset call")
    if new_video.index("if (videoId.equals(currentVideoId)) return;") > new_video.index("PlayerVolumePatch.resetSpeakerAnalysisForStudy();"):
        raise RuntimeError("speaker reset occurs before same-video guard")
    print("ok: same-video callbacks do not reset learned clusters")

    # Stage-G math remains exactly at the proven Stage-I settings.
    need(pv, "private static final int STUDY_SPEAKER_CLUSTER_MAX = 4;", "cluster max unchanged")
    need(pv, "private static final int STUDY_SPEAKER_CLUSTER_MIN_SEED_GAP = 6;", "seed gap unchanged")
    need(pv, "private static final double STUDY_SPEAKER_CLUSTER_NEW_DISTANCE = 0.255;", "new-cluster threshold unchanged")
    need(pv, "private static final int STUDY_SPEAKER_CLUSTER_STABLE_RUN = 2;", "commit smoothing unchanged")
    need(pv, "(0.50 * band)", "Stage-G spectral distance weight unchanged")
    need(pv, "(0.18 * pitchReliability * dp * dp)", "Stage-G pitch distance weight unchanged")

    # Stage-F and direct PCM capture remain present.
    need(pv, "private static final int STUDY_SPEAKER_FEATURE_WINDOW_MS = 800;", "Stage-F feature window unchanged")
    need(pv, "private static final int STUDY_SPEAKER_FEATURE_STRIDE = 5;", "Stage-F feature stride unchanged")
    need(pv, "public static void observePcmBufferForStudy(ByteBuffer buffer)", "direct PCM callback retained")

    # Sacred Morphe translation architecture remains untouched.
    need(tr, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char packet cap unchanged")
    need(tr, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first packet unchanged")
    need(fetcher, "mergeIntoSentences", "stock sentence merge retained")

    # Stage-I audition control remains in place.
    need(vot, "applySpanishVoiceStudySetting", "Spanish voice toggle retained")
    need(vot, "effectiveSpanishVoiceVolumeForStudy", "Spanish TTS audition volume gate retained")

    # No heavyweight speaker runtime is introduced in this isolation stage.
    forbid(pv, "ExecutorService", "no speaker executor")
    forbid(pv, "ThreadPoolExecutor", "no speaker worker pool")
    forbid(pv, "onnx", "no embedding runtime yet")

    print("Stage-J audit passed")


if __name__ == "__main__":
    main()
