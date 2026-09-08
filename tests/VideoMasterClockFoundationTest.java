package app.spanishstudy.vot;

public final class VideoMasterClockFoundationTest {
    public static void main(String[] args) {
        testSessionLifecycle();
        testDuplicatePcmCannotOutrunVideo();
        testSeekInvalidatesPartialCapture();
        testTimelineRejectsOldVideo();
        System.out.println("PASS VideoMasterClockFoundationTest");
    }

    private static void testSessionLifecycle() {
        check(VideoSessionClock.onVideoOpened("A"), "A should create video session");
        VideoSessionClock.publishVideoTime(100_000L);
        VideoSessionClock.Snapshot a = VideoSessionClock.snapshot();
        long epochA = a.videoEpoch;
        check(a.open && a.videoMs == 100_000L && a.continuityEpoch == 0L, "initial A clock");

        check(!VideoSessionClock.onVideoOpened("A"), "same open video must not reset");
        VideoSessionClock.publishVideoTime(100_020L);
        VideoSessionClock.Snapshot same = VideoSessionClock.snapshot();
        check(same.videoEpoch == epochA && same.continuityEpoch == 0L, "same-video lifecycle kept");

        VideoSessionClock.markExplicitSeek();
        VideoSessionClock.publishVideoTime(180_000L);
        VideoSessionClock.Snapshot seek = VideoSessionClock.snapshot();
        check(seek.videoEpoch == epochA && seek.continuityEpoch == 1L && seek.explicitSeeks == 1L,
                "seek must keep video identity and start new continuity");

        check(VideoSessionClock.onVideoOpened("B"), "B should create fresh video session");
        VideoSessionClock.Snapshot b = VideoSessionClock.snapshot();
        check(b.videoEpoch > epochA && b.continuityEpoch == 0L && b.videoMs == -1L,
                "new id must reset per-video clock state");

        long epochB = b.videoEpoch;
        VideoSessionClock.onVideoClosed();
        check(!VideoSessionClock.snapshot().open, "full close must close session");
        check(VideoSessionClock.onVideoOpened("B"), "reopening same id after close must be fresh");
        check(VideoSessionClock.snapshot().videoEpoch > epochB, "reopen after full close needs new epoch");
    }

    private static void testDuplicatePcmCannotOutrunVideo() {
        VideoSessionClock.onVideoClosed();
        VideoSessionClock.onVideoOpened("PCM");
        VideoSessionClock.publishVideoTime(0L);
        AudioVideoTimeBridge bridge = new AudioVideoTimeBridge();

        // Anchor callback is intentionally admitted as zero samples.
        check(bridge.permitSamples(320, 16_000, VideoSessionClock.snapshot()) == 0,
                "anchor callback must not speculate ahead");

        long accepted = 0L;
        for (int t = 20; t <= 20_000; t += 20) {
            VideoSessionClock.publishVideoTime(t);
            // Simulate the failure mode: four nominal 20 ms buffers arrive for each 20 ms of
            // actual YouTube content progress. Only one callback's worth may advance the stream.
            for (int duplicate = 0; duplicate < 4; duplicate++) {
                accepted += bridge.permitSamples(320, 16_000, VideoSessionClock.snapshot());
            }
        }
        check(accepted == 320_000L, "20 seconds of video must admit exactly 320k @16k, got " + accepted);
        check(bridge.getAcceptedSamples() == 320_000L, "bridge accepted counter");
        check(bridge.getCaptureVideoSpanMs() == 20_000L, "bridge absolute video span");
        check(bridge.getRejectedDuplicateOrAheadSamples() > bridge.getAcceptedSamples(),
                "duplicate callbacks should be visibly rejected");
    }

    private static void testSeekInvalidatesPartialCapture() {
        VideoSessionClock.onVideoClosed();
        VideoSessionClock.onVideoOpened("SEEK");
        VideoSessionClock.publishVideoTime(10_000L);
        AudioVideoTimeBridge bridge = new AudioVideoTimeBridge();
        bridge.permitSamples(320, 16_000, VideoSessionClock.snapshot());
        VideoSessionClock.publishVideoTime(10_020L);
        check(bridge.permitSamples(320, 16_000, VideoSessionClock.snapshot()) == 320,
                "normal continuity admits samples");

        VideoSessionClock.markExplicitSeek();
        VideoSessionClock.publishVideoTime(50_000L);
        check(bridge.permitSamples(320, 16_000, VideoSessionClock.snapshot()) == 0,
                "old partial capture must stop after seek");
        check(bridge.isInvalidated(), "seek must invalidate old continuity capture");
    }

    private static void testTimelineRejectsOldVideo() {
        SpeakerTimeline timeline = new SpeakerTimeline();
        timeline.beginVideo(10L);
        check(timeline.append(10L, 0L, 1_000L, 2_000L, "A", "stage-j"), "current epoch append");
        check(!timeline.append(9L, 0L, 2_000L, 3_000L, "B", "sherpa"), "old video must be rejected");
        check(timeline.snapshot().size() == 1, "old-video segment contaminated timeline");
        timeline.beginVideo(11L);
        check(timeline.snapshot().isEmpty(), "new video must clear timeline");
    }

    private static void check(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }
}
