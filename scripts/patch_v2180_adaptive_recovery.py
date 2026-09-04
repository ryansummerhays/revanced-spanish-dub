#!/usr/bin/env python3
"""v2.18.0: bounded adaptive OpenRouter recovery on top of v2.17."""
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
    if body.count(old) != 1:
        raise RuntimeError(f"{label}: expected one section anchor, found {body.count(old)}")
    body = body.replace(old, new, 1)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2180_adaptive_recovery.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    telemetry = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/OpenRouterTelemetry.java"
    for path in (translator, telemetry):
        if not path.is_file():
            raise RuntimeError(f"missing v2.17 source: {path}")

    # Classify the exception swallowed by translateBatchSafe so deterministic output failures can
    # recover differently from temporary transport/provider failures.
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

    old = '''                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    consecutiveOpenRouterFailures++;\n                    long delayMs = Math.min(15_000L, 1_000L << Math.min(4, consecutiveOpenRouterFailures - 1));\n                    SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                            "retry same native Morphe batch failures=" + consecutiveOpenRouterFailures\n                                    + " delayMs=" + delayMs);\n                    try {\n                        Thread.sleep(delayMs);\n                    } catch (InterruptedException ex) {\n                        Thread.currentThread().interrupt();\n                        return initial;\n                    }\n                    continue;\n                }\n                if (translated != null) consecutiveOpenRouterFailures = 0;\n'''
    new = '''                if (translated == null && isOpenRouter && !abortTranslation && !reprioritize) {\n                    if (lastOpenRouterFailureWasIntegrity) {\n                        consecutiveOpenRouterTransportFailures = 0;\n                        if (batch.size() > 1) {\n                            final int failedSize = batch.size();\n                            List<TranscriptSegment> head = new ArrayList<>(batch.subList(0, 1));\n                            List<TranscriptSegment> tail = new ArrayList<>(batch.subList(1, failedSize));\n                            batches.set(index, head);\n                            batches.add(index + 1, tail);\n                            batchDone.add(index + 1, false);\n                            liveBatches = new ArrayList<>(batches);\n                            OpenRouterTelemetry.recordRecoverySplit(failedSize, tail.size());\n                            TranscriptSegment first = batch.get(0);\n                            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                                    "action=split-first failedBatchSize=" + failedSize\n                                            + " head=1 tail=" + tail.size()\n                                            + " firstSourceChars=" + first.text.length()\n                                            + " firstSourceHash=" + Integer.toHexString(first.text.hashCode()));\n                            continue;\n                        }\n                        translated = fallbackGoogleAfterOpenRouter(\n                                videoId, batch, targetLang, "singleton-integrity");\n                    } else {\n                        consecutiveOpenRouterTransportFailures++;\n                        if (consecutiveOpenRouterTransportFailures == 1) {\n                            final long delayMs = 1_000L;\n                            OpenRouterTelemetry.recordTransportRetry(delayMs);\n                            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",\n                                    "action=retry-transport-once batchSize=" + batch.size()\n                                            + " delayMs=" + delayMs);\n                            try {\n                                Thread.sleep(delayMs);\n                            } catch (InterruptedException ex) {\n                                Thread.currentThread().interrupt();\n                                return initial;\n                            }\n                            continue;\n                        }\n                        translated = fallbackGoogleAfterOpenRouter(\n                                videoId, batch, targetLang, "transport-after-one-retry");\n                        consecutiveOpenRouterTransportFailures = 0;\n                    }\n                }\n                if (translated != null) consecutiveOpenRouterTransportFailures = 0;\n'''
    rep_section(translator, "static List<TranscriptSegment> translate(",
                "\n    private static boolean[] toBoolArray", old, new,
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
        OpenRouterTelemetry.recordGoogleFallbackAttempt(reason);
        TranscriptSegment first = batch.get(0);
        SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                "action=google-fallback reason=" + reason + " batchSize=" + batch.size()
                        + " firstSourceChars=" + first.text.length()
                        + " firstSourceHash=" + Integer.toHexString(first.text.hashCode()));
        try {
            List<String> fallback = translateBatchGoogle(videoId, batch, targetLang);
            OpenRouterTelemetry.recordGoogleFallbackSuccess();
            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                    "action=google-fallback-success reason=" + reason + " batchSize=" + batch.size());
            return fallback;
        } catch (Exception ex) {
            OpenRouterTelemetry.recordGoogleFallbackFailure(ex.getMessage());
            SpanishStudyDiagnostics.record("OPENROUTER-RECOVERY",
                    "action=google-fallback-failed reason=" + reason + " batchSize=" + batch.size());
            Logger.printDebug(() -> "Google recovery fallback failed", ex);
            return null;
        }
    }

