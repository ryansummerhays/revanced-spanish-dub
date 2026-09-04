package app.spanishstudy.vot;

/**
 * Pure policy for choosing the reliability floor underneath Edge TTS.
 *
 * Edge remains the preferred high-quality voice when its MP3 was prepared before the source phrase
 * becomes active. Once a phrase is already active, starting a fresh network synthesis competes with
 * the phrase deadline and can leave the entire dub silent on a slow/broken Edge connection. In that
 * case a warmed Android Spanish TTS engine is the deterministic fail-forward path.
 */
public final class EdgeReliabilityPolicy {
    public static final int PREFETCH_FAILURES_BEFORE_SUPPRESS = 3;

    private EdgeReliabilityPolicy() {}

    /**
     * Use native TTS for an active phrase when Edge audio was not prefetched and native TTS is ready.
     * Future phrases may continue to prefetch Edge normally.
     */
    public static boolean useNativeForActiveCacheMiss(boolean edgeCached,
                                                      boolean nativeReady,
                                                      long nowMs,
                                                      long startMs,
                                                      long endMs) {
        return !edgeCached && nativeReady && nowMs >= startMs && nowMs < endMs;
    }

    /** Stop hammering one Edge phrase forever after repeated prefetch failures in the same video. */
    public static boolean suppressEdgePrefetch(int failures) {
        return failures >= PREFETCH_FAILURES_BEFORE_SUPPRESS;
    }
}
