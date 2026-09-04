package app.spanishstudy.vot;

import java.util.Locale;

/** Session-scoped, credential-free OpenRouter accounting and failure telemetry. */
public final class OpenRouterTelemetry {
    private OpenRouterTelemetry() {}

    private static long requests;
    private static long successes;
    private static long failures;
    private static long promptTokens;
    private static long completionTokens;
    private static long totalTokens;
    private static long cachedTokens;
    private static long reasoningTokens;
    private static double costUsd;
    private static long cardinalityMismatches;
    private static long finishLengthCount;
    private static long googleFallbackAttempts;
    private static long googleFallbackFailures;
    private static long google429s;
    private static int lastHttpStatus;
    private static long lastLatencyMs;
    private static String lastProvider = "-";
    private static String lastGeneration = "-";
    private static String lastFinishReason = "-";
    private static String lastRouteStrategy = "-";
    private static String lastRouteRegion = "-";
    private static int lastRouteAttempt;
    private static String lastRouteSummary = "-";
    private static String lastRouteAttempts = "-";
    private static String lastError = "none";

    public static synchronized void resetSession() {
        requests = successes = failures = 0;
        promptTokens = completionTokens = totalTokens = 0;
        cachedTokens = reasoningTokens = 0;
        costUsd = 0.0;
        cardinalityMismatches = 0;
        finishLengthCount = 0;
        googleFallbackAttempts = googleFallbackFailures = google429s = 0;
        lastHttpStatus = 0;
        lastLatencyMs = 0;
        lastRouteAttempt = 0;
        lastProvider = lastGeneration = lastFinishReason = "-";
        lastRouteStrategy = lastRouteRegion = lastRouteSummary = lastRouteAttempts = "-";
        lastError = "none";
    }

    public static synchronized void recordRequestStart() {
        requests++;
    }

    public static synchronized void recordSuccess(int httpStatus, long latencyMs,
                                                  String provider, String generation,
                                                  String finishReason,
                                                  long prompt, long completion, long total,
                                                  long cached, long reasoning, double cost) {
        successes++;
        lastHttpStatus = httpStatus;
        lastLatencyMs = Math.max(0L, latencyMs);
        if (provider != null && !provider.trim().isEmpty()) lastProvider = compact(provider);
        if (generation != null && !generation.trim().isEmpty()) lastGeneration = compact(generation);
        if (finishReason != null && !finishReason.trim().isEmpty()) {
            lastFinishReason = compact(finishReason);
            if ("length".equalsIgnoreCase(finishReason.trim())) finishLengthCount++;
        }
        if (prompt >= 0) promptTokens += prompt;
        if (completion >= 0) completionTokens += completion;
        if (total >= 0) totalTokens += total;
        if (cached >= 0) cachedTokens += cached;
        if (reasoning >= 0) reasoningTokens += reasoning;
        if (!Double.isNaN(cost) && !Double.isInfinite(cost) && cost >= 0.0) costUsd += cost;
        lastError = "none";
    }

    public static synchronized void recordRouterMetadata(String strategy, String region, int attempt,
                                                         String summary, String selectedProvider,
                                                         String attempts) {
        if (strategy != null && !strategy.trim().isEmpty()) lastRouteStrategy = compact(strategy);
        if (region != null && !region.trim().isEmpty() && !"null".equals(region)) lastRouteRegion = compact(region);
        if (attempt >= 0) lastRouteAttempt = attempt;
        if (summary != null && !summary.trim().isEmpty()) lastRouteSummary = compact(summary);
        if (attempts != null && !attempts.trim().isEmpty()) lastRouteAttempts = compact(attempts);
        if (selectedProvider != null && !selectedProvider.trim().isEmpty()) lastProvider = compact(selectedProvider);
    }

    public static synchronized void recordFailure(int httpStatus, long latencyMs, String error) {
        failures++;
        lastHttpStatus = httpStatus;
        lastLatencyMs = Math.max(0L, latencyMs);
        lastError = compact(error);
    }

    public static synchronized void recordCardinalityMismatch(int expected, int observed) {
        cardinalityMismatches++;
        lastError = "cardinality " + observed + "/" + expected;
    }

    public static synchronized void recordGoogleFallbackAttempt() {
        googleFallbackAttempts++;
    }

    public static synchronized void recordGoogleFallbackResult(boolean success, int httpStatus) {
        if (!success) googleFallbackFailures++;
        if (httpStatus == 429) google429s++;
    }

    private static String compact(String text) {
        if (text == null || text.trim().isEmpty()) return "unknown";
        String value = text.replace('\n', ' ').replace('\r', ' ').trim();
        return value.length() <= 160 ? value : value.substring(0, 160);
    }

    /** Ready to append directly to the copied diagnostics report. */
    public static synchronized String diagnostics() {
        return "openRouterRequests=" + requests + '\n'
                + "openRouterSucceeded=" + successes + '\n'
                + "openRouterFailed=" + failures + '\n'
                + "openRouterPromptTokens=" + promptTokens + '\n'
                + "openRouterCompletionTokens=" + completionTokens + '\n'
                + "openRouterTotalTokens=" + totalTokens + '\n'
                + "openRouterCachedTokens=" + cachedTokens + '\n'
                + "openRouterReasoningTokens=" + reasoningTokens + '\n'
                + "openRouterCostUsd=" + String.format(Locale.ROOT, "%.8f", costUsd) + '\n'
                + "openRouterCardinalityMismatches=" + cardinalityMismatches + '\n'
                + "openRouterFinishLengthCount=" + finishLengthCount + '\n'
                + "googleFallbackAttempts=" + googleFallbackAttempts + '\n'
                + "googleFallbackFailures=" + googleFallbackFailures + '\n'
                + "googleFallback429s=" + google429s + '\n'
                + "openRouterLastHttpStatus=" + lastHttpStatus + '\n'
                + "openRouterLastLatencyMs=" + lastLatencyMs + '\n'
                + "openRouterLastProvider=" + lastProvider + '\n'
                + "openRouterLastGeneration=" + lastGeneration + '\n'
                + "openRouterLastFinishReason=" + lastFinishReason + '\n'
                + "openRouterLastRouteStrategy=" + lastRouteStrategy + '\n'
                + "openRouterLastRouteRegion=" + lastRouteRegion + '\n'
                + "openRouterLastRouteAttempt=" + lastRouteAttempt + '\n'
                + "openRouterLastRouteSummary=" + lastRouteSummary + '\n'
                + "openRouterLastRouteAttempts=" + lastRouteAttempts + '\n'
                + "openRouterLastError=" + lastError + '\n';
    }
}
