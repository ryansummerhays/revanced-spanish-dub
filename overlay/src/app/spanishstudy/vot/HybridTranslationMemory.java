package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Small in-memory translation memory for the current app process.
 *
 * <p>This deliberately does not write dubbed videos or transcripts to disk. It only keeps a bounded
 * set of exact source-slot translations so a seek/reload/revisit does not need to spend another
 * Gemini request for text we already translated successfully. Google fallback entries are retained
 * too, but a later healthy Gemini request is still allowed to upgrade them.
 */
final class HybridTranslationMemory {
    private enum Quality { GOOGLE, GEMINI }

    private static final int MAX_ENTRIES = 4_000;

    private static final class Entry {
        final String text;
        final Quality quality;
        final String model;

        Entry(String text, Quality quality, String model) {
            this.text = text;
            this.quality = quality;
            this.model = model == null ? "" : model;
        }
    }

    private static final LinkedHashMap<String, Entry> CACHE =
            new LinkedHashMap<String, Entry>(512, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, Entry> eldest) {
                    return size() > MAX_ENTRIES;
                }
            };

    private HybridTranslationMemory() {}

    static synchronized List<String> getGeminiBatch(String videoId,
                                                     List<TranscriptSegment> segments,
                                                     String targetLang,
                                                     String model) {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();
        ArrayList<String> out = new ArrayList<>(segments.size());
        for (TranscriptSegment segment : segments) {
            Entry entry = CACHE.get(key(videoId, segment, targetLang));
            if (entry == null || entry.quality != Quality.GEMINI
                    || !entry.model.equals(model == null ? "" : model)) return null;
            out.add(entry.text);
        }
        return out;
    }

    static synchronized List<String> getAnyBatch(String videoId,
                                                  List<TranscriptSegment> segments,
                                                  String targetLang) {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();
        ArrayList<String> out = new ArrayList<>(segments.size());
        for (TranscriptSegment segment : segments) {
            Entry entry = CACHE.get(key(videoId, segment, targetLang));
            if (entry == null) return null;
            out.add(entry.text);
        }
        return out;
    }

    static synchronized void putGeminiBatch(String videoId,
                                             List<TranscriptSegment> segments,
                                             String targetLang,
                                             String model,
                                             List<String> translations) {
        putBatch(videoId, segments, targetLang, translations, Quality.GEMINI, model);
    }

    static synchronized void putGoogleBatch(String videoId,
                                             List<TranscriptSegment> segments,
                                             String targetLang,
                                             List<String> translations) {
        putBatch(videoId, segments, targetLang, translations, Quality.GOOGLE, "");
    }

    private static void putBatch(String videoId,
                                 List<TranscriptSegment> segments,
                                 String targetLang,
                                 List<String> translations,
                                 Quality quality,
                                 String model) {
        if (segments == null || translations == null || segments.size() != translations.size()) return;
        for (int i = 0; i < segments.size(); i++) {
            String translated = translations.get(i);
            if (translated == null || translated.isBlank()) continue;
            CACHE.put(key(videoId, segments.get(i), targetLang), new Entry(translated, quality, model));
        }
    }

    static synchronized String summary() {
        int gemini = 0;
        int google = 0;
        for (Entry entry : CACHE.values()) {
            if (entry.quality == Quality.GEMINI) gemini++;
            else google++;
        }
        return CACHE.size() + "/" + MAX_ENTRIES + " entries (Gemini " + gemini + ", Google " + google + ")";
    }

    private static String key(String videoId, TranscriptSegment segment, String targetLang) {
        if (segment == null) return "";
        String source = segment.text == null ? "" : segment.text;
        return (videoId == null ? "" : videoId) + '\n'
                + (targetLang == null ? "" : targetLang) + '\n'
                + segment.startMs + ':' + segment.endMs + '\n' + source;
    }
}
