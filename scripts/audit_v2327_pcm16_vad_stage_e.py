#!/usr/bin/env python3
"""Audit v2.32.7 Stage E: real PCM16 decoding + bounded voice-candidate analysis, no clustering."""
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
        raise SystemExit("usage: audit_v2327_pcm16_vad_stage_e.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    player_volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    hook = (root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt").read_text(encoding="utf-8")

    need(controller, "Spanish Dub Study v2.32.7 Stage-E PCM16 voice-analysis diagnostics", "Stage-E header")
    need(controller, "captionSourcePolicy=english-first-for-spanish-target-when-available", "English-source policy retained")
    need(controller, "pcmProbe=audio-track-write-bytebuffer-sparse-bounded-read", "Stage-C probe retained")
    need(controller, "pcmTrackProbe=actual-audiotrack-write-receiver-format-metadata", "Stage-D track probe retained")
    need(controller, "pcmVoiceAnalysis=direct-pcm16-energy-peak-zcr-voice-candidate-stage-e", "Stage-E voice analyzer label")
    need(controller, "pcmVoiceAnalysisByteOrder=explicit-little-endian", "explicit PCM16 byte order diagnostic")
    need(controller, "pcmVoiceAnalysisWorkerThreads=0", "zero analysis workers")
    need(controller, "pcmVoiceAnalysisBufferCopies=0", "zero analysis buffer copies")
    need(controller, "speakerPcmDiarizationStatus=pre-clustering-real-pcm-voice-candidate-analysis", "pre-clustering status")

    english_first = fetcher.index('if ("es".equals(targetLang) && englishUrl != null) return englishUrl;')
    target_fallback = fetcher.index("if (targetLangUrl != null) return targetLangUrl;")
    if english_first >= target_fallback:
        raise RuntimeError("English-for-Spanish preference must precede target-language fallback")
    print("ok: English-source repair retained")

    # Proven Stage-D hook geometry must be untouched.
    need(hook, "val trackRegister = when (writeInstruction)", "AudioTrack receiver register extraction")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerC", "FiveRegister receiver register")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister", "range receiver register")
    need(hook, "is FiveRegisterInstruction -> writeInstruction.registerD", "FiveRegister ByteBuffer register")
    need(hook, "is RegisterRangeInstruction -> writeInstruction.startRegister + 1", "range ByteBuffer register")
    need(hook, "observeAudioTrackForStudy(Landroid/media/AudioTrack;)V", "Stage-D track callback")
    need(hook, "observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V", "proven PCM callback")
    need(hook, "invoke-static/range { v$trackRegister .. v$trackRegister }", "single-register track callback")
    need(hook, "invoke-static/range { v$bufferRegister .. v$bufferRegister }", "single-register PCM callback")
    forbid(hook, "LocalSpeakerDiarizer;->onPcmBuffer", "old direct diarizer hook")
    forbid(hook, "v$sizeRegister", "old second size-register injection")

    pcm_callback = between(
        player_volume,
        "public static void observePcmBufferForStudy(ByteBuffer buffer)",
        "public static long getPcmHookCallsForStudy()",
        "Stage-E PCM callback",
    )
    # Previous safe stages stay intact.
    need(pcm_callback, "ByteBuffer view = buffer.duplicate();", "buffer duplicate retained")
    need(pcm_callback, "STUDY_PCM_SAMPLE_STRIDE", "Stage-C sparse byte probe retained")
    need(pcm_callback, "view.get(start + i)", "Stage-C absolute read retained")
    need(pcm_callback, "studyPcmSampleReadErrors++;", "Stage-C fail-soft counter retained")

    # Stage E must really decode PCM16 and produce speech-candidate features.
    need(player_volume, "STUDY_PCM16_ENCODING = 2", "PCM16 format gate")
    need(player_volume, "STUDY_PCM_ANALYSIS_MAX_FRAMES = 2048", "bounded analysis frame count")
    need(player_volume, "STUDY_PCM_VOICE_WINDOW_MS = 1000", "one-second activity window")
    need(player_volume, "STUDY_PCM_VOICE_WINDOW_MIN_ACTIVE_MS = 250", "minimum active speech-candidate time")
    need(pcm_callback, "final int bytesPerFrame = channels * 2;", "PCM16 frame geometry")
    need(pcm_callback, "final int lo = view.get(sampleOffset) & 0xFF;", "little-endian low byte read")
    need(pcm_callback, "final int hi = view.get(sampleOffset + 1);", "little-endian high byte read")
    need(pcm_callback, "final short sample = (short) ((hi << 8) | lo);", "signed PCM16 reconstruction")
    need(pcm_callback, "Math.sqrt(meanSquare)", "RMS feature")
    need(pcm_callback, "zeroCrossings++", "zero-crossing feature")
    need(pcm_callback, "studyPcmVoiceCandidateBuffers++", "voice-candidate counter")
    need(pcm_callback, "studyPcmVoiceActiveWindows++", "active window counter")
    need(pcm_callback, "studyPcmVoiceNoiseFloorPermille", "adaptive noise floor")
    need(pcm_callback, "catch (Throwable ignored)", "fail-soft Stage-E decoder")

    # Keep this stage intentionally lightweight and isolated on the proven class.
    for token, label in (
        ("new byte", "byte-array allocation"),
        ("System.arraycopy", "array copy"),
        ("Thread(", "worker thread creation"),
        ("ThreadPoolExecutor", "executor creation"),
        ("ExecutorService", "executor service"),
        ("PcmSpeakerFeature", "old spectral helper"),
        ("LocalSpeakerDiarizer", "old diarizer class"),
        ("SpeakerAssignmentStore", "speaker assignment"),
        ("FFT", "FFT analysis"),
        ("onnx", "embedding runtime"),
    ):
        forbid(pcm_callback, token, label)

    # Diagnostics for every Stage-E metric must be wired to PlayerVolumePatch getters.
    for getter in (
        "getPcmAnalysisCallsForStudy()", "getPcmAnalysisEligibleBuffersForStudy()",
        "getPcmAnalysisFormatSkipsForStudy()", "getPcmAnalysisDecodeErrorsForStudy()",
        "getPcmAnalysisDecodedFramesForStudy()", "getPcmVoiceCandidateBuffersForStudy()",
        "getPcmVoiceQuietBuffersForStudy()", "getPcmVoiceCandidateMsForStudy()",
        "getPcmVoiceLastRmsPermilleForStudy()", "getPcmVoiceMaxRmsPermilleForStudy()",
        "getPcmVoiceLastPeakPermilleForStudy()", "getPcmVoiceMaxPeakPermilleForStudy()",
        "getPcmVoiceLastZcrPermilleForStudy()", "getPcmVoiceNoiseFloorPermilleForStudy()",
        "getPcmVoiceLastThresholdPermilleForStudy()", "getPcmVoiceWindowsForStudy()",
        "getPcmVoiceActiveWindowsForStudy()", "getPcmVoiceQuietWindowsForStudy()",
        "getPcmVoiceLastWindowCandidateMsForStudy()",
    ):
        need(controller, "PlayerVolumePatch." + getter, "Stage-E diagnostic publication " + getter)

    # Sacred Morphe translation/segmentation invariants.
    need(translator, "OPENROUTER_MAX_BATCH_CHARS = 1_500", "1500-char batch ceiling unchanged")
    need(translator, "OPENROUTER_FIRST_BATCH_CHARS = 350", "350-char first batch unchanged")
    need(fetcher, "private static List<TranscriptSegment> mergeIntoSentences", "stock sentence merger retained")
    need(translator, "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.", "numbered packet contract retained")

    # Stock Morphe volume hooks remain present.
    need(hook, "getAudioMultiplier(F)F", "stock volume hook retained")
    need(hook, "setAudioTrack(Landroid/media/AudioTrack;)V", "stock AudioTrack wrapper observation retained")

    print("v2.32.7 Stage-E audit passed")
    print("Runtime target: stable playback + pcmVoiceEligibleBuffers > 0 + pcmVoiceDecodedFrames > 0 + pcmVoiceDecodeErrors == 0 + pcmVoiceWindows > 0.")
    print("Useful signal target: pcmVoiceCandidateBuffers > 0 and both active/quiet window counts become nonzero on mixed speech/silence material.")


if __name__ == "__main__":
    main()
