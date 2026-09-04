package app.spanishstudy.vot;

/** Small pure helpers for Gemini speaker-analysis accounting and quota backoff. */
public final class SpeakerCostPolicy {
    // Gemini 3.7 Flash introductory Standard pricing through 2026-12-31.
    public static final double INPUT_USD_PER_M = 0.75;
    public static final double OUTPUT_USD_PER_M = 3.75;
    public static final long QUOTA_BACKOFF_MS = 10 * 60_000L;

    private SpeakerCostPolicy() {}

    public static double estimatedUsd(long inputTokens, long toolUseTokens,
                                      long outputTokens, long thoughtTokens) {
        long billedInput = Math.max(0L, inputTokens) + Math.max(0L, toolUseTokens);
        long billedOutput = Math.max(0L, outputTokens) + Math.max(0L, thoughtTokens);
        return billedInput * INPUT_USD_PER_M / 1_000_000.0
                + billedOutput * OUTPUT_USD_PER_M / 1_000_000.0;
    }
}
