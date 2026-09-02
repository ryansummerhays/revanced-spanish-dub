package app.spanishstudy.vot;

/**
 * Small, dependency-free signal helpers for source-expression transfer.
 *
 * The goal is deliberately NOT voice conversion. We only estimate whether the currently playing
 * source speech is moving up/down in pitch or getting somewhat stronger/weaker relative to its own
 * recent baseline. The resulting multipliers are tightly bounded so noisy audio, music, a speaker
 * change, yelling, whispering, or a bad pitch estimate cannot radically distort the Spanish voice.
 */
public final class SourceExpressionMath {
    public static final float MIN_PITCH_MULTIPLIER = 0.944f; // about -1 semitone
    public static final float MAX_PITCH_MULTIPLIER = 1.059f; // about +1 semitone
    public static final float MIN_VOLUME_MULTIPLIER = 0.92f;
    public static final float MAX_VOLUME_MULTIPLIER = 1.08f;

    private static final float MIN_RMS = 0.018f;
    private static final float MIN_VOICING_CORRELATION = 0.46f;
    private static final int MIN_PITCH_HZ = 75;
    private static final int MAX_PITCH_HZ = 420;

    private SourceExpressionMath() {}

    public static final class Frame {
        public final float rms;
        public final float pitchHz;
        /** 0..1 confidence that the waveform contains a usable periodic voiced component. */
        public final float confidence;

        Frame(float rms, float pitchHz, float confidence) {
            this.rms = rms;
            this.pitchHz = pitchHz;
            this.confidence = confidence;
        }

        public boolean hasReliablePitch() {
            return pitchHz > 0f && confidence >= 0.55f;
        }
    }

    /**
     * Analyze an Android Visualizer waveform. Visualizer samples are unsigned 8-bit PCM centered at
     * 128 and samplingRateMilliHz is reported in milli-Hz by Android.
     */
    public static Frame analyze(byte[] waveform, int samplingRateMilliHz) {
        if (waveform == null || waveform.length < 128) return new Frame(0f, 0f, 0f);
        int sampleRate = samplingRateMilliHz > 100_000
                ? samplingRateMilliHz / 1000 : samplingRateMilliHz;
        if (sampleRate < 8_000 || sampleRate > 192_000) return new Frame(0f, 0f, 0f);

        final int n = waveform.length;
        double mean = 0.0;
        for (byte b : waveform) mean += (b & 0xff) - 128.0;
        mean /= n;

        double energy = 0.0;
        for (byte b : waveform) {
            double x = ((b & 0xff) - 128.0 - mean) / 128.0;
            energy += x * x;
        }
        float rms = (float) Math.sqrt(energy / n);
        if (rms < MIN_RMS) return new Frame(rms, 0f, 0f);

        int minLag = Math.max(2, sampleRate / MAX_PITCH_HZ);
        int maxLag = Math.min(n / 2, sampleRate / MIN_PITCH_HZ);
        if (maxLag <= minLag) return new Frame(rms, 0f, 0f);

        int bestLag = -1;
        double bestCorr = -1.0;

        // Step by two samples. That halves callback cost while retaining much finer resolution than
        // the very small pitch modulation we ultimately allow through to TTS.
        for (int lag = minLag; lag <= maxLag; lag++) {
            double cross = 0.0;
            double left = 0.0;
            double right = 0.0;
            for (int i = 0; i + lag < n; i += 2) {
                double a = ((waveform[i] & 0xff) - 128.0 - mean) / 128.0;
                double b = ((waveform[i + lag] & 0xff) - 128.0 - mean) / 128.0;
                cross += a * b;
                left += a * a;
                right += b * b;
            }
            if (left <= 1e-9 || right <= 1e-9) continue;
            double corr = cross / Math.sqrt(left * right);
            if (corr > bestCorr) {
                bestCorr = corr;
                bestLag = lag;
            }
        }

        if (bestLag <= 0 || bestCorr < MIN_VOICING_CORRELATION) {
            return new Frame(rms, 0f, 0f);
        }

        float pitch = sampleRate / (float) bestLag;
        if (pitch < MIN_PITCH_HZ || pitch > MAX_PITCH_HZ) return new Frame(rms, 0f, 0f);
        float confidence = clamp((float) ((bestCorr - MIN_VOICING_CORRELATION)
                / (1.0 - MIN_VOICING_CORRELATION)), 0f, 1f);
        return new Frame(rms, pitch, confidence);
    }

    /**
     * Convert a source pitch deviation into a very gentle Spanish playback pitch change.
     * Absolute speaker pitch is intentionally discarded: only deviation from that source's rolling
     * baseline is transferred. The log-domain compression prevents a new/high-pitched speaker from
     * being mistaken for a huge expressive jump.
     */
    public static float pitchMultiplier(float pitchHz, float baselinePitchHz, float confidence) {
        if (pitchHz <= 0f || baselinePitchHz <= 0f || confidence < 0.55f) return 1f;
        float ratio = pitchHz / baselinePitchHz;
        if (!Float.isFinite(ratio) || ratio <= 0f) return 1f;

        // Reject implausibly large one-frame jumps as identity/noise changes rather than expression.
        if (ratio < 0.58f || ratio > 1.72f) return 1f;
        double compressed = Math.exp(Math.log(ratio) * 0.28 * confidence);
        return clamp((float) compressed, MIN_PITCH_MULTIPLIER, MAX_PITCH_MULTIPLIER);
    }

    /** Gentle energy transfer, accepted only when a voiced pitch estimate is also trustworthy. */
    public static float volumeMultiplier(float rms, float baselineRms, float confidence) {
        if (rms <= 0f || baselineRms <= 0f || confidence < 0.55f) return 1f;
        float ratio = rms / baselineRms;
        if (!Float.isFinite(ratio) || ratio <= 0f) return 1f;
        if (ratio < 0.25f || ratio > 4.0f) return 1f;
        double compressed = Math.exp(Math.log(ratio) * 0.10 * confidence);
        return clamp((float) compressed, MIN_VOLUME_MULTIPLIER, MAX_VOLUME_MULTIPLIER);
    }

    static float clamp(float value, float min, float max) {
        return Math.max(min, Math.min(max, value));
    }
}
