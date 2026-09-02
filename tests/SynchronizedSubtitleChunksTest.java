package app.spanishstudy.vot;

public final class SynchronizedSubtitleChunksTest {
    public static void main(String[] args) {
        // Different word counts must still use one shared chunk index and change time.
        SynchronizedSubtitleChunks.Window a = SynchronizedSubtitleChunks.window(
                12, 8, 4, 1_000, 5_000, 1_100);
        SynchronizedSubtitleChunks.Window b = SynchronizedSubtitleChunks.window(
                12, 8, 4, 1_000, 5_000, 3_100);
        if (a.chunkCount != 3 || b.chunkCount != 3)
            throw new AssertionError("expected three shared chunks");
        if (a.chunkIndex != 0 || b.chunkIndex != 1)
            throw new AssertionError("shared chunk clock is wrong");
        if (a.englishEnd <= a.englishStart || a.spanishEnd <= a.spanishStart)
            throw new AssertionError("first chunk must contain words in both languages");
        if (b.englishEnd <= b.englishStart || b.spanishEnd <= b.spanishStart)
            throw new AssertionError("second chunk must contain words in both languages");

        // A much shorter translation still must never get an empty synchronized box.
        for (long t : new long[]{0, 2_500, 5_000, 7_500, 9_999}) {
            SynchronizedSubtitleChunks.Window w = SynchronizedSubtitleChunks.window(
                    20, 3, 4, 0, 10_000, t);
            if (w.chunkCount != 3)
                throw new AssertionError("chunk count should be limited by shorter sentence");
            if (w.englishEnd <= w.englishStart || w.spanishEnd <= w.spanishStart)
                throw new AssertionError("synchronized chunk must be nonempty");
        }

        // Seeking backward should deterministically select the earlier shared chunk again.
        SynchronizedSubtitleChunks.Window late = SynchronizedSubtitleChunks.window(
                9, 10, 4, 10_000, 14_000, 13_800);
        SynchronizedSubtitleChunks.Window early = SynchronizedSubtitleChunks.window(
                9, 10, 4, 10_000, 14_000, 10_200);
        if (late.chunkIndex <= early.chunkIndex)
            throw new AssertionError("seek/chunk indexing is not deterministic");

        System.out.println("synchronized subtitle chunk contract: OK");
    }
}
