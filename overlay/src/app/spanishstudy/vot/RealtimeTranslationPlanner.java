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

    /**
     * Output cap for one OpenRouter subrequest. v2.15 used only 30 tokens/segment, which
     * repeatedly ended with finish_reason=length and created artificial missing translations.
     * This cap is intentionally generous: providers charge actual generated tokens, not the cap.
     */
    public static int openRouterMaxOutputTokens(int promptCaptionChars, int segmentCount) {
        int chars = Math.max(0, promptCaptionChars);
        int segments = Math.max(1, segmentCount);
        int byText = chars / 2 + 96;
        int bySegments = segments * 72;
        return Math.max(192, Math.min(640, Math.max(byText, bySegments)));
    }
}
