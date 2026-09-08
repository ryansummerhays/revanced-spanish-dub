package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Per-video historical speaker intervals expressed only in absolute YouTube video milliseconds. */
public final class SpeakerTimeline {
    private final List<Segment> segments = new ArrayList<>();
    private long videoEpoch = -1L;

    public synchronized void beginVideo(long newVideoEpoch) {
        if (videoEpoch == newVideoEpoch) return;
        videoEpoch = newVideoEpoch;
        segments.clear();
    }

    public synchronized void clear() {
        segments.clear();
        videoEpoch = -1L;
    }

    public synchronized boolean append(long segmentVideoEpoch, long continuityEpoch,
                                       long startVideoMs, long endVideoMs,
                                       String speakerId, String source) {
        if (segmentVideoEpoch != videoEpoch || startVideoMs < 0L || endVideoMs <= startVideoMs
                || speakerId == null || speakerId.isEmpty()) return false;
        segments.add(new Segment(segmentVideoEpoch, continuityEpoch, startVideoMs, endVideoMs,
                speakerId, source == null ? "unknown" : source));
        return true;
    }

    public synchronized List<Segment> snapshot() {
        return Collections.unmodifiableList(new ArrayList<>(segments));
    }

    public synchronized long getVideoEpoch() { return videoEpoch; }

    public static final class Segment {
        public final long videoEpoch;
        public final long continuityEpoch;
        public final long startVideoMs;
        public final long endVideoMs;
        public final String speakerId;
        public final String source;

        Segment(long videoEpoch, long continuityEpoch, long startVideoMs, long endVideoMs,
                String speakerId, String source) {
            this.videoEpoch = videoEpoch;
            this.continuityEpoch = continuityEpoch;
            this.startVideoMs = startVideoMs;
            this.endVideoMs = endVideoMs;
            this.speakerId = speakerId;
            this.source = source;
        }
    }
}
