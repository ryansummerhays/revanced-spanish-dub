package app.spanishstudy.vot;

public final class CaptionSpeakerTurnStoreTest {
    public static void main(String[] args) {
        detectsLeadingTurnMarker();
        approximatesMidChunkTurn();
        stripsMarkersWithoutJoiningWords();
        clearsBetweenVideos();
        System.out.println("caption speaker turn store: OK");
    }

    private static void detectsLeadingTurnMarker() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(1000, 1800, ">> hello there");
        require(CaptionSpeakerTurnStore.count() == 1, "expected one speaker turn");
        require(CaptionSpeakerTurnStore.isTurnStartNear(1000),
                "leading marker should map to chunk start");
    }

    private static void approximatesMidChunkTurn() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(0, 1000, "hello >> goodbye");
        require(CaptionSpeakerTurnStore.count() == 1, "mid-chunk marker missing");
        require(CaptionSpeakerTurnStore.hasBoundaryBetween(250, 800),
                "marker should be discoverable between adjacent word times");
    }

    private static void stripsMarkersWithoutJoiningWords() {
        String cleaned = CaptionSpeakerTurnStore.stripMarkers("hello>>there  >> friend");
        require(cleaned.equals("hello there friend"),
                "marker stripping must preserve word separation: " + cleaned);
    }

    private static void clearsBetweenVideos() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(500, 900, ">> hello");
        require(CaptionSpeakerTurnStore.count() == 1, "setup failed");
        CaptionSpeakerTurnStore.beginTranscript();
        require(CaptionSpeakerTurnStore.count() == 0, "speaker turns leaked across transcripts");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
