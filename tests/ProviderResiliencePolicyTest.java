package app.spanishstudy.vot;

public final class ProviderResiliencePolicyTest {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(ProviderResiliencePolicy.retryDelayMs(1) == 1000L, "first retry");
        check(ProviderResiliencePolicy.retryDelayMs(2) == 2000L, "second retry");
        check(ProviderResiliencePolicy.retryDelayMs(6) == 15000L, "retry cap");
        check(ProviderResiliencePolicy.googleFallbackCooldownMs(429) == 60000L, "429 circuit");
        check(ProviderResiliencePolicy.googleFallbackCooldownMs(500) == 0L, "non-429 circuit");
        check(ProviderResiliencePolicy.shouldRetryOpenRouter("openrouter", false, false), "retry OpenRouter");
        check(!ProviderResiliencePolicy.shouldRetryOpenRouter("openrouter", true, false), "abort blocks retry");
    }
}
