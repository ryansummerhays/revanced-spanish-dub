package app.spanishstudy.vot;

/**
 * Small pure-Java feature extractor for direct PCM speaker probing.
 *
 * Input is a copied slice of YouTube's decoded PCM. It never changes the playback buffer.
 * Supported Android PCM encodings: 16-bit (2), 8-bit (3), and float (4).
 */
public final class PcmSpeakerFeature {
    public static final int ENCODING_PCM_16BIT = 2;
    public static final int ENCODING_PCM_8BIT = 3;
    public static final int ENCODING_PCM_FLOAT = 4;

    public static final double[] BAND_EDGES = {
            80, 150, 250, 400, 600, 900, 1300, 1800, 2500, 3400, 4500, 6000
    };
    public static final int SPECTRAL_DIMS = BAND_EDGES.length - 1;
    public static final int FEATURE_DIMS = SPECTRAL_DIMS + 4;

    private static final int MAX_MONO_SAMPLES = 2048;
    private static final int FFT_SIZE = 1024;

    private PcmSpeakerFeature() {}

    public static final class Result {
        public final double[] feature;
        public final double rms;
        public final double zcr;
        public final double pitchHz;
        public final double pitchConfidence;
        public final int monoSamples;

        Result(double[] feature, double rms, double zcr, double pitchHz,
               double pitchConfidence, int monoSamples) {
            this.feature = feature;
            this.rms = rms;
            this.zcr = zcr;
            this.pitchHz = pitchHz;
            this.pitchConfidence = pitchConfidence;
            this.monoSamples = monoSamples;
        }
    }

    public static Result analyze(byte[] pcm, int sampleRateHz, int channels, int encoding) {
        if (pcm == null || pcm.length < 64 || sampleRateHz < 8000 || channels < 1) return null;
        int bytesPerSample = bytesPerSample(encoding);
        if (bytesPerSample == 0) return null;
        int frameBytes = bytesPerSample * channels;
        int frameCount = pcm.length / frameBytes;
        if (frameCount < 256) return null;

        int n = Math.min(MAX_MONO_SAMPLES, frameCount);
        double[] mono = new double[n];
        int offset = 0;
        for (int i = 0; i < n; i++) {
            double sum = 0;
            for (int ch = 0; ch < channels; ch++) {
                sum += decodeSample(pcm, offset + ch * bytesPerSample, encoding);
            }
            mono[i] = sum / channels;
            offset += frameBytes;
        }

        double mean = 0;
        for (double v : mono) mean += v;
        mean /= mono.length;

        double power = 0;
        int crossings = 0;
        double prev = mono[0] - mean;
        for (int i = 0; i < mono.length; i++) {
            double v = mono[i] - mean;
            mono[i] = v;
            power += v * v;
            if (i > 0 && ((v >= 0) != (prev >= 0))) crossings++;
            prev = v;
        }
        double rms = Math.sqrt(power / mono.length);
        double zcr = crossings / (double) Math.max(1, mono.length - 1);
        if (rms < 0.0025) return null;

        Pitch pitch = estimatePitch(mono, sampleRateHz, rms);
        Spectrum spectrum = spectrum(mono, sampleRateHz);
        if (spectrum == null) return null;

        double[] out = new double[FEATURE_DIMS];
        System.arraycopy(spectrum.bands, 0, out, 0, SPECTRAL_DIMS);

        double pitchNorm = 0;
        if (pitch.hz > 0) {
            double low = Math.log(70), high = Math.log(350);
            pitchNorm = 2.0 * ((Math.log(clamp(pitch.hz, 70, 350)) - low) / (high - low)) - 1.0;
            pitchNorm = clamp(pitchNorm, -1, 1);
        }
        out[SPECTRAL_DIMS] = pitchNorm;
        out[SPECTRAL_DIMS + 1] = clamp(pitch.confidence, 0, 1);
        out[SPECTRAL_DIMS + 2] = clamp((zcr - 0.10) / 0.10, -1, 1);
        out[SPECTRAL_DIMS + 3] = spectrum.centroidNorm;

        return new Result(out, rms, zcr, pitch.hz, pitch.confidence, mono.length);
    }

    private static Spectrum spectrum(double[] mono, int sampleRateHz) {
        int n = Math.min(FFT_SIZE, Integer.highestOneBit(mono.length));
        if (n < 256) return null;
        double[] re = new double[n];
        double[] im = new double[n];
        for (int i = 0; i < n; i++) {
            double window = 0.5 - 0.5 * Math.cos((2.0 * Math.PI * i) / (n - 1));
            re[i] = mono[i] * window;
        }
        fft(re, im);

        double hzPerBin = sampleRateHz / (double) n;
        double[] bands = new double[SPECTRAL_DIMS];
        double total = 0;
        double weightedHz = 0;

        for (int k = 1; k < n / 2; k++) {
            double hz = k * hzPerBin;
            if (hz > BAND_EDGES[BAND_EDGES.length - 1]) break;
            double mag2 = re[k] * re[k] + im[k] * im[k];
            total += mag2;
            weightedHz += mag2 * hz;
            for (int b = 0; b < SPECTRAL_DIMS; b++) {
                if (hz >= BAND_EDGES[b] && hz < BAND_EDGES[b + 1]) {
                    bands[b] += mag2;
                    break;
                }
            }
        }

        double mean = 0;
        for (int b = 0; b < SPECTRAL_DIMS; b++) {
            bands[b] = Math.log1p(bands[b]);
            mean += bands[b];
        }
        mean /= SPECTRAL_DIMS;
        double norm = 0;
        for (int b = 0; b < SPECTRAL_DIMS; b++) {
            bands[b] -= mean;
            norm += bands[b] * bands[b];
        }
        norm = Math.sqrt(Math.max(1e-9, norm));
        for (int b = 0; b < SPECTRAL_DIMS; b++) bands[b] /= norm;

        double centroid = total > 0 ? weightedHz / total : 0;
        return new Spectrum(bands, clamp(centroid / 6000.0, 0, 1));
    }

