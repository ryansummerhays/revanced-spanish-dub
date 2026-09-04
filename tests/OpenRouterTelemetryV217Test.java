package app.spanishstudy.vot;

public final class OpenRouterTelemetryV217Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        OpenRouterTelemetry.resetSession();
        OpenRouterTelemetry.recordRequestStart();
        OpenRouterTelemetry.recordContentReject(200, 400, "DeepInfra", "gen-x", "stop",
                120, 35, 155, 20, 0.00002, "language-guard slot=2");
        String report = OpenRouterTelemetry.diagnostics();
        check(report.contains("openRouterRequests=1"), "request count");
        check(report.contains("openRouterSucceeded=0"), "semantic reject must not count as success");
        check(report.contains("openRouterFailed=1"), "semantic reject must count as failed translation");
        check(report.contains("openRouterContentRejected=1"), "content reject count");
        check(report.contains("openRouterTotalTokens=155"), "usage still accounted on semantic reject");
        check(report.contains("openRouterCostUsd=0.00002000"), "cost still accounted on semantic reject");
    }
}