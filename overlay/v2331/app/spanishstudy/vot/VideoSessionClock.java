package app.spanishstudy.vot;

import java.util.Objects;

/**
 * Authoritative content-time state for one YouTube video session.
 *
 * Rules:
 * - YouTube video milliseconds are the master content clock.
 * - Repeated lifecycle callbacks for the same open video do not reset state.
 * - Pause/resume/minimize/PiP do not create a new epoch.
 * - A seek/discontinuity increments continuityEpoch but keeps the video identity.
 * - A different video, or closing and reopening a video, creates a new videoEpoch.
 */
public final class VideoSessionClock {
    private static final Object LOCK = new Object();
    private static final long AUTO_DISCONTINUITY_MS = 2_500L;

    private static String activeVideoId = "";
    private static boolean open;
    private static long videoEpoch;
    private static long continuityEpoch;
    private static long videoMs = -1L;
    private static long previousVideoMs = -1L;
    private static long updates;
    private static long explicitSeeks;
    private static long detectedDiscontinuities;
    private static boolean explicitSeekPending;

    private VideoSessionClock() {}

    public static boolean onVideoOpened(String videoId) {
        final String id = videoId == null ? "" : videoId;
        synchronized (LOCK) {
            if (open && Objects.equals(activeVideoId, id)) return false;
            activeVideoId = id;
            open = !id.isEmpty();
            videoEpoch++;
            continuityEpoch = 0L;
            videoMs = -1L;
            previousVideoMs = -1L;
            updates = 0L;
            explicitSeeks = 0L;
            detectedDiscontinuities = 0L;
            explicitSeekPending = false;
            return true;
        }
    }

    public static void onVideoClosed() {
        synchronized (LOCK) {
            activeVideoId = "";
            open = false;
            continuityEpoch++;
            videoMs = -1L;
            previousVideoMs = -1L;
            updates = 0L;
            explicitSeekPending = false;
        }
    }

    public static void publishVideoTime(long timeMs) {
        if (timeMs < 0L) return;
        synchronized (LOCK) {
            if (!open) return;
            boolean discontinuity = false;
            boolean explicit = explicitSeekPending;
            if (videoMs >= 0L) {
                long delta = timeMs - videoMs;
                discontinuity = Math.abs(delta) > AUTO_DISCONTINUITY_MS;
                previousVideoMs = videoMs;
            }
            if (explicit || discontinuity) {
                continuityEpoch++;
                if (explicit) explicitSeeks++;
                else detectedDiscontinuities++;
            }
            explicitSeekPending = false;
            videoMs = timeMs;
            updates++;
        }
    }

    public static void markExplicitSeek() {
        synchronized (LOCK) {
            if (open) explicitSeekPending = true;
        }
    }

    public static Snapshot snapshot() {
        synchronized (LOCK) {
            return new Snapshot(activeVideoId, open, videoEpoch, continuityEpoch,
                    videoMs, previousVideoMs, updates, explicitSeeks,
                    detectedDiscontinuities, explicitSeekPending);
        }
    }

    public static final class Snapshot {
        public final String videoId;
        public final boolean open;
        public final long videoEpoch;
        public final long continuityEpoch;
        public final long videoMs;
        public final long previousVideoMs;
        public final long updates;
        public final long explicitSeeks;
        public final long detectedDiscontinuities;
        public final boolean explicitSeekPending;

        private Snapshot(String videoId, boolean open, long videoEpoch, long continuityEpoch,
                         long videoMs, long previousVideoMs, long updates,
                         long explicitSeeks, long detectedDiscontinuities,
                         boolean explicitSeekPending) {
            this.videoId = videoId;
            this.open = open;
            this.videoEpoch = videoEpoch;
            this.continuityEpoch = continuityEpoch;
            this.videoMs = videoMs;
            this.previousVideoMs = previousVideoMs;
            this.updates = updates;
            this.explicitSeeks = explicitSeeks;
            this.detectedDiscontinuities = detectedDiscontinuities;
            this.explicitSeekPending = explicitSeekPending;
        }
    }
}
