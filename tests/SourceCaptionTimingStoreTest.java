package app.spanishstudy.vot;

import java.util.List;

public final class SourceCaptionTimingStoreTest {
    public static void main(String[] args) {
        usesInnerCaptionTiming();
        rejectsAmbiguousAlignment();
        System.out.println("source caption timing store: OK");
    }

    private static void usesInnerCaptionTiming() {
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(1000, 1600, "I think ");
        SourceCaptionTimingStore.addTimedChunk(1600, 2600, "this is fine, ");
        SourceCaptionTimingStore.addTimedChunk(3100, 3900, "but we should leave.");

        long[] ends = SourceCaptionTimingStore.phraseEndTimes(
                1000, 3900,
                "I think this is fine, but we should leave.",
                List.of("I think this is fine,", "but we should leave."));

        require(ends != null && ends.length == 2, "expected measured phrase timing");
        require(ends[0] >= 2500 && ends[0] <= 3150,
                "first phrase should end near real caption pause, got " + ends[0]);
        require(ends[1] == 3900, "last phrase must keep sentence end");
    }

    private static void rejectsAmbiguousAlignment() {
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(0, 1000, "completely different words");
        long[] ends = SourceCaptionTimingStore.phraseEndTimes(
                0, 1000, "hello there friend", List.of("hello there", "friend"));
        require(ends == null, "unrelated timing stream must not be guessed");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
