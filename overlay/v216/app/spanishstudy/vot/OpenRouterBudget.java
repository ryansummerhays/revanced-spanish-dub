package app.spanishstudy.vot;

/** Output-token allowance only; it does not affect Morphe's native batching or request order. */
public final class OpenRouterBudget {
    private OpenRouterBudget() {}

    /**
     * Morphe's native 1500-character batches generally need far less than this, but 30 tokens per
     * segment was small enough to truncate valid Spanish. Keep a generous bounded allowance.
     */
    public static int maxOutputTokens(int inputChars, int segmentCount) {
        int chars = Math.max(0, inputChars);
        int segments = Math.max(1, segmentCount);
        int estimate = 96 + (chars / 3) + (segments * 8);
        return Math.max(192, Math.min(640, estimate));
    }
}
