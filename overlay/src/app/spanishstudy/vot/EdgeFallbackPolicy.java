package app.spanishstudy.vot;

/** Pure policy for temporarily preferring offline Android TTS after repeated Edge failures. */
public final class EdgeFallbackPolicy {
    public static final int FAILURE_THRESHOLD = 2;
    public static final long FALLBACK_WINDOW_MS = 60_000L;

    private EdgeFallbackPolicy() {}

    public static boolean shouldOpen(int consecutiveFailures) {
        return consecutiveFailures >= FAILURE_THRESHOLD;
    }

    public static long fallbackUntil(long nowMs) {
        return nowMs + FALLBACK_WINDOW_MS;
    }

    public static boolean isOpen(long nowMs, long untilMs) {
        return untilMs > nowMs;
    }
}
