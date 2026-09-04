package app.spanishstudy.vot;

public final class TtsStartPolicyV219Test {
    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        check(TtsStartPolicy.allowStart(9_500, 5_000, 10_000, false), "in-cue start should play");
        check(TtsStartPolicy.allowStart(10_400, 5_000, 10_000, false), "small scheduler delay should be tolerated");
        check(!TtsStartPolicy.allowStart(11_000, 5_000, 10_000, false), "stale old cue must not begin over next cue");
        check(TtsStartPolicy.allowStart(14_000, 5_000, 10_000, true), "explicit user seek/replay is allowed");
        check(TtsStartPolicy.lateFromSourceStartMs(8_250, 5_000) == 3_250, "late-start arithmetic");
        check(TtsStartPolicy.sourceRemainingMs(8_250, 10_000) == 1_750, "remaining-slot arithmetic");
        float required = TtsStartPolicy.requiredRate(3_500, 8_250, 10_000);
        check(Math.abs(required - 2.0f) < 0.001f, "required-rate arithmetic");
        System.out.println("TtsStartPolicyV219Test OK");
    }
}