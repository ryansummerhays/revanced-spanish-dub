package app.spanishstudy.vot;

public final class PcmSpeakerFeatureV232Test {
    public static void main(String[] args) {
        detectsTone();
        separatesDifferentPitchFeatures();
        handlesStereo();
        rejectsSilence();
        System.out.println("PcmSpeakerFeatureV232Test passed");
    }

    private static void detectsTone() {
        byte[] pcm = sine16(48000, 180.0, 0.20, 1);
        PcmSpeakerFeature.Result r = PcmSpeakerFeature.analyze(pcm, 48000, 1,
                PcmSpeakerFeature.ENCODING_PCM_16BIT);
        req(r != null, "180 Hz tone should produce features");
        req(r.feature.length == PcmSpeakerFeature.FEATURE_DIMS, "feature dimensions");
        req(r.rms > 0.05, "non-silent RMS");
        req(r.pitchHz > 130 && r.pitchHz < 240, "pitch should be speech-like: " + r.pitchHz);
    }

    private static void separatesDifferentPitchFeatures() {
        PcmSpeakerFeature.Result low = PcmSpeakerFeature.analyze(
                sine16(48000, 120.0, 0.25, 1), 48000, 1, PcmSpeakerFeature.ENCODING_PCM_16BIT);
        PcmSpeakerFeature.Result high = PcmSpeakerFeature.analyze(
                sine16(48000, 260.0, 0.25, 1), 48000, 1, PcmSpeakerFeature.ENCODING_PCM_16BIT);
        req(low != null && high != null, "both tones");
        double delta = Math.abs(low.feature[PcmSpeakerFeature.SPECTRAL_DIMS]
                - high.feature[PcmSpeakerFeature.SPECTRAL_DIMS]);
        req(delta > 0.35, "pitch feature should differ: " + delta);
    }

    private static void handlesStereo() {
        byte[] pcm = sine16(48000, 200.0, 0.20, 2);
        PcmSpeakerFeature.Result r = PcmSpeakerFeature.analyze(pcm, 48000, 2,
                PcmSpeakerFeature.ENCODING_PCM_16BIT);
        req(r != null && r.monoSamples >= 256, "stereo decode");
    }

    private static void rejectsSilence() {
        byte[] pcm = new byte[8192];
        req(PcmSpeakerFeature.analyze(pcm, 48000, 2,
                PcmSpeakerFeature.ENCODING_PCM_16BIT) == null, "silence must be ignored");
    }

    private static byte[] sine16(int sr, double hz, double seconds, int channels) {
        int frames = (int) (sr * seconds);
        byte[] out = new byte[frames * channels * 2];
        int p = 0;
        for (int i = 0; i < frames; i++) {
            short s = (short) Math.round(Math.sin(2.0 * Math.PI * hz * i / sr) * 12000.0);
            for (int ch = 0; ch < channels; ch++) {
                out[p++] = (byte) (s & 0xff);
                out[p++] = (byte) ((s >>> 8) & 0xff);
            }
        }
        return out;
    }

    private static void req(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
}
