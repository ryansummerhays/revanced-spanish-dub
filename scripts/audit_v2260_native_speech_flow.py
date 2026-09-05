#!/usr/bin/env python3
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
        raise SystemExit("usage: audit_v2260_native_speech_flow.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    sidecar = (study / "GeminiSpeakerDiarizationSidecar.java").read_text(encoding="utf-8")

    # Morphe owns speech scheduling/rate/seek. Our subtitle code may observe it only.
    forbid(vot, "SpanishStudyController.allowTtsStart(index", "custom TTS start gate removed")
    need(vot, "final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);", "stock speak-from calculation retained")
    need(vot, "final float rate = calculateSpeechRate(remainingSpeechMs, availableMs);", "stock slot-fit speech-rate calculation retained")
    need(vot, "ttsEndVideoTimeMs = speakFromMs + (long) (remainingSpeechMs / rate);", "stock TTS end calculation retained")
    need(vot, "final float playbackRate = rate * VideoInformation.getPlaybackSpeed();", "stock playback-speed multiplication retained")
    need(vot, "subtitleAudioStarted, VoiceOverTranslationPatch::triggerNextSegmentCheck", "subtitle observer remains attached to Edge playback")

    # Deterministic model-integrity failures fail forward once instead of serial resplitting.
    need(translator, "integrity-whole-native-batch", "whole native batch integrity fallback")
    forbid(translator, "action=split-first", "serial split-first recovery removed")
    need(translator, "transport-after-one-retry", "one transport retry policy retained")
    need(translator, "fallbackGoogleAfterOpenRouter", "existing Google fallback retained")

    # 402 is a pre-inference balance gate and must not produce periodic retries.
    need(sidecar, "private static boolean terminalBlocked;", "terminal speaker state")
    need(sidecar, "if (analysisComplete || terminalBlocked || inFlight", "terminal reschedule gate")
    need(sidecar, "if (lastHttpStatus == 402)", "HTTP 402 classifier")
    need(sidecar, "backoffUntilWallMs = Long.MAX_VALUE;", "terminal current-video backoff")
    need(sidecar, "speakerTerminalBlocked=", "terminal state diagnostics")
    need(sidecar, "$1 balance required", "actionable speaker status")

    need(controller, "Spanish Dub Study v2.26.0 diagnostics", "v2.26 diagnostics")
    need(controller, "speechFlowAuthority=morphe-v1.41.0-native-speak+rate+seek+edge-cache-prefetch", "native speech authority diagnostic")
    need(controller, "whole-native-batch-google-on-integrity", "flow-priority recovery diagnostic")
    need(controller, "diagnostic-only-no-custom-start-gate", "late-start observer diagnostic")

    print("v2.26 native speech flow audit: OK")


if __name__ == "__main__":
    main()
