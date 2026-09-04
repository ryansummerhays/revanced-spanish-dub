package app.spanishstudy.vot;

import java.util.ArrayDeque;
import java.util.Deque;

/**
 * Separate bounded trace for judging translation quality without evicting runtime diagnostics.
 * Stores source and translated text side-by-side. Never stores credentials.
 */
public final class TranslationQualityLog {
    private static final int MAX_PAIRS = 120;
    private static final int MAX_TEXT_CHARS = 260;
    private static final Deque<String> PAIRS = new ArrayDeque<>(MAX_PAIRS);
    private static String currentVideoId = "";

    private TranslationQualityLog() {}

    public static synchronized void beginVideo(String videoId) {
        String safe = videoId == null ? "" : videoId.trim();
        if (!safe.equals(currentVideoId)) {
            currentVideoId = safe;
            PAIRS.clear();
        }
    }

    public static synchronized void record(String provider,
                                           String model,
                                           int segmentIndex,
                                           long startMs,
                                           long endMs,
                                           String source,
                                           String translated) {
        String line = "idx=" + segmentIndex
                + " t=" + startMs + "-" + endMs + "ms"
                + " provider=" + cleanMeta(provider)
                + " model=" + cleanMeta(model)
                + " | EN: " + cleanText(source)
                + " || ES: " + cleanText(translated);
        if (!PAIRS.isEmpty() && line.equals(PAIRS.peekLast())) return;
        if (PAIRS.size() >= MAX_PAIRS) PAIRS.removeFirst();
        PAIRS.addLast(line);
    }

    public static synchronized int size() {
        return PAIRS.size();
    }

    public static synchronized String dump() {
        StringBuilder out = new StringBuilder();
        for (String line : PAIRS) out.append(line).append('\n');
        return out.toString();
    }

    public static synchronized void clear() {
        PAIRS.clear();
        currentVideoId = "";
    }

    private static String cleanMeta(String value) {
        if (value == null || value.isBlank()) return "-";
        String clean = value.replace('\n', ' ').replace('\r', ' ').trim();
        return clean.length() <= 100 ? clean : clean.substring(0, 100);
    }

    private static String cleanText(String value) {
        if (value == null) return "<missing>";
        String clean = value.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
        if (clean.isEmpty()) return "<empty>";
        return clean.length() <= MAX_TEXT_CHARS ? clean : clean.substring(0, MAX_TEXT_CHARS) + "…";
    }
}
