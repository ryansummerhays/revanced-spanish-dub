package app.spanishstudy.vot;

public final class CaptionNamedSpeakerStoreTest {
    public static void main(String[] args) {
        extractsNamedSpeaker();
        keepsRecurringNameStable();
        bareTurnClearsIdentity();
        rejectsSoundLabels();
        resetClearsRoster();
        System.out.println("caption named speaker store: OK");
    }

    private static void extractsNamedSpeaker() {
        CaptionNamedSpeakerStore.beginTranscript();
        CaptionNamedSpeakerStore.markTurn(1000, "JOHN: hello there");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1000) == 0, "JOHN should map to first speaker");
        require(CaptionNamedSpeakerStore.namedSpeakerCount() == 1, "expected one named speaker");
    }

    private static void keepsRecurringNameStable() {
        CaptionNamedSpeakerStore.beginTranscript();
        CaptionNamedSpeakerStore.markTurn(1000, "JOHN: first");
        CaptionNamedSpeakerStore.markTurn(2000, "MARY JANE: second");
        CaptionNamedSpeakerStore.markTurn(3000, "JOHN: again");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1000) == 0, "JOHN first index");
        require(CaptionNamedSpeakerStore.speakerIndexAt(2000) == 1, "MARY JANE second index");
        require(CaptionNamedSpeakerStore.speakerIndexAt(3000) == 0, "JOHN should reuse original index");
    }

    private static void bareTurnClearsIdentity() {
        CaptionNamedSpeakerStore.beginTranscript();
        CaptionNamedSpeakerStore.markTurn(1000, "JOHN: hello");
        CaptionNamedSpeakerStore.markTurn(2000, "hello from someone else");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1500) == 0, "named identity should propagate until next turn");
        require(CaptionNamedSpeakerStore.speakerIndexAt(2000) == -1, "bare turn must clear identity rather than guess");
        require(CaptionNamedSpeakerStore.speakerIndexAt(2500) == -1, "anonymous turn should remain unknown");
    }

    private static void rejectsSoundLabels() {
        CaptionNamedSpeakerStore.beginTranscript();
        CaptionNamedSpeakerStore.markTurn(1000, "MUSIC: theme starts");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1000) == -1, "MUSIC must not become a speaker");
    }

    private static void resetClearsRoster() {
        CaptionNamedSpeakerStore.beginTranscript();
        CaptionNamedSpeakerStore.markTurn(1000, "JOHN: hello");
        CaptionNamedSpeakerStore.beginTranscript();
        require(CaptionNamedSpeakerStore.namedSpeakerCount() == 0, "reset should clear speaker roster");
        require(CaptionNamedSpeakerStore.speakerIndexAt(1000) == -1, "reset should clear timeline");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
