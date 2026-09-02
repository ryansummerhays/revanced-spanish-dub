package app.spanishstudy.vot;

public final class TranscriptCorrectionStoreTest {
    public static void main(String[] args) {
        shortJargonCorrectionIsAllowed();
        longParaphraseIsRejected();
        localProperNounFixIsAllowed();
        System.out.println("transcript correction store: OK");
    }

    private static void shortJargonCorrectionIsAllowed() {
        TranscriptCorrectionStore.clear();
        TranscriptCorrectionStore.put(100, 200, "Try the DVO", "Try the Devo");
        require("Try the Devo".equals(TranscriptCorrectionStore.get(100, 200, "Try the DVO")),
                "short domain-term correction should be accepted");
    }

    private static void longParaphraseIsRejected() {
        TranscriptCorrectionStore.clear();
        String raw = "I think this weapon is probably better for the next fight because it has more ammo";
        String rewrite = "The gun seems ideal for combat since its magazine capacity is considerably larger";
        TranscriptCorrectionStore.put(300, 400, raw, rewrite);
        require(raw.equals(TranscriptCorrectionStore.get(300, 400, raw)),
                "broad English paraphrase should not replace the raw source");
    }

    private static void localProperNounFixIsAllowed() {
        TranscriptCorrectionStore.clear();
        String raw = "I get out ahead of her rock tomb plans with a rock tomb of my own";
        String corrected = "I get out ahead of her Rock Tomb plans with a Rock Tomb of my own";
        TranscriptCorrectionStore.put(500, 600, raw, corrected);
        require(corrected.equals(TranscriptCorrectionStore.get(500, 600, raw)),
                "capitalization/proper-name correction should be accepted");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
