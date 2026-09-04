package app.spanishstudy.vot;

/** Pure timing policy for keeping bilingual subtitle pages stable during normal playback. */
public final class SubtitleSyncPolicy {
    public static final long BACKWARD_SEEK_RESET_MS = 1_000L;

    private SubtitleSyncPolicy() {}

    public static boolean isBackwardSeek(long previousTimeMs, long currentTimeMs) {
        return previousTimeMs != Long.MIN_VALUE
                && currentTimeMs + BACKWARD_SEEK_RESET_MS < previousTimeMs;
    }

    public static double monotonicProgress(double previousProgress,
                                           double candidateProgress,
                                           boolean backwardSeek) {
        double candidate = clamp(candidateProgress);
        if (backwardSeek) return candidate;
        return Math.max(clamp(previousProgress), candidate);
    }

    private static double clamp(double value) {
        if (!Double.isFinite(value)) return 0.0;
        return Math.max(0.0, Math.min(1.0, value));
    }
}
