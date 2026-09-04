package app.spanishstudy.vot;

public final class SpeakerCostPolicyV222Test {
    public static void main(String[] args) {
        countsToolUseAsInput();
        countsThinkingAsOutput();
        ignoresNegativeCounters();
        System.out.println("SpeakerCostPolicyV222Test passed");
    }

    private static void countsToolUseAsInput() {
        double usd = SpeakerCostPolicy.estimatedUsd(1_000L, 3_000L, 0L, 0L);
        near(0.003, usd);
    }

    private static void countsThinkingAsOutput() {
        double usd = SpeakerCostPolicy.estimatedUsd(0L, 0L, 1_000L, 1_000L);
        near(0.0075, usd);
    }

    private static void ignoresNegativeCounters() {
        near(0.0, SpeakerCostPolicy.estimatedUsd(-1, -2, -3, -4));
    }

    private static void near(double expected, double actual) {
        if (Math.abs(expected - actual) > 0.0000001) {
            throw new AssertionError("expected " + expected + " got " + actual);
        }
    }
}
