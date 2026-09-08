import app.spanishstudy.vot.VideoSessionClock;

public final class VideoSessionClockV2331Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        VideoSessionClock.onVideoClosed();

        check(VideoSessionClock.onVideoOpened("video-A"), "first video must open new epoch");
        long epochA = VideoSessionClock.snapshot().videoEpoch;
        VideoSessionClock.publishVideoTime(180_000L);
        check(VideoSessionClock.snapshot().videoMs == 180_000L, "master time must publish");

        check(!VideoSessionClock.onVideoOpened("video-A"), "duplicate lifecycle callback must not reset");
        check(VideoSessionClock.snapshot().videoMs == 180_000L, "duplicate open contaminated time");
        check(VideoSessionClock.snapshot().videoEpoch == epochA, "duplicate open changed epoch");

        VideoSessionClock.Snapshot paused = VideoSessionClock.snapshot();
        check(paused.videoMs == 180_000L && paused.continuityEpoch == 0L, "pause should preserve state");

        VideoSessionClock.markExplicitSeek();
        check(VideoSessionClock.snapshot().continuityEpoch == 0L, "seek marker should wait for new clock sample");
        VideoSessionClock.publishVideoTime(480_000L);
        VideoSessionClock.Snapshot seeked = VideoSessionClock.snapshot();
        check(seeked.videoEpoch == epochA, "seek must keep speaker/video identity epoch");
        check(seeked.continuityEpoch == 1L, "explicit seek must create exactly one continuity epoch");
        check(seeked.explicitSeeks == 1L, "explicit seek count wrong");
        check(seeked.detectedDiscontinuities == 0L, "explicit seek double-counted as auto discontinuity");
        check(seeked.videoMs == 480_000L, "seek master time wrong");

        VideoSessionClock.publishVideoTime(490_000L);
        check(VideoSessionClock.snapshot().continuityEpoch == 2L, "unannounced large jump should create continuity epoch");
        check(VideoSessionClock.snapshot().detectedDiscontinuities == 1L, "auto discontinuity count wrong");

        check(VideoSessionClock.onVideoOpened("video-B"), "different id must create new video session");
        VideoSessionClock.Snapshot b = VideoSessionClock.snapshot();
        check(b.videoEpoch > epochA, "new video did not advance epoch");
        check(b.continuityEpoch == 0L && b.videoMs == -1L && b.updates == 0L,
                "new video inherited per-video timing state");

        long epochB = b.videoEpoch;
        VideoSessionClock.onVideoClosed();
        check(!VideoSessionClock.snapshot().open, "close did not close session");
        check(VideoSessionClock.onVideoOpened("video-B"), "reopen after full close must be fresh session");
        check(VideoSessionClock.snapshot().videoEpoch > epochB, "reopen same id contaminated old session");

        System.out.println("VideoSessionClockV2331Test OK");
    }
}
