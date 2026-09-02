package app.spanishstudy.vot;

public final class SourceExpressionMathTest {
    public static void main(String[] args) {
        estimatesVoicedPitch();
        transfersOnlyRelativePitchGently();
        rejectsLowConfidenceAndLargeJumps();
        energyTransferIsBounded();
        System.out.println("source expression math: OK");
    }

    private static void estimatesVoicedPitch() {
        byte[] wave = sineWave(220.0, 44_100, 1024, 0.72);
        SourceExpressionMath.Frame frame = SourceExpressionMath.analyze(wave, 44_100_000);
        require(frame.hasReliablePitch(), "220 Hz sine should be recognized as voiced");
        require(Math.abs(frame.pitchHz - 220f) < 12f,
                "pitch estimate too far from 220 Hz: " + frame.pitchHz);
    }

    private static void transfersOnlyRelativePitchGently() {
        float up = SourceExpressionMath.pitchMultiplier(260f, 220f, 0.9f);
        float down = SourceExpressionMath.pitchMultiplier(185f, 220f, 0.9f);
        require(up > 1f && up <= SourceExpressionMath.MAX_PITCH_MULTIPLIER,
                "upward source inflection should gently raise dubbed pitch");
        require(down < 1f && down >= SourceExpressionMath.MIN_PITCH_MULTIPLIER,
                "downward source inflection should gently lower dubbed pitch");
    }

    private static void rejectsLowConfidenceAndLargeJumps() {
        require(SourceExpressionMath.pitchMultiplier(260f, 220f, 0.2f) == 1f,
                "low-confidence pitch must fail neutral");
        require(SourceExpressionMath.pitchMultiplier(410f, 200f, 1f) == 1f,
                "huge one-frame jump should be treated as noise/identity change");
    }

    private static void energyTransferIsBounded() {
        float loud = SourceExpressionMath.volumeMultiplier(0.16f, 0.08f, 0.9f);
        float quiet = SourceExpressionMath.volumeMultiplier(0.04f, 0.08f, 0.9f);
        require(loud >= 1f && loud <= SourceExpressionMath.MAX_VOLUME_MULTIPLIER,
                "loud expression multiplier outside safe range");
        require(quiet <= 1f && quiet >= SourceExpressionMath.MIN_VOLUME_MULTIPLIER,
                "quiet expression multiplier outside safe range");
    }

    private static byte[] sineWave(double hz, int sampleRate, int size, double amplitude) {
        byte[] out = new byte[size];
        for (int i = 0; i < size; i++) {
            double sample = Math.sin(2.0 * Math.PI * hz * i / sampleRate) * amplitude;
            int unsigned = (int) Math.round(128.0 + sample * 120.0);
            out[i] = (byte) Math.max(0, Math.min(255, unsigned));
        }
        return out;
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
