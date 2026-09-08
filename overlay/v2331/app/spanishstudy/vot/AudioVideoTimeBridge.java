package app.spanishstudy.vot;

/**
 * Links diarization audio to authoritative YouTube video time.
 * Raw AudioTrack callback count is deliberately not a clock.
 */
public final class AudioVideoTimeBridge {
    private long videoEpoch = -1L;
    private long continuityEpoch = -1L;
    private long captureStartVideoMs = -1L;
    private long lastVideoMs = -1L;
    private long acceptedSamples;
    private long offeredSamples;
    private long rejectedDuplicateOrAheadSamples;
    private boolean invalidated;
    private final long allowedLeadMs;

    public AudioVideoTimeBridge() { this(0L); }

    public AudioVideoTimeBridge(long allowedLeadMs) {
        if (allowedLeadMs < 0L) throw new IllegalArgumentException("allowedLeadMs < 0");
        this.allowedLeadMs = allowedLeadMs;
    }

    public void reset() {
        videoEpoch = -1L;
        continuityEpoch = -1L;
        captureStartVideoMs = -1L;
        lastVideoMs = -1L;
        acceptedSamples = 0L;
        offeredSamples = 0L;
        rejectedDuplicateOrAheadSamples = 0L;
        invalidated = false;
    }

    /** Returns how many offered samples may advance the diarization timeline now. */
    public int permitSamples(int offered, int sampleRateHz, VideoSessionClock.Snapshot clock) {
        if (offered <= 0 || sampleRateHz <= 0 || clock == null || !clock.open || clock.videoMs < 0L) return 0;
        offeredSamples += offered;

        if (captureStartVideoMs < 0L) {
            videoEpoch = clock.videoEpoch;
            continuityEpoch = clock.continuityEpoch;
            captureStartVideoMs = clock.videoMs;
            lastVideoMs = clock.videoMs;
            rejectedDuplicateOrAheadSamples += offered;
            return 0;
        }

        if (clock.videoEpoch != videoEpoch || clock.continuityEpoch != continuityEpoch) {
            invalidated = true;
            rejectedDuplicateOrAheadSamples += offered;
            return 0;
        }

        lastVideoMs = clock.videoMs;
        long elapsedVideoMs = Math.max(0L, clock.videoMs - captureStartVideoMs + allowedLeadMs);
        long allowedTotalSamples = (elapsedVideoMs * sampleRateHz) / 1000L;
        long room = allowedTotalSamples - acceptedSamples;
        if (room <= 0L) {
            rejectedDuplicateOrAheadSamples += offered;
            return 0;
        }
        int acceptedNow = (int) Math.min((long) offered, room);
        acceptedSamples += acceptedNow;
        rejectedDuplicateOrAheadSamples += offered - acceptedNow;
        return acceptedNow;
    }

    public boolean isInvalidated() { return invalidated; }
    public long getVideoEpoch() { return videoEpoch; }
    public long getContinuityEpoch() { return continuityEpoch; }
    public long getCaptureStartVideoMs() { return captureStartVideoMs; }
    public long getCaptureEndVideoMs() { return lastVideoMs; }
    public long getCaptureVideoSpanMs() {
        return captureStartVideoMs < 0L || lastVideoMs < 0L ? 0L : Math.max(0L, lastVideoMs - captureStartVideoMs);
    }
    public long getAcceptedSamples() { return acceptedSamples; }
    public long getOfferedSamples() { return offeredSamples; }
    public long getRejectedDuplicateOrAheadSamples() { return rejectedDuplicateOrAheadSamples; }
}
