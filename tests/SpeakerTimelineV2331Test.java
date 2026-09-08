import app.spanishstudy.vot.SpeakerTimeline;

public final class SpeakerTimelineV2331Test {
    private static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        SpeakerTimeline t = new SpeakerTimeline();
        t.beginVideo(10L);
        check(t.append(10L, 0L, 1000L, 1800L, "A", "stage-j"), "valid interval rejected");
        check(t.append(10L, 0L, 1800L, 2500L, "N0", "sherpa"), "valid neural interval rejected");
        check(!t.append(9L, 0L, 2500L, 3000L, "A", "old-video"), "old video contamination accepted");
        check(t.snapshot().size() == 2, "timeline size wrong");
        t.beginVideo(11L);
        check(t.snapshot().isEmpty(), "new video did not clear timeline");
        System.out.println("SpeakerTimelineV2331Test OK");
    }
}
