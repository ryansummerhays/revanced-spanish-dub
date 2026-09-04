package app.spanishstudy.vot;

/** Pure timing policy that prevents an old subtitle from starting well after its source cue ended. */
public final class TtsStartPolicy {
    public static final long LATE_START_GRACE_MS = 500L;

    private TtsStartPolicy() {}

    public static boolean allowStart(long speakFromMs, long sourceStartMs, long sourceEndMs,
                                     boolean explicitSeek) {
        if (explicitSeek) return true;
        if (sourceEndMs <= sourceStartMs) return true;
        return speakFromMs <= sourceEndMs + LATE_START_GRACE_MS;
    }

    public static long lateFromSourceStartMs(long speakFromMs, long sourceStartMs) {
        return Math.max(0L, speakFromMs - sourceStartMs);
    }

    public static long sourceRemainingMs(long speakFromMs, long sourceEndMs) {
        return Math.max(0L, sourceEndMs - speakFromMs);
    }

    public static float requiredRate(long remainingSpeechMs, long speakFromMs, long sourceEndMs) {
        long remaining = sourceRemainingMs(speakFromMs, sourceEndMs);
        if (remaining <= 0L) return Float.POSITIVE_INFINITY;
        return remainingSpeechMs / (float) remaining;
    }
}