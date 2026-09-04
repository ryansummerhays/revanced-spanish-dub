package app.spanishstudy.vot;

/** Pure retry/circuit policy for recoverable translation-provider failures. */
public final class ProviderResiliencePolicy {
    private ProviderResiliencePolicy() {}

    public static long retryDelayMs(int consecutiveFailures) {
        if (consecutiveFailures <= 0) return 0L;
        int shift = Math.min(consecutiveFailures - 1, 4);
        return Math.min(15_000L, 1_000L << shift);
    }

    public static long googleFallbackCooldownMs(int statusCode) {
        return statusCode == 429 ? 60_000L : 0L;
    }

    public static boolean shouldRetryOpenRouter(String selectedProvider,
                                                boolean externalAbortRequested,
                                                boolean reprioritizeRequested) {
        return "openrouter".equals(selectedProvider)
                && !externalAbortRequested
                && !reprioritizeRequested;
    }
}
