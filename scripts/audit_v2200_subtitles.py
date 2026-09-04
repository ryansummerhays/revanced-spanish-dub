#!/usr/bin/env python3
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"forbidden {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2200_subtitles.py <morphe-root>")
    root = Path(sys.argv[1])
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    overlay = (study / "SpanishSubtitleOverlay.java").read_text()
    policy = (study / "SubtitlePagePolicy.java").read_text()
    controller = (study / "SpanishStudyController.java").read_text()
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text()
    sidecar = (study / "GeminiSpeakerDiarizationSidecar.java").read_text()
    speaker = (study / "SpeakerAssignmentStore.java").read_text()

    need(policy, "TARGET_WORDS = 10", "bounded word pages")
    need(policy, "TARGET_CHARS = 68", "bounded character pages")
    need(policy, "cleanDisplayText", "display-only cleanup")
    need(policy, "ttsProgress", "TTS progress mapping")
    need(policy, "startProgress", "partial TTS start mapping")

    need(overlay, "setMaxLines(3)", "three-line safety valve")
    forbid(overlay, "setMaxLines(4)", "old four-line clipping policy removed")
    need(overlay, "SubtitlePagePolicy.paginate", "lossless pagination")
    need(overlay, "activeTts.progress(timeMs)", "Spanish pages follow effective TTS")
    need(overlay, "SUBTITLE-PAGE", "page transition diagnostics")
    need(overlay, "speakerPrefix", "speaker labels preserved")

    need(controller, "Spanish Dub Study v2.20.0 diagnostics", "v2.20 diagnostics")
    need(controller, "subtitleLinePolicy=lossless-pagination-10words-68chars+3-line-safety", "subtitle policy diagnostics")
    need(controller, "subtitleProgressSync=tts-window+partial-speech-offset+source-fallback", "subtitle sync diagnostics")
    need(controller, "subtitleTextCleanup=display-only-spacing+punctuation-normalization", "cleanup diagnostics")
    need(controller, "long totalSpeechMs, long remainingSpeechMs", "total/remaining speech bridge")
    need(controller, "SubtitlePagePolicy.startProgress(totalSpeechMs, remainingSpeechMs)", "late-start display alignment")
    need(vot, "speechDurationMs, remainingSpeechMs, rate, explicitSeekAttempt", "Morphe speech duration preserved for display")

    need(sidecar, '.put("processing", "agentic")', "speaker agentic processing")
    forbid(sidecar, '.put("processing", new JSONObject()', "rejected speaker processing object removed")
    forbid(sidecar, '.put("fps",', "custom FPS removed from speaker request")
    need(sidecar, "Inspect the CURRENT WINDOW from", "timestamp-bounded speaker prompt")
    need(speaker, "Use those timestamps as acoustic anchors", "timestamp speaker anchors")

    print("v2.20 subtitle/speaker audit passed")


if __name__ == "__main__":
    main()
