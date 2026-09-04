package app.spanishstudy.vot;

public final class CaptionSpeakerTurnStoreTest {
    public static void main(String[] args) {
        bareMarkerIsCueNotSpeaker();
        labelledMarkerIsHardSpeakerBoundary();
        bracketedLabelIsAccepted();
        lowerCaseSentenceColonIsRejected();
        approximatesMidChunkLabelledTurn();
        stripsMarkersWithoutJoiningWords();
        clearsBetweenVideos();
        System.out.println("caption speaker turn store: OK");
    }

    private static void bareMarkerIsCueNotSpeaker() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(1000, 1800, ">> hello there");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "expected one raw cue marker");
        require(CaptionSpeakerTurnStore.count() == 0,
                "bare >> must not be promoted to speaker identity evidence");
        require(!CaptionSpeakerTurnStore.isTurnStartNear(1000),
                "bare cue must not become a hard speaker boundary");
    }

    private static void labelledMarkerIsHardSpeakerBoundary() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(1000, 1800, ">> JOHN: hello there");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "raw marker missing");
        require(CaptionSpeakerTurnStore.count() == 1, "labelled speaker turn missing");
        require(CaptionSpeakerTurnStore.isTurnStartNear(1000),
                "labelled leading marker should map to chunk start");
    }

    private static void bracketedLabelIsAccepted() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(0, 1000, ">> [Narrator]: hello");
        require(CaptionSpeakerTurnStore.count() == 1, "bracketed explicit speaker label missing");
    }

    private static void lowerCaseSentenceColonIsRejected() {
        CaptionSpeakerTurnStore.beginTranscript();
        CaptionSpeakerTurnStore.markFromChunk(0, 1000, ">> well: I think so");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "cue marker missing");
        require(CaptionSpeakerTurnStore.count() == 0,
                "ordinary lower-case clause before colon must not become a speaker label");
    }

    private static void approximatesMidChunkLabelledTurn() {
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
        CaptionSpeakerTurnStore.markFromChunk(500, 900, ">> HOST: hello");
        require(CaptionSpeakerTurnStore.count() == 1, "setup failed");
        require(CaptionSpeakerTurnStore.markerCount() == 1, "marker setup failed");
        CaptionSpeakerTurnStore.beginTranscript();
        require(CaptionSpeakerTurnStore.count() == 0, "speaker turns leaked across transcripts");
        require(CaptionSpeakerTurnStore.markerCount() == 0, "cue markers leaked across transcripts");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
