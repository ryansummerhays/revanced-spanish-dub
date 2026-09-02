package app.spanishstudy.vot;

import java.util.List;

public final class SemanticClauseSplitterTest {
    public static void main(String[] args) {
        shortSentenceStaysWhole();
        longSentencePrefersPunctuationPause();
        distantSentenceBoundaryStillSplits();
        multipleSentencesAreRecursivelySeparated();
        unpunctuatedThoughtDoesNotGetArbitrarilyChopped();
        conjunctionAloneDoesNotCreateTtsStop();
        reconstructionPreservesWords();
        weakRelativeClauseIsNotPreferredBoundary();
        System.out.println("semantic clause splitter: OK");
    }

    private static void shortSentenceStaysWhole() {
        String s = "I went home because I was tired.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 1, "short sentence should stay whole");
        require(parts.get(0).equals(s), "short sentence changed");
    }

    private static void longSentencePrefersPunctuationPause() {
        String s = "I wanted to finish the project before dinner, but the last experiment took much longer than expected, so I stayed another hour to make sure the result was real.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 2, "long punctuated sentence should split at a natural pause");
        require(parts.get(0).endsWith(","), "first split should preserve the punctuation pause");
        for (String part : parts) {
            require(part.length() >= 12, "created tiny fragment: " + part);
        }
    }

    private static void distantSentenceBoundaryStillSplits() {
        String s = "If you were in a boat directly over the Mariana Trench and dropped a seven kilogram bowling ball over the side, how long would it take to hit the bottom? It's a good thing you mentioned the mass.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 2, "terminal punctuation beyond the old search window must still split");
        require(parts.get(parts.size() - 2).endsWith("?"),
                "question boundary should remain a natural subtitle event");
    }

    private static void multipleSentencesAreRecursivelySeparated() {
        String s = "This first sentence deliberately runs longer than the preferred subtitle width before it finally ends. This second sentence also has enough words to require its own event. The third sentence should not be glued onto either of them.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 3, "multiple complete sentences should become separate events");
        require(parts.get(0).endsWith("."), "first sentence boundary lost");
        require(parts.get(1).endsWith("."), "second sentence boundary lost");
    }

    private static void unpunctuatedThoughtDoesNotGetArbitrarilyChopped() {
        String s = "This deliberately long unpunctuated spoken thought has no trustworthy pause cue anywhere near the display target and should remain intact instead of making the voice stop at some random width boundary";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 1,
                "unpunctuated thought should remain whole when no natural pause exists");
    }

    private static void conjunctionAloneDoesNotCreateTtsStop() {
        String s = "I kept trying the same setup for much longer than I expected because the first few results looked inconsistent enough that I wanted another clean comparison before changing anything";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 1,
                "conjunction alone should not invent a speech pause or TTS clip boundary");
    }

    private static void reconstructionPreservesWords() {
        String s = "The first idea is complete, and the second idea explains why it matters, because both languages must show the same meaning when the video is paused.";
        List<String> parts = SemanticClauseSplitter.split(s);
        String rebuilt = String.join(" ", parts).replaceAll("\\s+", " ").trim();
        require(rebuilt.equals(s), "splitter changed source text: " + rebuilt);
    }

    private static void weakRelativeClauseIsNotPreferredBoundary() {
        String s = "This is the controller that I bought after watching the review which explained the buttons that matter most during normal play";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 1, "relative clauses without punctuation should remain in one phrase");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