    private static Pitch estimatePitch(double[] x, int sampleRateHz, double rms) {
        if (rms < 0.006) return new Pitch(0, 0);
        int minLag = Math.max(2, sampleRateHz / 350);
        int maxLag = Math.min(x.length / 2, sampleRateHz / 70);
        double bestCorr = 0;
        double bestScore = -Double.MAX_VALUE;
        int bestLag = 0;
        for (int lag = minLag; lag <= maxLag; lag += 2) {
            double num = 0, a = 0, b = 0;
            for (int i = 0; i + lag < x.length; i += 2) {
                double p = x[i], q = x[i + lag];
                num += p * q;
                a += p * p;
                b += q * q;
            }
            double corr = num / Math.sqrt(Math.max(1e-12, a * b));
            // Autocorrelation has near-equal peaks at integer multiples of a period. A tiny
            // lag penalty selects the earliest strong peak instead of a later subharmonic.
            double score = corr - lag * 0.00008;
            if (score > bestScore) {
                bestScore = score;
                bestCorr = corr;
                bestLag = lag;
            }
        }
        if (bestLag == 0 || bestCorr < 0.18) return new Pitch(0, Math.max(0, bestCorr));
        return new Pitch(sampleRateHz / (double) bestLag, Math.min(1, bestCorr));
    }

    private static void fft(double[] re, double[] im) {
        int n = re.length;
        for (int i = 1, j = 0; i < n; i++) {
            int bit = n >> 1;
            for (; (j & bit) != 0; bit >>= 1) j ^= bit;
            j ^= bit;
            if (i < j) {
                double tr = re[i]; re[i] = re[j]; re[j] = tr;
                double ti = im[i]; im[i] = im[j]; im[j] = ti;
            }
        }
        for (int len = 2; len <= n; len <<= 1) {
            double angle = -2.0 * Math.PI / len;
            double wLenR = Math.cos(angle), wLenI = Math.sin(angle);
            for (int i = 0; i < n; i += len) {
                double wr = 1, wi = 0;
                for (int j = 0; j < len / 2; j++) {
                    int u = i + j, v = i + j + len / 2;
                    double vr = re[v] * wr - im[v] * wi;
                    double vi = re[v] * wi + im[v] * wr;
                    double ur = re[u], ui = im[u];
                    re[u] = ur + vr; im[u] = ui + vi;
                    re[v] = ur - vr; im[v] = ui - vi;
                    double nextWr = wr * wLenR - wi * wLenI;
                    wi = wr * wLenI + wi * wLenR;
                    wr = nextWr;
                }
            }
        }
    }

    private static int bytesPerSample(int encoding) {
        if (encoding == ENCODING_PCM_16BIT) return 2;
        if (encoding == ENCODING_PCM_8BIT) return 1;
        if (encoding == ENCODING_PCM_FLOAT) return 4;
        return 0;
    }

    private static double decodeSample(byte[] data, int offset, int encoding) {
        if (encoding == ENCODING_PCM_16BIT) {
            int lo = data[offset] & 0xff;
            int hi = data[offset + 1];
            short s = (short) ((hi << 8) | lo);
            return s / 32768.0;
        }
        if (encoding == ENCODING_PCM_8BIT) {
            return ((data[offset] & 0xff) - 128) / 128.0;
        }
        if (encoding == ENCODING_PCM_FLOAT) {
            int bits = (data[offset] & 0xff)
                    | ((data[offset + 1] & 0xff) << 8)
                    | ((data[offset + 2] & 0xff) << 16)
                    | ((data[offset + 3] & 0xff) << 24);
            float f = Float.intBitsToFloat(bits);
            if (!Float.isFinite(f)) return 0;
            return clamp(f, -1, 1);
        }
        return 0;
    }

    private static double clamp(double v, double lo, double hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    private static final class Pitch {
        final double hz;
        final double confidence;
        Pitch(double hz, double confidence) {
            this.hz = hz;
            this.confidence = confidence;
        }
    }

    private static final class Spectrum {
        final double[] bands;
        final double centroidNorm;
        Spectrum(double[] bands, double centroidNorm) {
            this.bands = bands;
            this.centroidNorm = centroidNorm;
        }
    }
}
