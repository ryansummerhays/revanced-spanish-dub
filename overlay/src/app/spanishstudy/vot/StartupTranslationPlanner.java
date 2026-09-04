package app.spanishstudy.vot;

import java.util.List;

/** Keeps the first playhead translation request deliberately small so dubbing can become audible. */
public final class StartupTranslationPlanner {
    public static final int MAX_INITIAL_SEGMENTS = 8;
    public static final int MAX_INITIAL_CHARS = 600;

    private StartupTranslationPlanner() {}

    /**
     * Returns how many leading segment texts should be kept in the first request after start/seek.
     * The first segment is always retained even when it alone exceeds the character budget.
     */
    public static int initialSegmentCount(List<String> texts) {
        if (texts == null || texts.isEmpty()) return 0;
        int chars = 0;
        int count = 0;
        for (String text : texts) {
            if (count >= MAX_INITIAL_SEGMENTS) break;
            int added = (text == null ? 0 : text.length()) + 1;
            if (count > 0 && chars + added > MAX_INITIAL_CHARS) break;
            chars += added;
            count++;
        }
        return Math.max(1, count);
    }
}
