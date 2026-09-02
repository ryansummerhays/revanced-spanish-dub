package app.spanishstudy.vot;

import java.util.List;

public final class SemanticClauseSplitterTest {
    public static void main(String[] args) {
        shortSentenceStaysWhole();
        longSentencePrefersClauseBoundary();
        hardLimitFallsBackToWordBoundary();
        reconstructionPreservesWords();
        normalClausesStayWithinOneLineCeiling();
        targetRangeIsProfessionalOneLineRange();
        System.out.println("semantic clause splitter: OK");
    }

    private static void shortSentenceStaysWhole() {
        String s = "I went home because I was tired.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() == 1, "short sentence should stay whole");
        require(parts.get(0).equals(s), "short sentence changed");
    }

    private static void longSentencePrefersClauseBoundary() {
        String s = "I wanted to finish the project before dinner, but the last experiment took much longer than expected, so I stayed another hour to make sure the result was real.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 3, "long sentence should split into compact semantic units");
        for (String part : parts) {
            require(part.length() >= 10, "created tiny fragment: " + part);
        }
    }

    private static void hardLimitFallsBackToWordBoundary() {
        String s = "This is a deliberately long unpunctuated stretch of speech where the caption source gives us no commas or sentence marks and we still need a readable compact subtitle without chopping a word in half at an arbitrary character position";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 4, "hard-max fallback did not split enough");
        for (String part : parts) {
            require(!part.startsWith(" ") && !part.endsWith(" "), "bad whitespace");
            require(part.length() <= SemanticClauseSplitter.HARD_MAX_CHARS,
                    "ordinary clause exceeded one-line ceiling: " + part);
        }
    }

    private static void reconstructionPreservesWords() {
        String s = "The first idea is complete, and the second idea explains why it matters, because both languages must show the same meaning when the video is paused.";
        List<String> parts = SemanticClauseSplitter.split(s);
        String rebuilt = String.join(" ", parts).replaceAll("\\s+", " ").trim();
        require(rebuilt.equals(s), "splitter changed source text: " + rebuilt);
    }

    private static void normalClausesStayWithinOneLineCeiling() {
        String s = "The speaker moves very quickly through this idea, but the translated voice needs enough room to finish without falling behind the next clause.";
        List<String> parts = SemanticClauseSplitter.split(s);
        require(parts.size() >= 3, "expected compact clause split");
        for (String part : parts) {
            require(part.length() <= 42, "clause is too wide for normal one-line target: " + part);
        }
    }

    private static void targetRangeIsProfessionalOneLineRange() {
        require(SemanticClauseSplitter.TARGET_CHARS >= 25
                        && SemanticClauseSplitter.TARGET_CHARS <= 38,
                "target should stay in the compact bilingual one-line range");
        require(SemanticClauseSplitter.SOFT_MAX_CHARS <= 38,
                "soft max should not exceed the preferred bilingual range");
        require(SemanticClauseSplitter.HARD_MAX_CHARS == 42,
                "normal Latin-script one-line ceiling should be 42 chars");
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
