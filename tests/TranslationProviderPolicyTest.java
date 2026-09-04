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
                "video/session abort must not launch a fallback request");
        require(!TranslationProviderPolicy.shouldFallbackToGoogle("openrouter", false, true),
                "seek reprioritization must not launch a fallback request");
        require(!TranslationProviderPolicy.shouldFallbackToGoogle("google", false, false),
                "Google failure must not recursively fallback to Google");

        require("openrouter".equals(TranslationProviderPolicy.effectiveService("openrouter", false)),
                "effective service should be OpenRouter while healthy");
        require("google".equals(TranslationProviderPolicy.effectiveService("google", false)),
                "effective service should preserve Google selection");

        System.out.println("translation provider policy: OK");
    }
}
