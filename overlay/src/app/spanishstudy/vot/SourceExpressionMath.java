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
    private static final float YIN_THRESHOLD = 0.18f;
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
     *
     * A compact YIN-style cumulative mean normalized difference estimator is used instead of plain
     * autocorrelation. Plain autocorrelation frequently prefers two periods over one (110 Hz for a
     * clean 220 Hz tone); YIN deliberately chooses the first strong periodic minimum and is much
     * safer for the gentle relative pitch tracking needed here.
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

        final double[] samples = new double[n];
        double energy = 0.0;
        for (int i = 0; i < n; i++) {
            double x = ((waveform[i] & 0xff) - 128.0 - mean) / 128.0;
            samples[i] = x;
            energy += x * x;
        }
        float rms = (float) Math.sqrt(energy / n);
        if (rms < MIN_RMS) return new Frame(rms, 0f, 0f);

        int minLag = Math.max(2, sampleRate / MAX_PITCH_HZ);
        int maxLag = Math.min(n / 2, sampleRate / MIN_PITCH_HZ);
        if (maxLag <= minLag) return new Frame(rms, 0f, 0f);

        final double[] difference = new double[maxLag + 1];
        final double[] cmnd = new double[maxLag + 1];
        cmnd[0] = 1.0;

        // Step by two samples to keep Visualizer callbacks inexpensive on phones.
        for (int lag = 1; lag <= maxLag; lag++) {
            double sum = 0.0;
            for (int i = 0; i + lag < n; i += 2) {
                double delta = samples[i] - samples[i + lag];
                sum += delta * delta;
            }
            difference[lag] = sum;
        }

        double running = 0.0;
        for (int lag = 1; lag <= maxLag; lag++) {
            running += difference[lag];
            cmnd[lag] = running > 1e-12 ? difference[lag] * lag / running : 1.0;
        }

        int chosenLag = -1;
        for (int lag = minLag; lag <= maxLag; lag++) {
            if (cmnd[lag] < YIN_THRESHOLD) {
                // Descend to the local minimum, then stop. The first good minimum is the period,
                // whereas later minima are commonly integer multiples of that period.
                while (lag + 1 <= maxLag && cmnd[lag + 1] < cmnd[lag]) lag++;
                chosenLag = lag;
                break;
            }
        }

        if (chosenLag < 0) {
            // No threshold crossing: take the global minimum only when it is still reasonably
            // periodic. Otherwise fail neutral rather than inventing expression from noise/music.
            double best = Double.POSITIVE_INFINITY;
            int bestLag = -1;
            for (int lag = minLag; lag <= maxLag; lag++) {
                if (cmnd[lag] < best) {
                    best = cmnd[lag];
                    bestLag = lag;
                }
            }
            if (bestLag < 0 || best > 0.32) return new Frame(rms, 0f, 0f);
            chosenLag = bestLag;
        }

        float pitch = sampleRate / (float) chosenLag;
        if (pitch < MIN_PITCH_HZ || pitch > MAX_PITCH_HZ) return new Frame(rms, 0f, 0f);
        float confidence = clamp((float) (1.0 - cmnd[chosenLag] / 0.35), 0f, 1f);
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
