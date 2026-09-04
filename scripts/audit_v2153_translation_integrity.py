#!/usr/bin/env python3
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2153_translation_integrity.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    sheet = (study / "SpanishStudySheet.java").read_text(encoding="utf-8")
    sanitizer = (study / "DubTextSanitizer.java").read_text(encoding="utf-8")
    planner = (study / "RealtimeTranslationPlanner.java").read_text(encoding="utf-8")
    telemetry = (study / "OpenRouterTelemetry.java").read_text(encoding="utf-8")

    require(translator, "DubTextSanitizer.cleanForSpeech", "provider output sanitizer")
    require(translator, "TRANSLATION-SANITIZE", "sanitizer diagnostics")
    require(translator, "RealtimeTranslationPlanner.openRouterMaxOutputTokens", "dynamic output budget")
    require(translator, '.put("max_tokens", maxOutputTokens)', "dynamic max_tokens request")
    require(translator, '" finish=" + finishReason + " maxTokens=" + maxOutputTokens', "per-request finish logging")
    require(translator, '!"length".equalsIgnoreCase(finishReason)', "length-tail suppression")
    require(translator, "OpenRouter output truncated at max token budget", "length response rejection")
    if '.put("max_tokens", segments.size() * 30)' in translator:
        raise RuntimeError("old 30-token-per-segment OpenRouter cap still present")

    require(vot, "TTS-SANITIZE", "final TTS firewall diagnostics")
    require(vot, "DubTextSanitizer.cleanForSpeech(seg.text)", "final TTS firewall")
    require(vot, "blocked residual protocol metadata", "fail-closed contaminated TTS")
    require(vot, "pendingSpeechIndex == index", "TTS firewall releases reservation")
    require(vot, "onDubPlaybackSkipped(seg, index)", "TTS firewall advances skipped event")

    require(controller, "return false;", "speaker routing hard off")
    require(controller, "Spanish Dub Study v2.15.3 diagnostics", "diagnostic version")
    require(controller, "providerRuntimeTelemetry=v2.15.3", "runtime telemetry version")
    require(controller, "translationOutputSanitizer=batch-enum+slot-duration+timestamp-firewall", "sanitizer diagnostic")
    require(controller, "openRouterOutputBudget=dynamic-192-640-tokens", "output budget diagnostic")
    require(controller, "speakerVoiceRouting=disabled-no-local-audio-backend", "speaker routing diagnostic")
    require(controller, "SpeakerAssignmentStore.profileSummary()", "speaker profile diagnostic")
    require(controller, "votRuntimeLifecycle=session-gated-no-provider-work-while-off", "v2.15.2 lifecycle preserved")

    require(sheet, "Speaker recognition — unavailable", "honest speaker recognition UI")
    require(sheet, "Per-speaker voices — unavailable", "honest speaker voice UI")

    require(sanitizer, "LEADING_BATCH_ENUM", "batch numbering strip")
    require(sanitizer, "BRACKET_DURATION_PREFIX", "seconds metadata strip")
    require(sanitizer, "TIMESTAMP_ECHO", "raw timestamp rejection")
    require(planner, "openRouterMaxOutputTokens", "planner output budget helper")
    require(telemetry, "openRouterFinishLengthCount=", "finish-length telemetry")

    print("v2.15.3 translation integrity audit passed")


if __name__ == "__main__":
    main()
