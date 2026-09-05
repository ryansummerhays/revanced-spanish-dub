package app.spanishstudy.vot;

import java.util.List;

public final class SubtitleCardSizeV224Test {
    public static void main(String[] args) {
        if (SubtitlePagePolicy.TARGET_WORDS != 13) throw new AssertionError("TARGET_WORDS");
        if (SubtitlePagePolicy.TARGET_CHARS != 88) throw new AssertionError("TARGET_CHARS");
        String text = "This subtitle card should be noticeably roomier than the previous ten word version while still remaining compact enough to read comfortably during normal video playback without returning to the old giant paragraph style.";
        List<SubtitlePagePolicy.Page> pages = SubtitlePagePolicy.paginate(text);
        if (pages.size() < 2 || pages.size() > 4) throw new AssertionError("unexpected page count " + pages.size());
        StringBuilder joined = new StringBuilder();
        for (SubtitlePagePolicy.Page p : pages) { if (joined.length() > 0) joined.append(' '); joined.append(p.text); }
        if (!SubtitlePagePolicy.cleanDisplayText(text).equals(joined.toString())) throw new AssertionError("pagination not lossless");
        System.out.println("SubtitleCardSizeV224Test passed");
    }
}
