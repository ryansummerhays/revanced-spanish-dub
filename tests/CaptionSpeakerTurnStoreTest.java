package app.spanishstudy.vot;

public final class CaptionSpeakerTurnStoreTest {
    public static void main(String[] args) {
        bareMarkerIsCueOnly();
        labelledMarkerIsHardTurn();
        labelledMidChunkTurnIsTimed();
        stripsMarkersWithoutJoiningWords();
        clearsBetweenVideos();
        System.out.println("caption speaker turn store: OK");
    }

    private static void bareMarkerIsCueOnly() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(1000, 1800, ">> hello there");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "expected one raw cue marker");
        require(CaptionSpeakerTurnStore.count() == 0,
                "bare >> must not be treated as a confirmed speaker change");
        require(!CaptionSpeakerTurnStore.isTurnStartNear(1000),
                "bare cue must not become a hard phrase boundary");
    }

    private static void labelledMarkerIsHardTurn() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(1000, 1800, ">> JOHN: hello there");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "expected raw marker");
        require(CaptionSpeakerTurnStore.count() == 1, "labelled speaker turn missing");
        require(CaptionSpeakerTurnStore.isTurnStartNear(1000),
                "labelled marker should map to chunk start");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1000) == 0,
                "labelled speaker identity should remain available downstream");
    }

    private static void labelledMidChunkTurnIsTimed() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(0, 1000, "hello >> MARY: goodbye");
        require(CaptionSpeakerTurnStore.count() == 1, "mid-chunk labelled marker missing");
        require(CaptionSpeakerTurnStore.hasBoundaryBetween(250, 800),
                "labelled marker should be discoverable between adjacent word times");
    }

    private static void stripsMarkersWithoutJoiningWords() {
        String cleaned = CaptionSpeakerTurnStore.stripMarkers("hello>>there  >> friend");
        require(cleaned.equals("hello there friend"),
                "marker stripping must preserve word separation: " + cleaned);
    }

    private static void clearsBetweenVideos() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(500, 900, ">> JOHN: hello");
        require(CaptionSpeakerTurnStore.count() == 1, "setup failed");
        CaptionSpeakerTurnStore.beginTranscript();
        require(CaptionSpeakerTurnStore.count() == 0, "speaker turns leaked across transcripts");
        require(CaptionSpeakerTurnStore.markerCount() == 0, "cue markers leaked across transcripts");
        require(CaptionNamedSpeakerStore.namedSpeakerCount() == 0, "named identities leaked across transcripts");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
