package app.spanishstudy.vot;

public final class TranslationProviderPolicyTest {
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        require(TranslationProviderPolicy.shouldUseOpenRouter("openrouter", false),
                "selected OpenRouter should be primary before a failure");
        require(!TranslationProviderPolicy.shouldUseOpenRouter("openrouter", true),
                "latched fallback should stop retrying OpenRouter in the same session");
        require(!TranslationProviderPolicy.shouldUseOpenRouter("google", false),
                "explicit Google selection must stay Google");
        require(TranslationProviderPolicy.shouldFallbackToGoogle("openrouter", false, false),
                "ordinary OpenRouter failure should fail forward to Google");
        require(!TranslationProviderPolicy.shouldFallbackToGoogle("openrouter", true, false),
                "abort must not launch fallback work");
        require(!TranslationProviderPolicy.shouldFallbackToGoogle("openrouter", false, true),
                "seek reprioritization must not launch fallback work");
        require(!TranslationProviderPolicy.shouldFallbackToGoogle("google", false, false),
                "Google must not recursively fallback to itself");
        System.out.println("translation provider policy: OK");
    }
}
