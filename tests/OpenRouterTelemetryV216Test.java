package app.spanishstudy.vot;

public final class OpenRouterTelemetryV216Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        OpenRouterTelemetry.resetSession();
        OpenRouterTelemetry.recordRequestStart();
        OpenRouterTelemetry.recordSuccess(200, 321, "DeepInfra", "gen-1", "stop",
                100, 25, 125, 40, 0.00001);
        OpenRouterTelemetry.recordCardinalityMismatch(3, 2);
        String report = OpenRouterTelemetry.diagnostics();
        check(report.contains("openRouterRequests=1"), "request count");
        check(report.contains("openRouterSucceeded=1"), "success count");
        check(report.contains("openRouterPromptTokens=100"), "prompt tokens");
        check(report.contains("openRouterCachedTokens=40"), "cached tokens");
        check(report.contains("openRouterLastProvider=DeepInfra"), "provider");
        check(report.contains("openRouterCardinalityMismatches=1"), "mismatch count");

        OpenRouterTelemetry.recordRequestStart();
        OpenRouterTelemetry.recordLengthFinish(200, 500, "Parasail", "gen-2",
                50, 30, 80, 0, 0.00002);
        report = OpenRouterTelemetry.diagnostics();
        check(report.contains("openRouterFinishLengthCount=1"), "length finish count");
        check(report.contains("openRouterFailed=1"), "length counted as failed translation");
    }
}
