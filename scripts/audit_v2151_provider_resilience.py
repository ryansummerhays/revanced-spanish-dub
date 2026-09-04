#!/usr/bin/env python3
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2151_provider_resilience.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    translator = (pkg / "TranscriptTranslator.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")

    require(translator, 'new JSONObject().put("include", true)', "OpenRouter usage request")
    require(translator, 'X-OpenRouter-Metadata', "OpenRouter router metadata request")
    require(translator, 'optJSONObject("openrouter_metadata")', "OpenRouter router metadata parser")
    require(translator, "boolean[] matchedSlots", "unique line-slot tracking")
    require(translator, "OpenRouterOutputGuard.parseNumberedLine", "guarded numbered output")
    require(translator, "OpenRouterOutputGuard.positionalFallback", "guarded positional output")
    require(translator, "Math.min(matched[0], segmentSize)", "cardinality clamp")
    require(translator, "while (contiguousCount < segmentSize && matchedSlots[contiguousCount])", "contiguous alignment")
    require(translator, "OpenRouter output alignment mismatch", "malformed output fails closed")
    require(translator, "OpenRouterTelemetry.recordSuccess", "OpenRouter usage accounting")
    require(translator, "OpenRouterTelemetry.recordRouterMetadata", "OpenRouter routing accounting")
    require(translator, "googleFallbackBlockedUntilMs", "Google fallback circuit")
    require(translator, "ProviderResiliencePolicy.googleFallbackCooldownMs", "Google 429 cooldown")
    require(translator, "ProviderResiliencePolicy.retryDelayMs", "OpenRouter retry backoff")
    require(translator, "PROVIDER-RECOVERY", "provider recovery diagnostics")
    require(translator, 'service.equals(TRANSLATION_SERVICE_OPENROUTER)', "selected OpenRouter remains primary")
    if "openRouterFallbackToGoogle = true;" in translator:
        raise RuntimeError("persistent Google fallback latch still present")

    require(controller, "Spanish Dub Study v2.15.1 diagnostics", "diagnostic version")
    require(controller, "providerRuntimeTelemetry=v2.15.1", "runtime telemetry version")
    require(controller, "providerRecovery=retry-openrouter+single-google-fallback+google-429-circuit", "recovery policy diagnostic")
    require(controller, "OpenRouterTelemetry.diagnostics()", "copied usage/cost diagnostics")
    require(controller, "OpenRouterTelemetry.resetSession()", "per-video telemetry reset")

    telemetry = (study / "OpenRouterTelemetry.java").read_text(encoding="utf-8")
    for key in (
        "openRouterRequests=", "openRouterPromptTokens=", "openRouterCompletionTokens=",
        "openRouterCostUsd=", "openRouterLastProvider=", "openRouterLastGeneration=",
        "openRouterLastFinishReason=", "openRouterLastRouteStrategy=",
        "openRouterLastRouteAttempts=", "googleFallback429s=",
    ):
        require(telemetry, key, "telemetry field")

    print("v2.15.1 provider resilience audit passed")


if __name__ == "__main__":
    main()
