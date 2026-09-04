package app.spanishstudy.vot;

/** Conservative network-TTS startup policy for an uncached phrase already under the playhead. */
public final class StartupSpeechPolicy {
    /** Do not spend a network synthesis turn on a phrase with less than this much source time left. */
    public static final long MIN_NETWORK_REMAINING_MS = 1_200L;

    private StartupSpeechPolicy() {}

    public static boolean shouldStartNetwork(long segmentEndMs, long playheadMs) {
        return segmentEndMs - playheadMs >= MIN_NETWORK_REMAINING_MS;
    }
}
