package app.spanishstudy.vot;

public final class OpenRouterTelemetryTest {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        OpenRouterTelemetry.resetSession();
        OpenRouterTelemetry.recordRequestStart();
        OpenRouterTelemetry.recordRouterMetadata("direct", "iad", 2,
                "available=2, selected=DeepInfra", "DeepInfra",
                "Together:529,DeepInfra:200");
        OpenRouterTelemetry.recordSuccess(200, 640, "DeepInfra", "gen-1", "stop",
                100, 25, 125, 8, 0, 0.0000125);
        OpenRouterTelemetry.recordCardinalityMismatch(2, 3);
        OpenRouterTelemetry.recordGoogleFallbackAttempt();
        OpenRouterTelemetry.recordGoogleFallbackResult(false, 429);
        String d = OpenRouterTelemetry.diagnostics();
        check(d.contains("openRouterRequests=1"), "request count");
        check(d.contains("openRouterPromptTokens=100"), "prompt tokens");
        check(d.contains("openRouterLastProvider=DeepInfra"), "provider");
        check(d.contains("openRouterLastRouteStrategy=direct"), "route strategy");
        check(d.contains("openRouterLastRouteAttempt=2"), "route attempt");
        check(d.contains("openRouterLastRouteAttempts=Together:529,DeepInfra:200"), "route attempts");
        check(d.contains("openRouterCardinalityMismatches=1"), "mismatch count");
        check(d.contains("googleFallback429s=1"), "google 429 count");
    }
}
