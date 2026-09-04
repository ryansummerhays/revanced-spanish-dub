package app.spanishstudy.vot;

public final class SubtitleSyncPolicyV221Test {
    public static void main(String[] args) {
        normalPlaybackNeverRewindsPageProgress();
        ttsClockCannotResetSourceFallbackProgress();
        trueBackwardSeekCanResetProgress();
        smallClockJitterIsNotASeek();
        System.out.println("SubtitleSyncPolicyV221Test passed");
    }

    private static void normalPlaybackNeverRewindsPageProgress() {
        near(0.75, SubtitleSyncPolicy.monotonicProgress(0.60, 0.75, false));
    }

    private static void ttsClockCannotResetSourceFallbackProgress() {
        near(0.62, SubtitleSyncPolicy.monotonicProgress(0.62, 0.18, false));
    }

    private static void trueBackwardSeekCanResetProgress() {
        require(SubtitleSyncPolicy.isBackwardSeek(12_000L, 8_000L), "4s rewind should reset");
        near(0.18, SubtitleSyncPolicy.monotonicProgress(0.62, 0.18, true));
    }

    private static void smallClockJitterIsNotASeek() {
        require(!SubtitleSyncPolicy.isBackwardSeek(12_000L, 11_400L), "600ms jitter is not a seek");
    }

    private static void near(double expected, double actual) {
        if (Math.abs(expected - actual) > 0.0001) {
            throw new AssertionError("expected " + expected + " got " + actual);
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
