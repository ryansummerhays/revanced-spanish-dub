package app.spanishstudy.vot;

import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Stores conservative, context-backed corrections to the English caption text for display only.
 *
 * Timing and immutable source IDs never change. The raw source remains the alignment authority for
 * translation/TTS. This store only lets the bilingual English line show a high-confidence cleanup
 * of an ASR error such as a misspelled proper noun, game item, acronym, jargon term, or homophone.
 */
final class TranscriptCorrectionStore {
    private static final int MAX_ENTRIES = 600;
    private static final Map<String, String> CORRECTIONS =
            new LinkedHashMap<String, String>(128, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, String> eldest) {
                    return size() > MAX_ENTRIES;
                }
            };

    private TranscriptCorrectionStore() {}

    static synchronized void put(long startMs, long endMs, String raw, String corrected) {
        String accepted = conservativeCorrection(raw, corrected);
        if (accepted == null || same(raw, accepted)) return;
        CORRECTIONS.put(key(startMs, endMs), accepted);
    }

    static synchronized String get(long startMs, long endMs, String rawFallback) {
        String corrected = CORRECTIONS.get(key(startMs, endMs));
        return corrected == null || corrected.isBlank() ? rawFallback : corrected;
    }

    /** Roll back a proposed correction when its paired translation later fails grounding checks. */
    static synchronized void remove(long startMs, long endMs) {
        CORRECTIONS.remove(key(startMs, endMs));
    }

    static synchronized void clear() {
        CORRECTIONS.clear();
    }

    /**
     * Gemini is instructed to leave correctedSource unchanged unless it has strong contextual
     * evidence of an ASR/misparse error. This second gate makes the display fail conservative too.
     * Short jargon tokens can change completely (DVO -> Devo/Devotion), while longer sentences are
     * allowed only modest local edits rather than paraphrasing the whole English subtitle.
     */
    private static String conservativeCorrection(String raw, String candidate) {
        String source = normalize(raw);
        String corrected = normalize(candidate);
        if (source.isEmpty() || corrected.isEmpty()) return null;
        if (source.equals(corrected)) return source;

        int sourceWords = words(source);
        int correctedWords = words(corrected);
        double lengthRatio = corrected.length() / (double) Math.max(1, source.length());
        if (lengthRatio < 0.45 || lengthRatio > 2.20) return null;

        // Very short labels/jargon are exactly where ASR often produces opaque errors.
        if (sourceWords <= 4) {
            return correctedWords <= sourceWords + 2 ? corrected : null;
        }

        int maxWordDelta = Math.max(2, (int) Math.ceil(sourceWords * 0.25));
        if (Math.abs(correctedWords - sourceWords) > maxWordDelta) return null;

        // For longer captions, require a substantial amount of lexical material to remain. This
        // rejects stylistic rewrites while allowing punctuation, spelling and a few domain terms.
        String[] a = lexical(source);
        String[] b = lexical(corrected);
        int overlap = multisetOverlap(a, b);
        double retained = overlap / (double) Math.max(1, Math.min(a.length, b.length));
        return retained >= 0.58 ? corrected : null;
    }

    private static int multisetOverlap(String[] a, String[] b) {
        boolean[] used = new boolean[b.length];
        int count = 0;
        for (String x : a) {
            for (int i = 0; i < b.length; i++) {
                if (!used[i] && x.equals(b[i])) {
                    used[i] = true;
                    count++;
                    break;
                }
            }
        }
        return count;
    }

    private static boolean same(String a, String b) {
        return normalize(a).equals(normalize(b));
    }

    private static int words(String text) {
        return lexical(text).length;
    }

    private static String[] lexical(String text) {
        String clean = normalize(text).toLowerCase(Locale.ROOT)
                .replace('’', '\'')
                .replaceAll("[^\\p{L}\\p{N}']+", " ")
                .trim();
        return clean.isEmpty() ? new String[0] : clean.split("\\s+");
    }

    private static String normalize(String text) {
        return text == null ? "" : text.trim().replaceAll("\\s+", " ");
    }

    private static String key(long startMs, long endMs) {
        return startMs + ":" + endMs;
    }
}
