import app.spanishstudy.vot.AudioVideoTimeBridge;
import app.spanishstudy.vot.SpeakerTimeline;
import app.spanishstudy.vot.VideoSessionClock;

public final class VideoMasterClockFoundationV2331Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        VideoSessionClock.onVideoClosed();
        check(VideoSessionClock.onVideoOpened("A"), "first open must create video epoch");
        long epochA = VideoSessionClock.snapshot().videoEpoch;
        VideoSessionClock.publishVideoTime(100_000L);
        check(!VideoSessionClock.onVideoOpened("A"), "same-video lifecycle noise reset state");
        check(VideoSessionClock.snapshot().videoMs == 100_000L, "same-video state lost");

        VideoSessionClock.markExplicitSeek();
        VideoSessionClock.publishVideoTime(180_000L);
        check(VideoSessionClock.snapshot().videoEpoch == epochA, "seek changed video identity");
        check(VideoSessionClock.snapshot().continuityEpoch == 1L, "seek failed continuity reset");

        check(VideoSessionClock.onVideoOpened("B"), "new id failed new session");
        long epochB = VideoSessionClock.snapshot().videoEpoch;
        check(epochB > epochA && VideoSessionClock.snapshot().videoMs == -1L, "new video inherited clock");
        VideoSessionClock.onVideoClosed();
        check(VideoSessionClock.onVideoOpened("B"), "reopen after full close not fresh");
        check(VideoSessionClock.snapshot().videoEpoch > epochB, "reopened video contaminated old session");

        // Four nominal 20-ms PCM callbacks per real 20 ms of video must not accelerate neural time.
        VideoSessionClock.onVideoClosed();
        VideoSessionClock.onVideoOpened("dup");
        VideoSessionClock.publishVideoTime(200_000L);
        AudioVideoTimeBridge bridge = new AudioVideoTimeBridge();
        final int sr = 16_000;
        final int chunk = 320;
        check(bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot()) == 0, "anchor consumed PCM");
        for (int step = 1; step <= 1000; step++) {
            VideoSessionClock.publishVideoTime(200_000L + step * 20L);
            for (int duplicate = 0; duplicate < 4; duplicate++)
                bridge.permitSamples(chunk, sr, VideoSessionClock.snapshot());
        }
        check(bridge.getAcceptedSamples() == 320_000L,
                "20 seconds of video must admit exactly 320000 samples, got " + bridge.getAcceptedSamples());
        check(bridge.getCaptureVideoSpanMs() == 20_000L, "neural capture not video-clock bounded");
        check(bridge.getRejectedDuplicateOrAheadSamples() > 0L, "duplicate PCM not rejected");

        SpeakerTimeline timeline = new SpeakerTimeline();
        long epoch = VideoSessionClock.snapshot().videoEpoch;
        timeline.beginVideo(epoch);
        check(timeline.append(epoch, 0L, 200_000L, 201_000L, "A", "stage-j"), "timeline rejected valid segment");
        check(!timeline.append(epoch - 1L, 0L, 201_000L, 202_000L, "A", "old-video"), "old video contaminated timeline");
        timeline.beginVideo(epoch + 1L);
        check(timeline.snapshot().isEmpty(), "new video failed timeline reset");

        System.out.println("VideoMasterClockFoundationV2331Test OK");
    }
}
