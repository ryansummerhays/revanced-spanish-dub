package app.spanishstudy.vot;

import java.util.List;

public final class SemanticClauseSplitterTest {
    public static void main(String[] args) {
        shortSentenceStaysWhole();
        shortTwoSentencesStillSplit();
        longSentencePrefersPunctuationPause();
        distantSentenceBoundaryStillSplits();
        multipleSentencesAreRecursivelySeparated();
        unpunctuatedThoughtDoesNotGetArbitrarilyChopped();
        conjunctionAloneDoesNotCreateTtsStop();
        strongTimingPauseRestoresPeriod();
        mediumTimingPauseRestoresComma();
        longDiscourseRunOnGetsConservativeComma();
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

    private static void shortTwoSentencesStillSplit() {
        String s = "We found the trail. Then we headed home safely.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 2, "internal sentence pause should split even under width target");
        require(parts.get(0).endsWith("."), "first short sentence boundary lost");
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
                "weak conjunction alone should not invent a speech pause or TTS clip boundary");
    }

    private static void strongTimingPauseRestoresPeriod() {
        String s = "we finished the first test then we checked the result carefully";
        // 11 lexical words -> 10 inter-word gaps. The 620ms pause after "test" is strong evidence.
        long[] gaps = {30, 35, 40, 620, 35, 30, 35, 30, 30, 30};
        List<String> parts = SemanticClauseSplitter.split(s, gaps);
        require(parts.size() == 2, "strong measured pause should make two spoken phrases: " + parts);
        require(parts.get(0).endsWith("."), "strong pause should restore terminal punctuation");
        require(parts.get(0).equals("we finished the first test."), "unexpected first phrase: " + parts.get(0));
    }

    private static void mediumTimingPauseRestoresComma() {
        String s = "we kept walking toward the ridge but the weather changed very quickly after that";
        // 14 words -> 13 gaps. 300ms before "but" should restore a comma and give the long run-on
        // a natural clause boundary without pretending it was a full sentence stop.
        long[] gaps = {25, 30, 25, 30, 25, 300, 25, 25, 30, 25, 30, 25, 25};
        String restored = SemanticClauseSplitter.restorePunctuation(s, gaps);
        require(restored.contains("ridge, but"), "medium pause did not restore comma: " + restored);
        List<String> parts = SemanticClauseSplitter.split(s, gaps);
        require(parts.size() >= 2, "restored pause should become a natural phrase boundary");
    }

    private static void longDiscourseRunOnGetsConservativeComma() {
        String s = "I thought the road would keep climbing for another mile but the grade suddenly flattened out and the whole valley opened in front of us";
        String restored = SemanticClauseSplitter.restorePunctuation(s, null);
        require(restored.contains("mile, but"), "high-confidence discourse run-on should gain comma: " + restored);
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
