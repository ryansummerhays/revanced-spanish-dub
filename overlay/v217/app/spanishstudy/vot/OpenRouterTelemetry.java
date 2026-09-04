package app.spanishstudy.vot;

import java.util.Locale;

/** Session-scoped OpenRouter usage accounting. No prompts, keys, or credentials are retained. */
public final class OpenRouterTelemetry {
    private OpenRouterTelemetry() {}

    private static long requests;
    private static long successes;
    private static long failures;
    private static long contentRejected;
    private static long promptTokens;
    private static long completionTokens;
    private static long totalTokens;
    private static long cachedTokens;
    private static double costUsd;
    private static long cardinalityMismatches;
    private static long finishLengthCount;
    private static int lastHttpStatus;
    private static long lastLatencyMs;
    private static String lastProvider = "-";
    private static String lastGeneration = "-";
    private static String lastFinishReason = "-";
    private static String lastError = "none";

    public static synchronized void resetSession() {
        requests = successes = failures = contentRejected = 0;
        promptTokens = completionTokens = totalTokens = cachedTokens = 0;
        costUsd = 0.0;
        cardinalityMismatches = finishLengthCount = 0;
        lastHttpStatus = 0;
        lastLatencyMs = 0;
        lastProvider = lastGeneration = lastFinishReason = "-";
        lastError = "none";
    }

    public static synchronized void recordRequestStart() {
        requests++;
    }

    public static synchronized void recordSuccess(int httpStatus, long latencyMs,
                                                  String provider, String generation,
                                                  String finishReason, long prompt,
                                                  long completion, long total,
                                                  long cached, double cost) {
        successes++;
        updateRequestMetadata(httpStatus, latencyMs, provider, generation, finishReason);
        accumulateUsage(prompt, completion, total, cached, cost);
        lastError = "none";
    }

    public static synchronized void recordContentReject(int httpStatus, long latencyMs,
                                                        String provider, String generation,
                                                        String finishReason, long prompt,
                                                        long completion, long total,
                                                        long cached, double cost, String error) {
        failures++;
        contentRejected++;
        updateRequestMetadata(httpStatus, latencyMs, provider, generation, finishReason);
        accumulateUsage(prompt, completion, total, cached, cost);
        lastError = compact(error);
    }

    public static synchronized void recordFailure(int httpStatus, long latencyMs, String error) {
        failures++;
        lastHttpStatus = httpStatus;
        lastLatencyMs = Math.max(0L, latencyMs);
        lastError = compact(error);
    }

    public static synchronized void recordLengthFinish(int httpStatus, long latencyMs,
                                                       String provider, String generation,
                                                       long prompt, long completion,
                                                       long total, long cached, double cost) {
        finishLengthCount++;
        failures++;
        updateRequestMetadata(httpStatus, latencyMs, provider, generation, "length");
        accumulateUsage(prompt, completion, total, cached, cost);
        lastError = "finish_reason=length";
    }

    public static synchronized void recordCardinalityMismatch(int expected, int observed) {
        cardinalityMismatches++;
        lastError = "cardinality " + observed + "/" + expected;
    }

    private static void updateRequestMetadata(int httpStatus, long latencyMs,
                                              String provider, String generation, String finishReason) {
        lastHttpStatus = httpStatus;
        lastLatencyMs = Math.max(0L, latencyMs);
        lastProvider = compactOr(lastProvider, provider);
        lastGeneration = compactOr(lastGeneration, generation);
        lastFinishReason = compactOr(lastFinishReason, finishReason);
    }

    private static void accumulateUsage(long prompt, long completion, long total, long cached, double cost) {
        if (prompt >= 0) promptTokens += prompt;
        if (completion >= 0) completionTokens += completion;
        if (total >= 0) totalTokens += total;
        if (cached >= 0) cachedTokens += cached;
        if (!Double.isNaN(cost) && !Double.isInfinite(cost) && cost >= 0.0) costUsd += cost;
    }

    private static String compactOr(String oldValue, String value) {
        return value == null || value.trim().isEmpty() ? oldValue : compact(value);
    }

    private static String compact(String value) {
        if (value == null || value.trim().isEmpty()) return "unknown";
        String text = value.replace('\n', ' ').replace('\r', ' ').trim();
        return text.length() <= 160 ? text : text.substring(0, 160);
    }

    public static synchronized String diagnostics() {
        return "openRouterRequests=" + requests + '\n'
                + "openRouterSucceeded=" + successes + '\n'
                + "openRouterFailed=" + failures + '\n'
                + "openRouterContentRejected=" + contentRejected + '\n'
                + "openRouterPromptTokens=" + promptTokens + '\n'
                + "openRouterCompletionTokens=" + completionTokens + '\n'
                + "openRouterTotalTokens=" + totalTokens + '\n'
                + "openRouterCachedTokens=" + cachedTokens + '\n'
                + "openRouterCostUsd=" + String.format(Locale.ROOT, "%.8f", costUsd) + '\n'
                + "openRouterCardinalityMismatches=" + cardinalityMismatches + '\n'
                + "openRouterFinishLengthCount=" + finishLengthCount + '\n'
                + "openRouterLastHttpStatus=" + lastHttpStatus + '\n'
                + "openRouterLastLatencyMs=" + lastLatencyMs + '\n'
                + "openRouterLastProvider=" + lastProvider + '\n'
                + "openRouterLastGeneration=" + lastGeneration + '\n'
                + "openRouterLastFinishReason=" + lastFinishReason + '\n'
                + "openRouterLastError=" + lastError + '\n';
    }
}