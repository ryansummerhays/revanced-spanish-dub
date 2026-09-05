package app.spanishstudy.vot;

public final class SubtitleLinePolicyV225Test {
    public static void main(String[] args) {
        losslessTwoLines();
        naturalBreak();
        noTinyTopLine();
        pathologicalWordIsPreserved();
        System.out.println("SubtitleLinePolicyV225Test passed");
    }

    private static void losslessTwoLines() {
        // v2.24 normally hands the formatter a card around 88 characters, not an entire paragraph.
        String input = "Larger subtitle cards should split into two clean readable lines without losing any words.";
        String formatted = SubtitleLinePolicy.format(input);
        eq(SubtitlePagePolicy.cleanDisplayText(input), SubtitleLinePolicy.removeFormatting(formatted));
        if (SubtitleLinePolicy.lineCount(formatted) != 2) fail("expected two lines: " + formatted);
        if (SubtitleLinePolicy.maxLineLength(formatted) > SubtitleLinePolicy.SOFT_MAX_CHARS_PER_LINE + 6)
            fail("ordinary card too wide: " + formatted);
    }

    private static void naturalBreak() {
        // The punctuation boundary is near the middle, so choosing it does not violate line width.
        String input = "The first idea is complete and easy to read, but the second idea should also remain clear.";
        String formatted = SubtitleLinePolicy.format(input);
        int breakAt = formatted.indexOf('\n');
        if (breakAt < 0) fail("expected line break");
        String top = formatted.substring(0, breakAt);
        if (!(top.endsWith(",") || formatted.substring(breakAt + 1).startsWith("but ")))
            fail("expected punctuation/conjunction-aware break: " + formatted);
    }

    private static void noTinyTopLine() {
        String input = "Well this sentence contains enough material that a two word first line would look awkward and should be avoided.";
        String formatted = SubtitleLinePolicy.format(input);
        if (formatted.indexOf('\n') >= 0 && formatted.substring(0, formatted.indexOf('\n')).split(" ").length <= 2)
            fail("tiny top line: " + formatted);
    }

    private static void pathologicalWordIsPreserved() {
        String input = "Pneumonoultramicroscopicsilicovolcanoconiosis is intentionally unbreakable but absolutely must never be truncated from subtitles.";
        String formatted = SubtitleLinePolicy.format(input);
        eq(SubtitlePagePolicy.cleanDisplayText(input), SubtitleLinePolicy.removeFormatting(formatted));
        if (SubtitleLinePolicy.lineCount(formatted) > 2) fail("more than two lines");
    }

    private static void eq(String a, String b) { if (!a.equals(b)) fail("expected <" + a + "> got <" + b + ">"); }
    private static void fail(String s) { throw new AssertionError(s); }
}
