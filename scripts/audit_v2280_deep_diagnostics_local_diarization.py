#!/usr/bin/env python3
"""Audit v2.28 diagnostic hooks and zero-cost local speaker experiment."""
from __future__ import annotations

import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2280_deep_diagnostics_local_diarization.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    engine = (pkg / "TtsEngine.java").read_text(encoding="utf-8")
    prefetch = (pkg / "TtsPrefetcher.java").read_text(encoding="utf-8")
    cache = (pkg / "TtsCache.java").read_text(encoding="utf-8")
    volume = (root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java").read_text(encoding="utf-8")
    diag = (study / "SpanishStudyDiagnostics.java").read_text(encoding="utf-8")
    prefs = (study / "SpanishStudyPrefs.java").read_text(encoding="utf-8")
    local = (study / "LocalSpeakerDiarizer.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    overlay = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
    sheet = (study / "SpanishStudySheet.java").read_text(encoding="utf-8")

    # Preserve the Morphe behavior the user wants.
    require(fetcher, "mergeIntoSentences(lines)", "stock sentence merging retained")
    forbid(fetcher, "splitIntoStudyClauses", "no study speech resegmentation")
    forbid(fetcher, "SemanticClauseSplitter", "no semantic speech resegmentation")
    require(translator, "private static final int OPENROUTER_MAX_BATCH_CHARS = 1_500", "stock OpenRouter batch size")
    require(translator, "private static final int OPENROUTER_FIRST_BATCH_CHARS = 350", "stock OpenRouter first batch")
    require(translator, ".put(\"sort\", \"latency\")", "stock OpenRouter latency routing")
    require(translator, ".put(\"temperature\", 0)", "stock OpenRouter temperature")
    require(vot, "final float rate = calculateSpeechRate(remainingSpeechMs, availableMs);", "stock speech rate decision")
    require(vot, "Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f", "stock max speech rate")
    require(engine, "adjustPlaybackTimes(List<TranscriptSegment> segments", "stock playback-window adjustment")
    require(prefetch, "DISTANCE_IMMEDIATE_MS = 30_000", "stock prefetch policy")
    require(cache, "Utils.createSizeRestrictedMap(1000)", "stock TTS cache size")

    # Deep component-selectable diagnostics.
    for category in ["LIFECYCLE", "CAPTIONS", "TRANSLATION", "TTS", "SUBTITLES", "AUDIO", "SPEAKER"]:
        require(diag, f'public static final String {category}', f"diagnostic category {category}")
    require(diag, "MAX_LINES = 3000", "large bounded diagnostic ring")
    require(prefs, "diag_include_text", "optional transcript text logging")
    require(sheet, "Diagnostic components", "diagnostic settings UI")
    require(sheet, "Translation / OpenRouter", "translation log toggle")
    require(sheet, "TTS / prefetch / cache", "TTS log toggle")
    require(sheet, "Audio capture", "audio log toggle")
    require(sheet, "Speaker clustering", "speaker log toggle")
    require(translator, "OpenRouter stream complete expected=", "OpenRouter cardinality telemetry")
    require(vot, "predictedEnd=", "TTS timing telemetry")
    require(engine, "MediaPlayer actual start id=", "actual audio-start telemetry")
    require(prefetch, "prefetch success index=", "prefetch telemetry")
    require(cache, "cache get index=", "cache telemetry")

    # The diarization experiment must be local and free.
    require(local, "android.media.audiofx.Visualizer", "Android Visualizer source-audio capture")
    require(local, "speakerApiCostUsd=0.000000", "zero remote speaker API cost")
    require(local, "speakerMicrophoneAccess=none-audiotrack-session-only", "no microphone design")
    require(local, "SECOND_SPEAKER_THRESHOLD", "speaker cluster threshold")
    require(local, "onFftDataCapture", "FFT speaker features")
    require(volume, "LocalSpeakerDiarizer.onAudioTrack(track)", "existing AudioTrack hook reused")
    require(controller, "LocalSpeakerDiarizer.setSourceSegments", "speaker timeline hookup")
    require(overlay, "LocalSpeakerDiarizer.labelForSegment", "visible A/B speaker labels")
    require(overlay, '"[" + speaker + "]"', "separate bracket speaker badge")
    forbid(local, "HttpURLConnection", "no diarization network connection")
    forbid(local, "openrouter.ai", "no OpenRouter diarization")
    forbid(local, "generativelanguage", "no Gemini diarization")

    # Make sure old paid/remote speaker components are not copied into the build.
    for name in ["GeminiSpeakerDiarizationSidecar.java", "SpeakerAssignmentStore.java", "SpeakerNamePolicy.java"]:
        if study.joinpath(name).exists():
            raise RuntimeError(f"old remote speaker component packaged: {name}")
        print("ok: old remote speaker component absent:", name)

    # Old flow/recovery experiments must not return.
    combined = "\n".join([fetcher, translator, vot, engine, prefetch, controller])
    for needle in ["whole-native-batch-google-on-integrity", "split-first", "ttsLateStartPolicy=source-end", "speakerPrimaryModel=google/"]:
        forbid(combined, needle, f"old experiment absent: {needle}")

    print("v2.28 deep diagnostics + local diarization audit passed")


if __name__ == "__main__":
    main()
