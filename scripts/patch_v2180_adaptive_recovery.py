#!/usr/bin/env python3
"""v2.18.0: bounded adaptive OpenRouter recovery on top of v2.17.

The v2.17 diagnostics exposed a deterministic no-prefix cardinality failure that could retry the
same batch forever. This follow-up keeps Morphe's native batching, streaming, seek reprioritization,
and provider setting, while changing only the non-fatal OpenRouter recovery state machine.
"""
from __future__ import annotations

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
                old: str, new: str, label: str) -> None:
    text, start, end, body = section(path, start_marker, end_marker)
    found = body.count(old)
    if found != 1:
        raise RuntimeError(f"{label}: expected one section anchor, found {found}")
    body = body.replace(old, new, 1)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2180_adaptive_recovery.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    if not translator.is_file():
        raise RuntimeError(f"missing v2.17 translator: {translator}")

    # translateBatchSafe() necessarily converts exceptions to null for Morphe's caller. Preserve one
    # bit of classification so translate() can distinguish deterministic output-integrity failures
    # from transient transport/provider failures.
    rep(translator,
        '''    private static volatile boolean reprioritize;\n    // Session state published while translate() runs''',
        '''    private static volatile boolean reprioritize;\n    private static volatile boolean lastOpenRouterFailureWasIntegrity;\n    // Session state published while translate() runs''',
        "publish OpenRouter failure classification")

    rep_section(translator, "static List<TranscriptSegment> translate(",
                "\n    private static boolean[] toBoolArray",
        '''        int completed = 0;\n        int consecutiveOpenRouterFailures = 0;''',
        '''        int completed = 0;\n        int consecutiveOpenRouterTransportFailures = 0;''',
        "track transport failures separately")

    rep_section(translator, "static List<TranscriptSegment> translate(",
                "\n    private static boolean[] toBoolArray",
        '''                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,''',
        '''                List<String> translated = translateBatchSafe(videoId, batch, targetLang,''',
        "make failed result replaceable by recovery")

    old_recovery = '''                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    consecutiveOpenRouterFailures++;\n                    long delayMs = Math.min(15_000L, 1_000L << Math.min(4, consecutiveOpenRouterFailures - 1));\n                    SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                            "retry same native Morphe batch failures=" + consecutiveOpenRouterFailures\n                                    + " delayMs=" + delayMs);\n                    try {\n                        Thread.sleep(delayMs);\n                    } catch (InterruptedException ex) {\n                        Thread.currentThread().interrupt();\n                        return initial;\n                    }\n                    continue;\n                }\n                if (translated != null) consecutiveOpenRouterFailures = 0;\n'''

    new_recovery = '''                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    if (lastOpenRouterFailureWasIntegrity) {\n                        consecutiveOpenRouterTransportFailures = 0;\n\n                        // A deterministic no-prefix failure cannot improve by resending the same\n                        // list forever. Isolate its first slot and leave the remaining contiguous\n                        // tail as normal Morphe work. The observed 5-item failure therefore becomes\n                        // 1 + 4 instead of 5 -> 5 -> 5 ... forever.\n                        if (batch.size() > 1) {\n                            final int failedSize = batch.size();\n                            List<TranscriptSegment> first = new ArrayList<>(batch.subList(0, 1));\n                            List<TranscriptSegment> tail = new ArrayList<>(batch.subList(1, failedSize));\n                            batches.set(index, first);\n                            batches.add(index + 1, tail);\n                            batchDone.add(index + 1, false);\n                            liveBatches = new ArrayList<>(batches);\n                            TranscriptSegment source = batch.get(0);\n                            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                                    "action=split-first failedBatchSize=" + failedSize\n                                            + " head=1 tail=" + tail.size()\n                                            + " firstSourceChars=" + source.text.length()\n                                            + " firstSourceHash=" + Integer.toHexString(source.text.hashCode()));\n                            continue;\n                        }\n\n                        // Once isolated to one segment there is nothing left to split. Use the\n                        // existing Google translator for this segment only, without changing the\n                        // user's selected OpenRouter provider.\n                        translated = fallbackGoogleAfterOpenRouter(\n                                videoId, batch, targetLang, "singleton-integrity");\n                    } else {\n                        consecutiveOpenRouterTransportFailures++;\n                        if (consecutiveOpenRouterTransportFailures == 1) {\n                            final long delayMs = 1_000L;\n                            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                                    "action=retry-transport-once batchSize=" + batch.size()\n                                            + " delayMs=" + delayMs);\n                            try {\n                                Thread.sleep(delayMs);\n                            } catch (InterruptedException ex) {\n                                Thread.currentThread().interrupt();\n                                return initial;\n                            }\n                            continue;\n                        }\n\n                        // A second consecutive transport/provider failure also must not hold the\n                        // translator hostage. Fail forward through Google for this native batch.\n                        translated = fallbackGoogleAfterOpenRouter(\n                                videoId, batch, targetLang, "transport-after-one-retry");\n                        consecutiveOpenRouterTransportFailures = 0;\n                    }\n                }\n                if (translated != null) consecutiveOpenRouterTransportFailures = 0;\n'''

    rep_section(translator, "static List<TranscriptSegment> translate(",
                "\n    private static boolean[] toBoolArray",
                old_recovery, new_recovery,
                "replace unbounded retry loop with adaptive recovery")

    helpers = r'''    private static boolean isOpenRouterIntegrityFailure(Exception ex) {
        String message = ex.getMessage();
        if (message == null) return false;
        return message.startsWith("OpenRouter output alignment mismatch")
                || message.startsWith("OpenRouter language guard rejected slot")
                || message.startsWith("OpenRouter output truncated at max token budget");
    }

    @Nullable
    private static List<String> fallbackGoogleAfterOpenRouter(String videoId,
                                                               List<TranscriptSegment> batch,
                                                               String targetLang,
                                                               String reason) {
        TranscriptSegment source = batch.get(0);
        SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                "action=google-fallback reason=" + reason + " batchSize=" + batch.size()
                        + " firstSourceChars=" + source.text.length()
                        + " firstSourceHash=" + Integer.toHexString(source.text.hashCode()));
        try {
            List<String> fallback = translateBatchGoogle(videoId, batch, targetLang);
            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                    "action=google-fallback-success reason=" + reason + " batchSize=" + batch.size());
            return fallback;
        } catch (Exception ex) {
            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                    "action=google-fallback-failed reason=" + reason + " batchSize=" + batch.size());
            Logger.printDebug(() -> "Google recovery fallback failed", ex);
            return null;
        }
    }

'''
    rep(translator,
        "    private static boolean[] toBoolArray(List<Boolean> source) {\n",
        helpers + "    private static boolean[] toBoolArray(List<Boolean> source) {\n",
        "add recovery classifier and Google fallback helper")

    rep_section(translator, "private static List<String> translateBatchSafe(",
                "\n    private static int findBatchAtTime",
        '''        try {\n            return translateBatch(videoId, batch, targetLang, onLineStreamed);\n        } catch (Exception ex) {''',
        '''        lastOpenRouterFailureWasIntegrity = false;\n        try {\n            return translateBatch(videoId, batch, targetLang, onLineStreamed);\n        } catch (Exception ex) {\n            if (Settings.VOT_TRANSLATION_SERVICE.get().equals(TRANSLATION_SERVICE_OPENROUTER)) {\n                lastOpenRouterFailureWasIntegrity = isOpenRouterIntegrityFailure(ex);\n            }''',
        "classify OpenRouter failure before it is swallowed")

    print("v2.18.0 adaptive OpenRouter recovery complete")


if __name__ == "__main__":
    main()
