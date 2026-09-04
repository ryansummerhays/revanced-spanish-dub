package app.spanishstudy.vot;

import java.util.List;

public final class SourceCaptionTimingStoreTest {
    public static void main(String[] args) {
        usesInnerCaptionTiming();
        exposesMeasuredInterWordPause();
        promotesLabelledSpeakerTurnToHardPause();
        bareCueDoesNotPretendSpeakerChange();
        rejectsAmbiguousAlignment();
        System.out.println("source caption timing store: OK");
    }

    private static void usesInnerCaptionTiming() {
        CaptionSpeakerTurnStore.beginTranscript();
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

    private static void exposesMeasuredInterWordPause() {
        CaptionSpeakerTurnStore.beginTranscript();
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(1000, 1600, "I think ");
        SourceCaptionTimingStore.addTimedChunk(1600, 2600, "this is fine ");
        SourceCaptionTimingStore.addTimedChunk(3150, 3900, "but we should leave");

        long[] gaps = SourceCaptionTimingStore.interWordGaps(
                1000, 3900, "I think this is fine but we should leave");
        require(gaps != null && gaps.length == 8, "expected one gap between each lexical word");
        require(gaps[4] >= 500, "pause after fine should remain visible, got " + gaps[4]);
        require(gaps[1] < 200, "normal within-speech transition should stay small, got " + gaps[1]);
    }

    private static void promotesLabelledSpeakerTurnToHardPause() {
        CaptionSpeakerTurnStore.beginTranscript();
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(0, 1000, "I agree ");
        CaptionSpeakerTurnStore.markFromChunk(1000, 1050, ">> MARY:");
        SourceCaptionTimingStore.addTimedChunk(1050, 2000, "no wait");

        long[] gaps = SourceCaptionTimingStore.interWordGaps(
                0, 2000, "I agree no wait");
        require(gaps != null && gaps.length == 3, "expected aligned labelled speaker-turn sentence");
        require(gaps[1] >= 1000,
                "explicit labelled speaker change must act as a hard phrase pause, got " + gaps[1]);
    }

    private static void bareCueDoesNotPretendSpeakerChange() {
        CaptionSpeakerTurnStore.beginTranscript();
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(0, 1000, "I agree ");
        CaptionSpeakerTurnStore.markFromChunk(1000, 1050, ">>");
        SourceCaptionTimingStore.addTimedChunk(1050, 2000, "no wait");

        long[] gaps = SourceCaptionTimingStore.interWordGaps(
                0, 2000, "I agree no wait");
        require(gaps != null && gaps.length == 3, "expected aligned bare-cue sentence");
        require(gaps[1] < 1000,
                "bare caption cue must not manufacture a hard speaker pause, got " + gaps[1]);
    }

    private static void rejectsAmbiguousAlignment() {
        CaptionSpeakerTurnStore.beginTranscript();
        SourceCaptionTimingStore.beginTranscript();
        SourceCaptionTimingStore.addTimedChunk(0, 1000, "completely different words");
        long[] ends = SourceCaptionTimingStore.phraseEndTimes(
                0, 1000, "hello there friend", List.of("hello there", "friend"));
        require(ends == null, "unrelated timing stream must not be guessed");
        require(SourceCaptionTimingStore.interWordGaps(0, 1000, "hello there friend") == null,
                "ambiguous pause timing must not be guessed");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
