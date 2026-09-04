#!/usr/bin/env python3
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise AssertionError(f"missing {label}: {needle}")


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise AssertionError(f"forbidden {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2190_lifecycle_speaker.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

    files = {
        "vot": pkg / "VoiceOverTranslationPatch.java",
        "controller": study / "SpanishStudyController.java",
        "runtime": study / "SpanishStudyRuntimeTelemetry.java",
        "prefs": study / "SpanishStudyPrefs.java",
        "sheet": study / "SpanishStudySheet.java",
        "subtitles": study / "SpanishSubtitleOverlay.java",
        "sidecar": study / "GeminiSpeakerDiarizationSidecar.java",
        "store": study / "SpeakerAssignmentStore.java",
        "voice": pkg / "VoiceCatalog.java",
        "prefetch": pkg / "TtsPrefetcher.java",
        "worker_policy": study / "WorkerLifecyclePolicy.java",
        "tts_policy": study / "TtsStartPolicy.java",
    }
    text = {}
    for key, path in files.items():
        if not path.is_file():
            raise AssertionError(f"missing source {key}: {path}")
        text[key] = path.read_text(encoding="utf-8")

    require(text["vot"], "restartTranscriptAfterLoad", "worker re-arm latch")
    require(text["vot"], "session-enable-while-loading", "session enable restart reason")
    require(text["vot"], "WorkerLifecyclePolicy.shouldRestartAfterFinish", "tested restart policy use")
    require(text["vot"], 'acceptTranslationWorkerCallback(loadEpoch, "progress")', "progress stale gate")
    require(text["vot"], 'acceptTranslationWorkerCallback(loadEpoch, "final")', "final stale gate")
    require(text["vot"], "allowTtsStart(index, speakFromMs, explicitSeekAttempt)", "late TTS start gate")
    require(text["controller"], '"TRANSLATION-WORKER"', "worker lifecycle logs")
    require(text["controller"], '"TTS-TIMING"', "decomposed TTS logs")
    require(text["controller"], '"TTS-LATE-SKIP"', "late TTS skip logs")
    require(text["runtime"], "translationWorkerRestartRequests", "worker restart counter")
    require(text["runtime"], "ttsRepeatedStartAttempts", "repeat TTS counter")
    require(text["runtime"], "ttsLateSkips", "late TTS skip counter")
    require(text["runtime"], "replace((char)10, ' ').replace((char)13, ' ')",
            "compile-safe telemetry newline sanitization")
    require(text["runtime"], "System.lineSeparator()", "compile-safe telemetry diagnostic lines")

    require(text["sidecar"], 'private static final String DIARIZATION_MODEL = "gemini-3.7-flash"', "speaker model")
    require(text["sidecar"], "SpanishStudyPrefs.speakerApiKey(context)", "speaker-only API key")
    require(text["sidecar"], '"SPEAKER-WORKER"', "speaker worker logs")
    require(text["sidecar"], "speakerLastHttpStatus", "speaker HTTP diagnostic")
    require(text["sidecar"], "isSpeakerRequestCurrent(requestEpoch, videoId)", "stale speaker result gate")
    forbid(text["sidecar"], "SpanishStudyPrefs.geminiEnabled", "translation Gemini dependency")
    forbid(text["sidecar"], "Api-Revision", "obsolete Interactions API revision header")
    forbid(text["sidecar"], "RECORD_AUDIO", "microphone permission")
    forbid(text["sidecar"], "AudioRecord", "microphone capture")
    require(text["store"], '"SPEAKER-ASSIGN"', "speaker assignment evidence logs")
    require(text["prefs"], "speaker_recognition_enabled", "speaker recognition preference")
    require(text["prefs"], "gemini_api_key", "historic local key migration")
    require(text["sheet"], "Speaker analysis API key", "speaker key UI")
    require(text["sheet"], "never uses the phone microphone", "speaker privacy UI")
    require(text["subtitles"], "speakerPrefix", "speaker subtitle labels")

    require(text["voice"], "resolveSpeakerVariant", "stable speaker voice variants")
    require(text["vot"], "resolveVoiceForSegment", "speaker-aware playback voice")
    require(text["prefetch"], "resolveVoiceForSegment", "speaker-aware prefetch voice")
    require(text["controller"], "Spanish Dub Study v2.19.0 diagnostics", "diagnostic version")
    require(text["controller"], "speakerBackend=gemini-3.7-flash-youtube-audio-sidecar", "speaker architecture diagnostic")
    require(text["controller"], "speakerMicrophoneAccess=none", "microphone diagnostic")
    require(text["controller"], "deterministic-provider-rearm", "lifecycle architecture diagnostic")

    print("v2.19 lifecycle/speaker audit OK")


if __name__ == "__main__":
    main()
