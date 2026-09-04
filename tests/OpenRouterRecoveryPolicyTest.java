package app.spanishstudy.vot;

public final class OpenRouterRecoveryPolicyTest {
    private static void expect(boolean expected, boolean actual, String name) {
        if (expected != actual) throw new AssertionError(name + ": expected=" + expected + " actual=" + actual);
    }

    public static void main(String[] args) {
        expect(false, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("openrouter", true, false, false), "usable OpenRouter result");
        expect(true, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("openrouter", false, false, false), "null OpenRouter result");
        expect(false, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("openrouter", false, true, false), "explicit abort");
        expect(false, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("openrouter", false, false, true), "seek reprioritize");
        expect(false, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("google", false, false, false), "Google selected");
        expect(false, OpenRouterRecoveryPolicy.shouldFallbackToGoogle("mymemory", false, false, false), "MyMemory selected");
        System.out.println("OpenRouterRecoveryPolicyTest passed");
    }
}
