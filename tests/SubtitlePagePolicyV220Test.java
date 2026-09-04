package app.spanishstudy.vot;

import java.util.List;

public final class SubtitlePagePolicyV220Test {
    public static void main(String[] args) {
        cleanSpacing();
        losslessPagination();
        naturalBreaks();
        weightedProgress();
        partialTtsProgress();
        System.out.println("SubtitlePagePolicyV220Test passed");
    }

    private static void cleanSpacing() {
        eq("Hello, world! I'm here.",
                SubtitlePagePolicy.cleanDisplayText(" Hello ,world!I ' m here. "));
        eq("¿Cómo estás? Muy bien.",
                SubtitlePagePolicy.cleanDisplayText("¿ Cómo estás ?Muy bien."));
    }

    private static void losslessPagination() {
        String input = "This is a fairly long subtitle sentence that should be divided into smaller readable pages without ever losing any of the original words in the process, because truncation is not acceptable.";
        List<SubtitlePagePolicy.Page> pages = SubtitlePagePolicy.paginate(input);
        if (pages.size() < 2) fail("expected multiple pages");
        StringBuilder joined = new StringBuilder();
        for (SubtitlePagePolicy.Page p : pages) {
            if (joined.length() > 0) joined.append(' ');
            joined.append(p.text);
        }
        eq(SubtitlePagePolicy.cleanDisplayText(input), joined.toString());
        for (SubtitlePagePolicy.Page p : pages) {
            if (p.text.split(" ").length > SubtitlePagePolicy.TARGET_WORDS + 2)
                fail("page too word-heavy: " + p.text);
        }
    }

    private static void naturalBreaks() {
        String input = "First thought ends here. Then the next thought continues with enough words to make another readable subtitle card.";
        List<SubtitlePagePolicy.Page> pages = SubtitlePagePolicy.paginate(input);
        if (pages.size() < 2) fail("expected sentence boundary split");
        if (!pages.get(0).text.endsWith(".")) fail("expected punctuation-aware first page");
    }

    private static void weightedProgress() {
        List<SubtitlePagePolicy.Page> pages = SubtitlePagePolicy.paginate(
                "Short page ends. This second page contains considerably more spoken material and should therefore remain visible for longer overall.");
        if (pages.size() < 2) fail("expected multiple weighted pages");
        int early = SubtitlePagePolicy.pageIndex(pages, 0.05);
        int late = SubtitlePagePolicy.pageIndex(pages, 0.95);
        if (early != 0 || late != pages.size() - 1) fail("bad weighted mapping");
    }

    private static void partialTtsProgress() {
        double start = SubtitlePagePolicy.startProgress(20_000L, 10_000L);
        near(0.5, start, 0.0001);
        near(0.75, SubtitlePagePolicy.ttsProgress(5_000L, 0L, 10_000L, start), 0.0001);
    }

    private static void eq(String expected, String actual) {
        if (!expected.equals(actual)) fail("expected <" + expected + "> got <" + actual + ">");
    }

    private static void near(double expected, double actual, double eps) {
        if (Math.abs(expected - actual) > eps) fail("expected " + expected + " got " + actual);
    }

    private static void fail(String msg) {
        throw new AssertionError(msg);
    }
}
