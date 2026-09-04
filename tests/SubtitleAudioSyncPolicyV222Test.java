package app.spanishstudy.vot;

public final class SubtitleAudioSyncPolicyV222Test {
    public static void main(String[] args) {
        dubFreezesUntilRealAudioStart();
        sourceOnlyStillUsesSourceClock();
        audioClockWinsAfterStart();
        computesActualPlaybackWindow();
        explicitSeekStartsInsideClip();
        System.out.println("SubtitleAudioSyncPolicyV222Test passed");
    }

    private static void dubFreezesUntilRealAudioStart() {
        near(0.0, SubtitleAudioSyncPolicy.pairedProgress(true, false, 0.0, 0.72));
    }

    private static void sourceOnlyStillUsesSourceClock() {
        near(0.72, SubtitleAudioSyncPolicy.pairedProgress(false, false, 0.0, 0.72));
    }

    private static void audioClockWinsAfterStart() {
        near(0.31, SubtitleAudioSyncPolicy.pairedProgress(true, true, 0.31, 0.88));
    }

    private static void computesActualPlaybackWindow() {
        long end = SubtitleAudioSyncPolicy.playbackEndMs(10_000L, 7_000L, 0L, 1.40f);
        require(end == 15_000L, "7s at 1.4x should occupy 5s of video time");
    }

    private static void explicitSeekStartsInsideClip() {
        near(0.25, SubtitleAudioSyncPolicy.audioStartProgress(8_000L, 2_000L));
        long end = SubtitleAudioSyncPolicy.playbackEndMs(20_000L, 8_000L, 2_000L, 1.5f);
        require(end == 24_000L, "remaining 6s at 1.5x should occupy 4s");
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
