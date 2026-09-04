#!/usr/bin/env python3
"""Final v2.14 audit: provider toggling, fail-forward, and conservative caption speaker evidence."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v214_openrouter_final.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    f = {
        "translator": (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8"),
        "picker": (pkg / "VotBottomSheet.java").read_text(encoding="utf-8"),
        "controller": (study / "SpanishStudyController.java").read_text(encoding="utf-8"),
        "markers": (study / "CaptionSpeakerTurnStore.java").read_text(encoding="utf-8"),
        "named": (study / "CaptionNamedSpeakerStore.java").read_text(encoding="utf-8"),
        "policy": (study / "TranslationProviderPolicy.java").read_text(encoding="utf-8"),
        "gemini": (study / "GeminiTranslator.java").read_text(encoding="utf-8"),
    }

    checks = [
        ("normal Morphe provider authoritative", "String service = Settings.VOT_TRANSLATION_SERVICE.get();" in f["translator"]
            and "final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);" in f["translator"]),
        ("Google provider remains selectable", "TRANSLATION_SERVICE_GOOGLE" in f["picker"]),
        ("MyMemory provider remains selectable", "TRANSLATION_SERVICE_MY_MEMORY" in f["picker"]),
        ("OpenRouter provider remains selectable", "TRANSLATION_SERVICE_OPENROUTER" in f["picker"]),
        ("provider switch persists setting", "Settings.VOT_TRANSLATION_SERVICE.save(value);" in f["picker"]),
        ("provider switch reloads current transcript", "VoiceOverTranslationPatch.reloadTranscript();" in f["picker"]),
        ("OpenRouter uses tested provider policy", "TranslationProviderPolicy.shouldUseOpenRouter" in f["translator"]),
        ("ordinary OpenRouter failure falls to Google", "openrouter failed; google fallback" in f["translator"]
            and "return translateBatchGoogle(videoId, batch, targetLang);" in f["translator"]),
        ("fallback stays latched for session", "openRouterFallbackToGoogle = true;" in f["translator"]
            and "openRouterFallbackToGoogle = false;" in f["translator"]),
        ("fallback uses Google request pacing", "effectiveBatchDelay" in f["translator"]
            and "GOOGLE_INTER_BATCH_DELAY_MS" in f["translator"]),
        ("seek/abort bypass provider fallback", "if (abortTranslation || reprioritize)" in f["translator"]),
        ("selected and effective provider diagnostics", "selectedProvider=" in f["controller"]
            and "effectiveProvider=" in f["controller"]),
        ("Gemini text runtime remains disabled", "public static boolean isEnabled()" in f["gemini"]
            and "return false;" in f["gemini"]),
        ("raw caption cues tracked separately", "ALL_MARKERS_MS" in f["markers"]
            and "markerCount()" in f["markers"]),
        ("hard turns require named caption speaker", "HARD_TURN_STARTS_MS" in f["markers"]
            and "CaptionNamedSpeakerStore.extractName(after) != null" in f["markers"]),
        ("named caption identities preserved", "CaptionNamedSpeakerStore.markTurn" in f["markers"]
            and "speakerIndexAt" in f["named"]),
        ("speaker diagnostics distinguish cue and turn", "captionCueMarkers=" in f["controller"]
            and "captionSpeakerTurns=" in f["controller"]),
        ("speaker boundary mode is conservative", "explicit-labelled-caption-turns-only" in f["controller"]),
        ("provider helper present", "shouldFallbackToGoogle" in f["policy"]),
    ]

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + name)
    if failed:
        raise SystemExit("final v2.14 audit failed: " + ", ".join(failed))
    print(f"final v2.14 audit passed: {len(checks)} invariants")


if __name__ == "__main__":
    main()
