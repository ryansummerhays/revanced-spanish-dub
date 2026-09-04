#!/usr/bin/env python3
"""Audit v2.14.0 provider, TTS reliability, and conservative speaker-marker integration."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v214_tts_failover_marker_confidence.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    files = {
        "vot": (votpkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8"),
        "prefetch": (votpkg / "TtsPrefetcher.java").read_text(encoding="utf-8"),
        "translator": (votpkg / "TranscriptTranslator.java").read_text(encoding="utf-8"),
        "fetcher": (votpkg / "TranscriptFetcher.java").read_text(encoding="utf-8"),
        "controller": (study / "SpanishStudyController.java").read_text(encoding="utf-8"),
        "markers": (study / "CaptionSpeakerTurnStore.java").read_text(encoding="utf-8"),
        "policy": (study / "EdgeReliabilityPolicy.java").read_text(encoding="utf-8"),
        "provider_policy": (study / "TranslationProviderPolicy.java").read_text(encoding="utf-8"),
        "gemini": (study / "GeminiTranslator.java").read_text(encoding="utf-8"),
    }

    checks = [
        ("v2.14 diagnostics label", "Spanish Dub Study v2.14.0 diagnostics" in files["controller"]),
        ("native provider authority exposed", "translationMode=morphe-native-provider" in files["controller"]
            and "providerAuthority=normal-morphe-setting" in files["controller"]),
        ("OpenRouter Google fallback exposed", "translationFallback=google-on-openrouter-failure" in files["controller"]),
        ("normal Morphe provider restored", "String service = Settings.VOT_TRANSLATION_SERVICE.get();" in files["translator"]
            and "final boolean isOpenRouter = service.equals(TRANSLATION_SERVICE_OPENROUTER);" in files["translator"]),
        ("tested provider policy wired", "TranslationProviderPolicy.shouldUseOpenRouter" in files["translator"]
            and "TranslationProviderPolicy.shouldFallbackToGoogle" in files["translator"]),
        ("OpenRouter fallback latched per session", "openRouterFallbackToGoogle" in files["translator"]
            and "openRouterFallbackToGoogle = false;" in files["translator"]
            and "openRouterFallbackToGoogle = true;" in files["translator"]),
        ("OpenRouter failure actually calls Google", "openrouter failed; google fallback" in files["translator"]
            and "return translateBatchGoogle(videoId, batch, targetLang);" in files["translator"]),
        ("seek or abort does not trigger provider fallback", "if (abortTranslation || reprioritize)" in files["translator"]),
        ("first OpenRouter slice remains small", "OPENROUTER_FIRST_BATCH_CHARS" in files["translator"]
            and "isOpenRouter ? OPENROUTER_FIRST_BATCH_CHARS : GOOGLE_FIRST_BATCH_CHARS" in files["translator"]),
        ("Gemini text runtime stays disabled", "public static boolean isEnabled()" in files["gemini"]
            and "return false;" in files["gemini"]),
        ("native failover policy exposed", "ttsFailover=edge-prefetched-native-offline-active-miss" in files["controller"]),
        ("native TTS warmed on session", "SpanishStudyController.onSessionEnabled();\n        ensureTts();" in files["vot"]),
        ("native TTS warmed on active video", "warm the local/native reliability floor" in files["vot"]),
        ("active Edge cache miss fails forward", "useNativeForActiveCacheMiss" in files["vot"]
            and "edge-cache-miss" in files["vot"]),
        ("fallback requires offline Spanish voice", "isNetworkConnectionRequired()" in files["vot"]
            and "no-offline-spanish-voice" in files["vot"]),
        ("Edge failure can fail forward", "edge-failure-" in files["vot"]),
        ("prefetch failures tracked", "failedAttemptsByIndex" in files["prefetch"]),
        ("poisoned prefetch slot suppressed", "suppressed index=" in files["prefetch"]
            and "isPrefetchSuppressed(next.index)" in files["prefetch"]),
        ("raw markers separated from speaker turns", "ALL_MARKERS_MS" in files["markers"]
            and "HARD_TURN_STARTS_MS" in files["markers"]
            and "markerCount()" in files["markers"]),
        ("bare markers no longer hard speaker boundaries", "hasExplicitSpeakerLabel" in files["markers"]
            and "HARD_TURN_STARTS_MS.add" in files["markers"]),
        ("phrase diagnostics separate cue and turn counts", "cueMarkers=" in files["fetcher"]
            and "speakerTurns=" in files["fetcher"]),
        ("speaker boundary mode is confidence-labelled", "explicit-labelled-caption-turns-only" in files["controller"]),
        ("Edge policy helper copied into extension", "PREFETCH_FAILURES_BEFORE_SUPPRESS = 3" in files["policy"]),
        ("provider policy helper copied into extension", "shouldFallbackToGoogle" in files["provider_policy"]),
    ]

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + " - " + name)
    if failed:
        raise SystemExit("v2.14 audit failed: " + ", ".join(failed))
    print(f"v2.14 audit passed: {len(checks)} invariants")


if __name__ == "__main__":
    main()
