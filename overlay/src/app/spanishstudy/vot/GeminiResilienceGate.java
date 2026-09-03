package app.spanishstudy.vot;

import java.util.Locale;

/**
 * Process-wide circuit breaker for optional Gemini enhancement work.
 *
 * <p>Text translation and media/speaker analysis have separate circuits because Google can expose
 * different limits for different models. A quota error never disables Spanish dubbing: callers are
 * expected to use Google text translation or already-cached results while the Gemini circuit rests.
 */
public final class GeminiResilienceGate {
    private static final long TEXT_TRANSIENT_BASE_MS = 45_000L;
    private static final long TEXT_QUOTA_BASE_MS = 10 * 60_000L;
    private static final long TEXT_MAX_MS = 6 * 60 * 60_000L;
    private static final long MEDIA_TRANSIENT_BASE_MS = 2 * 60_000L;
    private static final long MEDIA_QUOTA_BASE_MS = 20 * 60_000L;
    private static final long MEDIA_MAX_MS = 6 * 60 * 60_000L;

    private static long textBlockedUntil;
    private static long mediaBlockedUntil;
    private static int textFailures;
    private static int mediaFailures;
    private static boolean textLastWasQuota;
    private static boolean mediaLastWasQuota;

    private GeminiResilienceGate() {}

    public static synchronized boolean canUseText() {
        return System.currentTimeMillis() >= textBlockedUntil;
    }

    public static synchronized boolean canUseMedia() {
        return System.currentTimeMillis() >= mediaBlockedUntil;
    }

    public static synchronized void recordTextSuccess() {
        textBlockedUntil = 0L;
        textFailures = 0;
        textLastWasQuota = false;
    }

    public static synchronized void recordMediaSuccess() {
        mediaBlockedUntil = 0L;
        mediaFailures = 0;
        mediaLastWasQuota = false;
    }

    public static synchronized void recordTextFailure(Throwable error) {
        boolean quota = isQuota(error == null ? "" : error.getMessage());
        textFailures = Math.min(8, textFailures + 1);
        textLastWasQuota = quota;
        long base = quota ? TEXT_QUOTA_BASE_MS : TEXT_TRANSIENT_BASE_MS;
        long max = TEXT_MAX_MS;
        long delay = exponential(base, textFailures, max);
        textBlockedUntil = Math.max(textBlockedUntil, System.currentTimeMillis() + delay);
        SpanishStudyDiagnostics.record("GATE", "Gemini text paused " + human(delay)
                + (quota ? " after quota/429" : " after transient failure"));
    }

    public static synchronized void recordMediaFailure(Throwable error) {
        boolean quota = isQuota(error == null ? "" : error.getMessage());
        mediaFailures = Math.min(8, mediaFailures + 1);
        mediaLastWasQuota = quota;
        long base = quota ? MEDIA_QUOTA_BASE_MS : MEDIA_TRANSIENT_BASE_MS;
        long delay = exponential(base, mediaFailures, MEDIA_MAX_MS);
        mediaBlockedUntil = Math.max(mediaBlockedUntil, System.currentTimeMillis() + delay);
        SpanishStudyDiagnostics.record("GATE", "Gemini media paused " + human(delay)
                + (quota ? " after quota/429" : " after transient failure"));
    }

    public static synchronized String textStatus() {
        return status(textBlockedUntil, textLastWasQuota, textFailures);
    }

    public static synchronized String mediaStatus() {
        return status(mediaBlockedUntil, mediaLastWasQuota, mediaFailures);
    }

    private static String status(long until, boolean quota, int failures) {
        long remaining = Math.max(0L, until - System.currentTimeMillis());
        if (remaining <= 0L) return "available";
        return "fallback for " + human(remaining) + (quota ? " (quota)" : " (temporary)")
                + " failures=" + failures;
    }

    private static long exponential(long base, int failures, long max) {
        int shift = Math.min(5, Math.max(0, failures - 1));
        long value;
        try {
            value = Math.multiplyExact(base, 1L << shift);
        } catch (ArithmeticException overflow) {
            value = max;
        }
        return Math.min(max, value);
    }

    private static boolean isQuota(String message) {
        if (message == null) return false;
        String lower = message.toLowerCase(Locale.ROOT);
        return lower.contains("429") || lower.contains("quota")
                || lower.contains("resource_exhausted") || lower.contains("resource exhausted");
    }

    private static String human(long ms) {
        long seconds = Math.max(1L, (ms + 999L) / 1000L);
        if (seconds < 60L) return seconds + "s";
        long minutes = (seconds + 59L) / 60L;
        if (minutes < 60L) return minutes + "m";
        long hours = (minutes + 59L) / 60L;
        return hours + "h";
    }
}