'''
    rep(translator, "    private static boolean[] toBoolArray(List<Boolean> source) {\n",
        helpers + "    private static boolean[] toBoolArray(List<Boolean> source) {\n",
        "add recovery classifier and Google fallback helper")

    rep_section(translator, "private static List<String> translateBatchSafe(",
                "\n    private static int findBatchAtTime",
        '''        try {\n            return translateBatch(videoId, batch, targetLang, onLineStreamed);\n        } catch (Exception ex) {''',
        '''        lastOpenRouterFailureWasIntegrity = false;\n        try {\n            return translateBatch(videoId, batch, targetLang, onLineStreamed);\n        } catch (Exception ex) {\n            if (Settings.VOT_TRANSLATION_SERVICE.get().equals(TRANSLATION_SERVICE_OPENROUTER)) {\n                lastOpenRouterFailureWasIntegrity = isOpenRouterIntegrityFailure(ex);\n            }''',
        "classify OpenRouter failure before it is swallowed")

    # Extend the existing session telemetry rather than adding another runtime owner.
    rep(telemetry,
        '''    private static long finishLengthCount;\n    private static int lastHttpStatus;''',
        '''    private static long finishLengthCount;\n    private static long recoverySplits;\n    private static long transportRetries;\n    private static long googleFallbackAttempts;\n    private static long googleFallbackSucceeded;\n    private static long googleFallbackFailed;\n    private static int lastHttpStatus;''',
        "add recovery counters")
    rep(telemetry,
        '''    private static String lastError = "none";''',
        '''    private static String lastError = "none";\n    private static String lastRecovery = "none";''',
        "add last recovery summary")
    rep(telemetry,
        '''        cardinalityMismatches = finishLengthCount = 0;\n        lastHttpStatus = 0;''',
        '''        cardinalityMismatches = finishLengthCount = 0;\n        recoverySplits = transportRetries = 0;\n        googleFallbackAttempts = googleFallbackSucceeded = googleFallbackFailed = 0;\n        lastHttpStatus = 0;''',
        "reset recovery counters")
    rep(telemetry,
        '''        lastError = "none";\n    }''',
        '''        lastError = "none";\n        lastRecovery = "none";\n    }''',
        "reset last recovery", count=1)

    recovery_methods = r'''
    public static synchronized void recordRecoverySplit(int failedSize, int tailSize) {
        recoverySplits++;
        lastRecovery = "split " + failedSize + "->1+" + tailSize;
    }

    public static synchronized void recordTransportRetry(long delayMs) {
        transportRetries++;
        lastRecovery = "transport-retry " + Math.max(0L, delayMs) + "ms";
    }

    public static synchronized void recordGoogleFallbackAttempt(String reason) {
        googleFallbackAttempts++;
        lastRecovery = "google-fallback " + compact(reason);
    }

    public static synchronized void recordGoogleFallbackSuccess() {
        googleFallbackSucceeded++;
        lastRecovery = "google-fallback success";
    }

    public static synchronized void recordGoogleFallbackFailure(String error) {
        googleFallbackFailed++;
        lastRecovery = "google-fallback failed " + compact(error);
    }

'''
    rep(telemetry,
        "    private static void updateRequestMetadata(int httpStatus, long latencyMs,\n",
        recovery_methods + "    private static void updateRequestMetadata(int httpStatus, long latencyMs,\n",
        "add recovery telemetry methods")

    rep(telemetry,
        '''                + "openRouterFinishLengthCount=" + finishLengthCount + '\\n'\n                + "openRouterLastHttpStatus=" + lastHttpStatus + '\\n' ''',
        '''                + "openRouterFinishLengthCount=" + finishLengthCount + '\\n'\n                + "openRouterRecoverySplits=" + recoverySplits + '\\n'\n                + "openRouterTransportRetries=" + transportRetries + '\\n'\n                + "openRouterGoogleFallbackAttempts=" + googleFallbackAttempts + '\\n'\n                + "openRouterGoogleFallbackSucceeded=" + googleFallbackSucceeded + '\\n'\n                + "openRouterGoogleFallbackFailed=" + googleFallbackFailed + '\\n'\n                + "openRouterLastHttpStatus=" + lastHttpStatus + '\\n' ''',
        "publish recovery counters")
    rep(telemetry,
        '''                + "openRouterLastError=" + lastError + '\\n';''',
        '''                + "openRouterLastError=" + lastError + '\\n'\n                + "openRouterLastRecovery=" + lastRecovery + '\\n';''',
        "publish last recovery")

    print("v2.18.0 adaptive OpenRouter recovery complete")


if __name__ == "__main__":
    main()
