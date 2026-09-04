#!/usr/bin/env python3
"""v2.17.0 follow-up on the v2.16 Morphe-core reconciliation.

This script assumes patch_v2160_morphe_core.py has already been applied. It keeps Morphe's
segmentation/batching/seek/TTS/cache/prefetch architecture and adds only presentation timing,
semantic language guarding, deduplication telemetry, and lifecycle diagnostics.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def section(path: Path, start_marker: str, end_marker: str):
    text = path.read_text(encoding="utf-8")
    start_at = text.index(start_marker)
    start = text.rfind("\n", 0, start_at) + 1
    end = text.index(end_marker, start_at)
    return text, start, end, text[start:end]


def rep_section(path: Path, start_marker: str, end_marker: str,
                old: str, new: str, label: str, count: int = 1) -> None:
    text, start, end, body = section(path, start_marker, end_marker)
    found = body.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} section anchor(s), found {found}")
    body = body.replace(old, new, count)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched:", label)


def copy_sources(root: Path, overlay: Path) -> None:
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    target.mkdir(parents=True, exist_ok=True)
    for name in (
        "DubLanguageGuard.java",
        "OpenRouterTelemetry.java",
        "SpanishStudyRuntimeTelemetry.java",
        "SpanishStudyController.java",
        "SpanishSubtitleOverlay.java",
    ):
        src = overlay / "app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing v2.17 source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2170_followup.py <morphe-root> <v217-overlay-src>")

    root = Path(sys.argv[1]).resolve()
    overlay = Path(sys.argv[2]).resolve()
    copy_sources(root, overlay)

    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    for path in (vot, translator):
        if not path.is_file():
            raise RuntimeError(f"missing Morphe source: {path}")

    # ------------------------------------------------------------------------------------------
    # Lifecycle epochs: make disable/re-enable/new-video transitions unambiguous in diagnostics.
    # ------------------------------------------------------------------------------------------
    rep(vot,
        '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        SpanishStudyController.onVideoCleared();\n        OpenRouterTelemetry.resetSession();''',
        '''        currentVideoId = videoId;\n        segments = new ArrayList<>();\n        SpanishStudyController.onNewVideo(videoId);\n        OpenRouterTelemetry.resetSession();''',
        "start a diagnostic epoch for each new video")

    rep(vot,
        '''        sessionEnabled = true;\n        Settings.VOT_SESSION_ENABLED.save(true);\n        TtsPrefetcher.triggerRescan();''',
        '''        sessionEnabled = true;\n        Settings.VOT_SESSION_ENABLED.save(true);\n        SpanishStudyController.onSessionEnabled();\n        TtsPrefetcher.triggerRescan();''',
        "record VOT session re-enable epoch")

    # ------------------------------------------------------------------------------------------
    # Last-resort TTS language guard + subtitle window derived from Morphe's own effective timing.
    # ------------------------------------------------------------------------------------------
    rep_section(vot,
        "private static void speak(TranscriptSegment seg, int index)",
        "\n    private static void triggerNextSegmentCheck()",
        '''        String lang = resolveTargetLang();\n        final float volume = Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f;''',
        '''        String lang = resolveTargetLang();\n        if (!SpanishStudyController.allowTts(index, seg.text, lang)) {\n            triggerNextSegmentCheck();\n            return;\n        }\n        final float volume = Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f;''',
        "block English-like text immediately before Spanish TTS")

    rep_section(vot,
        "private static void speak(TranscriptSegment seg, int index)",
        "\n    private static void triggerNextSegmentCheck()",
        '''        ttsEndVideoTimeMs = speakFromMs + (long) (remainingSpeechMs / rate);\n        currentTtsBaseRate = rate;''',
        '''        ttsEndVideoTimeMs = speakFromMs + (long) (remainingSpeechMs / rate);\n        SpanishStudyController.onTtsWindow(index, seg.text, speakFromMs, ttsEndVideoTimeMs,\n                speechDurationMs, rate);\n        currentTtsBaseRate = rate;''',
        "drive Spanish subtitle lifetime from Morphe effective TTS end")

    # ------------------------------------------------------------------------------------------
    # OpenRouter semantic guard: a syntactically valid numbered line can still be English.
    # Reject it before applyBatch() gives it target-language metadata, so native retry handles it.
    # ------------------------------------------------------------------------------------------
    rep(translator,
        '''import app.spanishstudy.vot.DubTextSanitizer;\nimport app.spanishstudy.vot.OpenRouterBudget;''',
        '''import app.spanishstudy.vot.DubTextSanitizer;\nimport app.spanishstudy.vot.DubLanguageGuard;\nimport app.spanishstudy.vot.OpenRouterBudget;''',
        "add OpenRouter language guard import")
    rep(translator,
        '''import app.spanishstudy.vot.OpenRouterTelemetry;\nimport app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        '''import app.spanishstudy.vot.OpenRouterTelemetry;\nimport app.spanishstudy.vot.SpanishStudyController;\nimport app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        "add translation guard diagnostic bridge")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''        OpenRouterTelemetry.recordSuccess(httpCode, System.currentTimeMillis() - start,\n                routedProvider, generationId, finishReason, promptTokens, completionTokens,\n                totalTokens, cachedTokens, usageCostUsd);''',
        '''        for (int i = 0; i < matchedFirst; i++) {\n            String reason = DubLanguageGuard.reason(segments.get(i).text, result.get(i), targetLang);\n            if (reason != null) {\n                SpanishStudyController.recordTranslationGuardReject(i, reason);\n                OpenRouterTelemetry.recordContentReject(httpCode, System.currentTimeMillis() - start,\n                        routedProvider, generationId, finishReason, promptTokens, completionTokens,\n                        totalTokens, cachedTokens, usageCostUsd,\n                        "language-guard slot=" + i + " reason=" + reason);\n                throw new Exception("OpenRouter language guard rejected slot " + i + ": " + reason);\n            }\n        }\n\n        OpenRouterTelemetry.recordSuccess(httpCode, System.currentTimeMillis() - start,\n                routedProvider, generationId, finishReason, promptTokens, completionTokens,\n                totalTokens, cachedTokens, usageCostUsd);''',
        "reject English-like OpenRouter output before publication")

    rep_section(translator,
        "private static List<String> translateBatchOpenRouter(",
        "\n    static void fetchOpenRouterModelCost",
        '''            OpenRouterTelemetry.recordCardinalityMismatch(segmentSize, matched[0]);\n            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize''',
        '''            OpenRouterTelemetry.recordCardinalityMismatch(segmentSize, matched[0]);\n            StringBuilder missingSlots = new StringBuilder();\n            for (int i = 0; i < matchedSlots.length; i++) {\n                if (!matchedSlots[i]) {\n                    if (missingSlots.length() > 0) missingSlots.append(',');\n                    missingSlots.append(i);\n                }\n            }\n            SpanishStudyDiagnostics.record("OPENROUTER-CARDINALITY",\n                    "expected=" + segmentSize + " unique=" + matched[0]\n                            + " contiguous=" + matchedFirst + " missing=" + missingSlots);\n            Logger.printDebug(() -> "OpenRouter line mismatch - expected: " + segmentSize''',
        "log exact missing OpenRouter slots")

    print("v2.17.0 subtitle-sync/language-guard follow-up complete")


if __name__ == "__main__":
    main()
