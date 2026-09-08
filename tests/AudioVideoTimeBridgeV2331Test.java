import app.spanishstudy.vot.AudioVideoTimeBridge;
import app.spanishstudy.vot.VideoSessionClock;

public final class AudioVideoTimeBridgeV2331Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        final int sr = 16_000;
        final int chunk = 320; // nominal 20 ms

        VideoSessionClock.onVideoClosed();
        VideoSessionClock.onVideoOpened("dup-test");
        VideoSessionClock.publishVideoTime(100_000L);
        AudioVideoTimeBridge bridge = new AudioVideoTimeBridge();

        check(bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot()) == 0, "anchor consumed audio");
        for (int i = 0; i < 4; i++)
            check(bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot()) == 0,
                    "duplicate callback advanced neural clock");

        VideoSessionClock.publishVideoTime(100_020L);
        int accepted = 0;
        for (int i = 0; i < 5; i++) accepted += bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot());
        check(accepted == 320, "20 ms video advancement must permit exactly 320 samples, got " + accepted);

        // Simulate four raw 20-ms callbacks per real 20-ms of video for a full 20 seconds.
        for (int step = 2; step <= 1000; step++) {
            VideoSessionClock.publishVideoTime(100_000L + step * 20L);
            for (int d = 0; d < 4; d++) bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot());
        }
        check(bridge.getAcceptedSamples() == 320_000L,
                "20 s video must equal 320000 admitted samples, got " + bridge.getAcceptedSamples());
        check(bridge.getCaptureVideoSpanMs() == 20_000L, "capture span must be 20 s video time");
        check(bridge.getRejectedDuplicateOrAheadSamples() > 0L, "duplicate stream was not rejected");

        VideoSessionClock.markExplicitSeek();
        VideoSessionClock.publishVideoTime(300_000L);
        check(bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot()) == 0, "seek should admit no old-capture audio");
        check(bridge.isInvalidated(), "seek must invalidate active capture continuity");

        System.out.println("AudioVideoTimeBridgeV2331Test OK");
    }
}
