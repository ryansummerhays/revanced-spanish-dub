package app.spanishstudy.vot;

import java.util.List;

/**
 * Hard realtime budget for cloud translation requests feeding audible playback.
 * A small fixed upper bound prevents the growing 8 -> 17 -> 27 segment batches seen in v2.14.1.
 */
public final class RealtimeTranslationPlanner {
    public static final int MAX_BATCH_SEGMENTS = 6;
    public static final int MAX_BATCH_CHARS = 650;
    public static final int OPENROUTER_PARALLEL_REQUESTS = 2;

    private RealtimeTranslationPlanner() {}

    /** Returns the largest non-empty prefix that fits both the segment and character budgets. */
    public static int boundedSegmentCount(List<String> texts) {
        if (texts == null || texts.isEmpty()) return 0;
        int chars = 0;
        int count = 0;
        for (String text : texts) {
            if (count >= MAX_BATCH_SEGMENTS) break;
            int added = (text == null ? 0 : text.length()) + 1;
            if (count > 0 && chars + added > MAX_BATCH_CHARS) break;
            chars += added;
            count++;
        }
        return Math.max(1, count);
    }
}
