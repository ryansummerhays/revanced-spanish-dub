#!/usr/bin/env python3
"""Audit v2.32.8 Stage F: bounded short speaker-feature windows, still no clustering/assignment."""
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
        raise SystemExit("usage: audit_v2328_speaker_features_stage_f.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.8 Stage-F speaker-feature diagnostics", "Stage-F header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmVoiceAnalysis=direct-pcm16-energy-peak-zcr-voice-candidate-stage-e", "Stage-E PCM16 analyzer retained")
    need(controller, "speakerPcmDiarizationStatus=pre-clustering-short-speaker-feature-windows", "Stage-F status")
    need(controller, "speakerFeatureBackend=pcm16-autocorrelation+7point-goertzel-diagnostic-only", "feature backend label")
    need(controller, "speakerFeatureWorkerThreads=0", "zero feature workers")
    need(controller, "speakerFeatureByteArrayCopies=0", "zero byte-array copies")
    need(controller, "speakerFeatureClustering=disabled-stage-f", "clustering disabled diagnostic")
    need(controller, "speakerFeatureAssignment=disabled-stage-f", "assignment disabled diagnostic")

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    # Proven AudioTrack.write hook geometry must remain identical.
    need(hook, "val trackRegister = when (writeInstruction)", "AudioTrack receiver register extraction")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerC", "FiveRegister receiver register")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister", "range receiver register")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerD", "FiveRegister ByteBuffer register")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister + 1", "range ByteBuffer register")
    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "Stage-D track callback")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "proven PCM callback")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    pcm_callback = between(
        player_volume,
        "public static void observePcmBufferForStudy(ByteBuffer buffer)",
        "private static void studyAnalyzeSpeakerFeatureSample",
        "Stage-F PCM callback",
    )
    need(pcm_callback, "ByteBuffer view = buffer.duplicate();", "safe duplicate retained")
    need(pcm_callback, "studyPcmAnalysisDecodedFrames += frameCount;", "Stage-E decoding retained")
    need(pcm_callback, "studyPcmVoiceCandidateBuffers++", "Stage-E voice candidate retained")
    need(pcm_callback, "studySpeakerFeatureCandidateTicks++", "Stage-F sparse candidate counter")
    need(pcm_callback, "% STUDY_SPEAKER_FEATURE_STRIDE", "Stage-F sparse stride")
    need(pcm_callback, "studyAnalyzeSpeakerFeatureSample(view, position, frameCount, bytesPerFrame,", "feature sampler call")
    need(pcm_callback, "studyFinalizeSpeakerFeatureWindow();", "independent feature-window finalization")

    feature_helpers = between(
        player_volume,
        "private static void studyAnalyzeSpeakerFeatureSample",
        "public static long getPcmHookCallsForStudy()",
        "Stage-F feature helpers",
    )
    need(player_volume, "STUDY_SPEAKER_FEATURE_STRIDE = 5", "1-in-5 candidate sampling")
    need(player_volume, "STUDY_SPEAKER_FEATURE_MAX_MONO = 1024", "bounded mono scratch")
    need(player_volume, "STUDY_SPEAKER_FEATURE_WINDOW_MS = 800", "800 ms independent windows")
    need(player_volume, "STUDY_SPEAKER_FEATURE_MIN_VOICE_MS = 480", "minimum voiced time")
    need(player_volume, "STUDY_SPEAKER_FEATURE_MIN_SAMPLES = 4", "minimum feature samples")
    need(player_volume, "new short[STUDY_SPEAKER_FEATURE_MAX_MONO]", "single static short scratch allocation")
    need(feature_helpers, "studySpeakerMonoScratch[frame] = mono;", "decoded mono scratch fill")
    need(feature_helpers, "sampleRateHz / 320", "pitch minimum lag")
    need(feature_helpers, "sampleRateHz / 80", "pitch maximum lag")
    need(feature_helpers, "bestCorr >= 0.18", "pitch confidence gate")
    need(feature_helpers, "studyGoertzelPower(n, mean, sampleRateHz, 125.0)", "125 Hz spectral point")
    need(feature_helpers, "studyGoertzelPower(n, mean, sampleRateHz, 6000.0)", "6 kHz spectral point")
    need(feature_helpers, "Math.cos(omega)", "Goertzel coefficient")
    need(feature_helpers, "studySpeakerFeatureValidWindows++", "valid feature window count")
    need(feature_helpers, "studySpeakerFeatureRejectedWindows++", "rejected feature window count")
    need(feature_helpers, "studySpeakerFeatureRollingHash", "feature diversity hash")
    need(feature_helpers, "catch (Throwable ignored)", "fail-soft feature extraction")

    # Stage F intentionally allows only the one preallocated short[] scratch and tiny scalar arrays.
    for token, label in (
        ("new byte", "byte-array PCM copy"),
        ("System.arraycopy", "array copying"),
        ("Thread(", "worker thread creation"),
        ("ThreadPoolExecutor", "thread pool"),
        ("ExecutorService", "executor service"),
        ("LocalSpeakerDiarizer", "old diarizer class"),
        ("PcmSpeakerFeature", "old helper class"),
        ("SpanishStudyDiagnostics", "audio-thread diagnostic logging"),
        ("createSpeaker", "speaker cluster creation"),
        ("SpeakerProfile", "speaker profile clustering"),
        ("Assignment", "speaker assignment object"),
        ("labelForSegment", "segment speaker labels"),
    ):
        forbid(feature_helpers, token, label)

    # Every Stage-F metric used for runtime validation must be published.
    for getter in (
        "getSpeakerFeatureStrideForStudy()", "getSpeakerFeatureMaxMonoForStudy()",
        "getSpeakerFeatureWindowMsForStudy()", "getSpeakerFeatureMinVoiceMsForStudy()",
        "getSpeakerFeatureMinSamplesForStudy()", "getSpeakerFeatureAttemptsForStudy()",
        "getSpeakerFeatureSuccessForStudy()", "getSpeakerFeatureErrorsForStudy()",
        "getSpeakerFeatureWindowsForStudy()", "getSpeakerFeatureValidWindowsForStudy()",
        "getSpeakerFeatureRejectedWindowsForStudy()", "getSpeakerFeatureLastWindowVoiceMsForStudy()",
        "getSpeakerFeatureLastWindowSamplesForStudy()", "getSpeakerFeatureLastPitchHzForStudy()",
        "getSpeakerFeatureLastPitchConfidencePermilleForStudy()", "getSpeakerFeatureLastCentroidHzForStudy()",
        "getSpeakerFeatureLastZcrPermilleForStudy()", "getSpeakerFeatureLastLowPermilleForStudy()",
        "getSpeakerFeatureLastMidPermilleForStudy()", "getSpeakerFeatureLastHighPermilleForStudy()",
        "getSpeakerFeatureMinPitchHzForStudy()", "getSpeakerFeatureMaxPitchHzForStudy()",
        "getSpeakerFeatureMinCentroidHzForStudy()", "getSpeakerFeatureMaxCentroidHzForStudy()",
        "getSpeakerFeatureRollingHashForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "Stage-F diagnostic publication " + getter)
    need(controller, "getSpeakerFeatureLastBandPermilleForStudy(0)", "band-vector diagnostic start")
    need(controller, "getSpeakerFeatureLastBandPermilleForStudy(6)", "band-vector diagnostic end")

    # Sacred Morphe translation/segmentation invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")

    # Stock Morphe audio volume hooks remain present.
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack wrapper observation retained")

    print("v2.32.8 Stage-F audit passed")
    print("Runtime target: stable playback + featureAttempts > 0 + featureSuccess > 0 + featureErrors == 0 + validWindows > 0.")
    print("Useful discrimination signal: nonzero pitch/centroid ranges and a changing rolling hash across speech-heavy playback.")


if __name__ == "__main__":
    main()
