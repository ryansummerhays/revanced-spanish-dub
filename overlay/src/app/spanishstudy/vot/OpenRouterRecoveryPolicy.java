package app.spanishstudy.vot;

/** Pure recovery policy for provider fail-forward decisions. */
public final class OpenRouterRecoveryPolicy {
    private OpenRouterRecoveryPolicy() {}

    public static boolean shouldFallbackToGoogle(String selectedProvider,
                                                 boolean hasUsableResult,
                                                 boolean externalAbortRequested,
                                                 boolean reprioritizeRequested) {
        return "openrouter".equals(selectedProvider)
                && !hasUsableResult
                && !externalAbortRequested
                && !reprioritizeRequested;
    }
}
