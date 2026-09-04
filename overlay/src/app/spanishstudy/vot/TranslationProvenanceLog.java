package app.spanishstudy.vot;

import java.util.LinkedHashMap;
import java.util.Map;

/** Bounded per-segment provenance so diagnostics can prove what translation each TTS clip consumed. */
public final class TranslationProvenanceLog {
    private static final int MAX_ENTRIES = 500;
    private static final Map<Integer, ProvenanceEntry> ENTRIES =
            new LinkedHashMap<Integer, ProvenanceEntry>(128, 0.75f, true) {
                @Override protected boolean removeEldestEntry(
                        Map.Entry<Integer, ProvenanceEntry> eldest) {
                    return size() > MAX_ENTRIES;
                }
            };
    private static String currentVideoId = "";

    private TranslationProvenanceLog() {}

    public static synchronized void beginVideo(String videoId) {
        String safe = videoId == null ? "" : videoId.trim();
        if (!safe.equals(currentVideoId)) {
            currentVideoId = safe;
            ENTRIES.clear();
        }
    }

    /** First-ready wins so later full-batch publication cannot hide an earlier streamed origin. */
    public static synchronized boolean markReady(String videoId, int index, String provider,
                                                 String model, String path, String text) {
        beginVideo(videoId);
        if (index < 0 || ENTRIES.containsKey(index)) return false;
        ENTRIES.put(index, new ProvenanceEntry(clean(provider), clean(model), clean(path),
                System.currentTimeMillis(), hash(text)));
        return true;
    }

    public static synchronized String describe(int index, String text) {
        ProvenanceEntry e = ENTRIES.get(index);
        if (e == null) return "provider=unknown path=unknown ageMs=-1 hash=" + hash(text);
        long age = Math.max(0L, System.currentTimeMillis() - e.readyAtMs);
        return "provider=" + e.provider + " model=" + e.model + " path=" + e.path
                + " ageMs=" + age + " hash=" + e.textHash;
    }

    public static synchronized int size() {
        return ENTRIES.size();
    }

    public static synchronized void clear() {
        currentVideoId = "";
        ENTRIES.clear();
    }

    private static String clean(String value) {
        if (value == null || value.isBlank()) return "-";
        String v = value.replace('\n', ' ').replace('\r', ' ').trim();
        return v.length() <= 80 ? v : v.substring(0, 80);
    }

    private static String hash(String text) {
        return Integer.toHexString(text == null ? 0 : text.hashCode());
    }

    private record ProvenanceEntry(String provider, String model, String path,
                                   long readyAtMs, String textHash) {}
}
