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
    c = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    checks = [
        ("v2.14.1 diagnostics", "Spanish Dub Study v2.14.1 diagnostics" in c),
        ("runtime request telemetry", 'record("PROVIDER-RUNTIME", "request selected="' in t),
        ("runtime exception telemetry", 'record("PROVIDER-RUNTIME", "exception selected="' in t),
        ("null OpenRouter fallback", "null-result google fallback outputs=" in t),
        ("explicit abort state exists", "private static volatile boolean externalAbortRequested;" in t),
        ("requestAbort marks external abort", "externalAbortRequested = true;" in t),
        ("session reset clears external abort", "externalAbortRequested = false;" in t),
        ("null fallback excludes explicit abort/seek", "&& !externalAbortRequested && !reprioritize" in t),
        ("successful Google recovery clears provider abort", "abortTranslation = false;" in t),
        ("normal safe wrapper retained", "translateBatchSafeOriginal" in t),
        ("key configured diagnostic only", "openRouterConfiguredForDiagnostics" in t and "VOT_OPENROUTER_API_KEY.get().trim().isEmpty()" in t),
        ("model diagnostic", "openRouterModelForDiagnostics" in t),
        ("no secret logging", 'VOT_OPENROUTER_API_KEY.get() + ' not in t and '"key=" + Settings.VOT_OPENROUTER_API_KEY' not in t),
        ("provider setting remains authoritative", "String service = Settings.VOT_TRANSLATION_SERVICE.get();" in t),
        ("OpenRouter route remains present", "TranslationProviderPolicy.shouldUseOpenRouter" in t),
        ("Google fallback route remains present", "translateBatchGoogle(videoId, batch, targetLang)" in t),
    ]
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(("PASS" if ok else "FAIL") + ": " + name)
    if failed:
        raise SystemExit("v2.14.1 audit failed: " + ", ".join(failed))
    print(f"v2.14.1 OpenRouter runtime audit: {len(checks)} checks passed")


if __name__ == "__main__":
    main()
