package app.spanishstudy.vot;

/** Pure timing math for bilingual subtitle chunks. No Android dependencies. */
final class SynchronizedSubtitleChunks {
    static final class Window {
        final int chunkIndex;
        final int chunkCount;
        final int englishStart;
        final int englishEnd;
        final int spanishStart;
        final int spanishEnd;

        Window(int chunkIndex, int chunkCount,
               int englishStart, int englishEnd,
               int spanishStart, int spanishEnd) {
            this.chunkIndex = chunkIndex;
            this.chunkCount = chunkCount;
            this.englishStart = englishStart;
            this.englishEnd = englishEnd;
            this.spanishStart = spanishStart;
            this.spanishEnd = spanishEnd;
        }
    }

    private SynchronizedSubtitleChunks() {}

    /**
     * Creates one shared chunk clock for both languages.
     *
     * Chunk boundaries are derived only from the source video slot. Both languages therefore
     * switch boxes on the exact same player tick. Word ranges are distributed proportionally
     * across the same number of chunks, so different sentence lengths never cause one language
     * to advance ahead of the other.
     */
    static Window window(int englishWords,
                         int spanishWords,
                         int preferredWords,
                         long startMs,
                         long endMs,
                         long timeMs) {
        englishWords = Math.max(0, englishWords);
        spanishWords = Math.max(0, spanishWords);
        preferredWords = Math.max(1, preferredWords);

        int longest = Math.max(englishWords, spanishWords);
        int shortestNonZero;
        if (englishWords == 0) shortestNonZero = spanishWords;
        else if (spanishWords == 0) shortestNonZero = englishWords;
        else shortestNonZero = Math.min(englishWords, spanishWords);

        int desiredChunks = Math.max(1, ceilDiv(longest, preferredWords));
        // When both languages are visible, never create more chunks than the shorter sentence has
        // words. That guarantees every synchronized change contains new text in both boxes.
        int chunkCount = shortestNonZero > 0 ? Math.min(desiredChunks, shortestNonZero) : 1;
        chunkCount = Math.max(1, chunkCount);

        long span = Math.max(1L, endMs - startMs);
        double progress = (timeMs - startMs) / (double) span;
        progress = Math.max(0.0, Math.min(0.999999, progress));
        int chunkIndex = Math.min(chunkCount - 1, (int) Math.floor(progress * chunkCount));

        int englishStart = boundary(chunkIndex, englishWords, chunkCount);
        int englishEnd = boundary(chunkIndex + 1, englishWords, chunkCount);
        int spanishStart = boundary(chunkIndex, spanishWords, chunkCount);
        int spanishEnd = boundary(chunkIndex + 1, spanishWords, chunkCount);

        return new Window(chunkIndex, chunkCount,
                englishStart, englishEnd, spanishStart, spanishEnd);
    }

    private static int boundary(int chunk, int words, int chunkCount) {
        if (words <= 0) return 0;
        return (int) (((long) chunk * words) / chunkCount);
    }

    private static int ceilDiv(int n, int d) {
        return n <= 0 ? 1 : (n + d - 1) / d;
    }
}
