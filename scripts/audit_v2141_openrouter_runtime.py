#!/usr/bin/env python3
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2141_openrouter_runtime.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    t = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    v = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    c = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    q = (study / "TranslationQualityLog.java").read_text(encoding="utf-8")
    r = (study / "OpenRouterRecoveryPolicy.java").read_text(encoding="utf-8")
    s = (study / "SessionTogglePolicy.java").read_text(encoding="utf-8")
    checks = [
        ("v2.14.1 diagnostics", "Spanish Dub Study v2.14.1 diagnostics" in c),
        ("runtime request telemetry", 'record("PROVIDER-RUNTIME", "request selected="' in t),
        ("runtime exception telemetry", 'record("PROVIDER-RUNTIME", "exception selected="' in t),
        ("null OpenRouter fallback", "null-result google fallback outputs=" in t),
        ("explicit abort state exists", "private static volatile boolean externalAbortRequested;" in t),
        ("requestAbort marks external abort", "externalAbortRequested = true;" in t),
        ("session reset clears external abort", "externalAbortRequested = false;" in t),
        ("tested recovery helper used", "OpenRouterRecoveryPolicy.shouldFallbackToGoogle" in t and "shouldFallbackToGoogle" in r),
        ("successful Google recovery clears provider abort", "abortTranslation = false;" in t),
        ("normal safe wrapper retained", "translateBatchSafeOriginal" in t),
        ("key configured diagnostic only", "openRouterConfiguredForDiagnostics" in t and "VOT_OPENROUTER_API_KEY.get().trim().isEmpty()" in t),
        ("model diagnostic", "openRouterModelForDiagnostics" in t),
        ("no secret logging", 'VOT_OPENROUTER_API_KEY.get() + ' not in t and '"key=" + Settings.VOT_OPENROUTER_API_KEY' not in t),
        ("provider setting remains authoritative", "String service = Settings.VOT_TRANSLATION_SERVICE.get();" in t),
        ("OpenRouter route remains present", "TranslationProviderPolicy.shouldUseOpenRouter" in t),
        ("Google fallback route remains present", "translateBatchGoogle(videoId, batch, targetLang)" in t),
        ("quality logger imported", "TranslationQualityLog" in t),
        ("quality captures source and translated", "seg.text, target" in t),
        ("quality captures timing", "seg.startMs, seg.endMs" in t),
        ("quality captures provider/model", "recordTranslationQuality" in t and "VOT_OPENROUTER_MODEL" in t),
        ("quality trace separate bounded buffer", "MAX_PAIRS = 120" in q and "Deque<String> PAIRS" in q),
        ("quality source/target labels", '" | EN: "' in q and '" || ES: "' in q),
        ("quality report copied after events", "--- translation quality (recent 120 pairs) ---" in c),
        ("explicit user toggle uses tested policy", "SessionTogglePolicy.nextStateForUserPress" in v and "nextStateForUserPress" in s),
        ("user OFF not suppressed during loading", "player tap while loading; kept enabled" not in v),
        ("user toggle telemetry", '"user button requested "' in v and '" loading=" + isLoading' in v),
        ("automatic policy is enable-only", "nextStateForAutomaticStart" in s and "return true;" in s),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + ": " + name)
    if failed:
        raise SystemExit("v2.14.1 audit failed: " + ", ".join(failed))
    print(f"v2.14.1 OpenRouter runtime/quality/session audit: {len(checks)} checks passed")


if __name__ == "__main__":
    main()
