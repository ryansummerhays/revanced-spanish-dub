package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Lightweight, video-specific translation context built entirely from data already fetched for the
 * current YouTube video: title/channel/description/keywords plus the raw pre-parser caption cues.
 * No extra network request or second AI analysis pass is required.
 */
public final class VideoTranslationContext {
    private static final int MAX_RAW_CUES = 2_000;
    private static final int MAX_METADATA_CHARS = 1_200;
    private static final int MAX_CONTEXT_CHARS = 2_200;
    private static final long NEARBY_WINDOW_MS = 18_000L;
    private static final Pattern TOKEN = Pattern.compile("[\\p{L}\\p{N}][\\p{L}\\p{N}'’_-]{2,}");
    private static final Set<String> STOP = new HashSet<>(List.of(
            "this","that","with","from","have","will","would","could","should","there","their",
            "what","when","where","which","while","about","into","your","youre","theyre","were",
            "then","than","them","they","just","like","really","very","some","more","most","much",
            "also","only","even","because","been","being","here","okay","yeah","yes","nope","dont",
            "doesnt","didnt","cant","wont","im","ive","ill","its","the","and","for","are","but",
            "not","you","all","can","our","out","get","got","now","how","who","why","him","her",
            "his","she","was","had","has","did","too","off","one","two","three","four","five"
    ));

    private static String currentVideoId = "";
    private static String title = "";
    private static String author = "";
    private static String metadata = "";
    private static final List<Cue> RAW = new ArrayList<>();

    private VideoTranslationContext() {}

    public static synchronized void beginVideo(String videoId) {
        String safe = clean(videoId);
        if (safe.equals(currentVideoId)) return;
        currentVideoId = safe;
        title = "";
        author = "";
        metadata = "";
        RAW.clear();
    }

    public static synchronized void prepareMetadata(String videoId, String videoTitle,
                                                    String channel, String details) {
        beginVideo(videoId);
        title = clip(clean(videoTitle), 280);
        author = clip(clean(channel), 180);
        metadata = clip(clean(details), MAX_METADATA_CHARS);
    }

    /** Stores the original event text before punctuation cleanup, marker stripping, or phrase merging. */
    public static synchronized void addRawCue(long startMs, long endMs, String rawText) {
        String text = clean(rawText);
        if (text.isEmpty()) return;
        if (RAW.size() >= MAX_RAW_CUES) RAW.remove(0);
        RAW.add(new Cue(Math.max(0L, startMs), Math.max(startMs, endMs), clip(text, 320)));
    }

    public static synchronized int rawCueCount() {
        return RAW.size();
    }

    public static synchronized boolean hasMetadata() {
        return !title.isEmpty() || !author.isEmpty() || !metadata.isEmpty();
    }

    /**
     * Builds a compact prompt context for one realtime batch. Nearby raw cues are more valuable than
     * the already-merged translation units because they retain names, fragments, markers and local
     * wording that parsers can accidentally erase. Repeated distinctive tokens provide whole-video
     * vocabulary without sending the full transcript.
     */
    public static synchronized String contextFor(String videoId, long startMs, long endMs) {
        if (!clean(videoId).equals(currentVideoId)) return "";
        StringBuilder out = new StringBuilder();
        if (!title.isEmpty()) out.append("Title: ").append(title).append('\n');
        if (!author.isEmpty()) out.append("Channel: ").append(author).append('\n');
        if (!metadata.isEmpty()) out.append("Video metadata: ").append(metadata).append('\n');

        List<String> terms = distinctiveTerms(24);
        if (!terms.isEmpty()) {
            out.append("Repeated raw-caption terms: ");
            for (int i = 0; i < terms.size(); i++) {
                if (i > 0) out.append(", ");
                out.append(terms.get(i));
            }
            out.append('\n');
        }

        long lo = Math.max(0L, startMs - NEARBY_WINDOW_MS);
        long hi = endMs + NEARBY_WINDOW_MS;
        int beforeNearby = out.length();
        int cues = 0;
        for (Cue cue : RAW) {
            if (cue.endMs < lo || cue.startMs > hi) continue;
            if (cues == 0) out.append("Nearby raw YouTube captions (pre-parser, may contain ASR errors):\n");
            String line = "[" + cue.startMs + "-" + cue.endMs + "] " + cue.text + "\n";
            if (out.length() + line.length() > MAX_CONTEXT_CHARS) break;
            out.append(line);
            cues++;
            if (cues >= 14) break;
        }
        if (cues == 0 && out.length() == beforeNearby && !RAW.isEmpty()) {
            out.append("Raw caption examples:\n");
            for (int i = 0; i < Math.min(3, RAW.size()); i++) {
                Cue cue = RAW.get(i);
                String line = "[" + cue.startMs + "-" + cue.endMs + "] " + cue.text + "\n";
                if (out.length() + line.length() > MAX_CONTEXT_CHARS) break;
                out.append(line);
            }
        }
        return clip(out.toString().trim(), MAX_CONTEXT_CHARS);
    }

    private static List<String> distinctiveTerms(int limit) {
        Map<String, Integer> counts = new HashMap<>();
        Map<String, String> spelling = new HashMap<>();
        for (Cue cue : RAW) {
            Matcher matcher = TOKEN.matcher(cue.text);
            while (matcher.find()) {
                String raw = matcher.group();
                String key = raw.toLowerCase(Locale.ROOT).replace('’', '\'');
                if (key.length() < 4 || STOP.contains(key) || key.chars().allMatch(Character::isDigit)) continue;
                counts.merge(key, 1, Integer::sum);
                spelling.putIfAbsent(key, raw);
            }
        }
        List<Map.Entry<String, Integer>> ranked = new ArrayList<>(counts.entrySet());
        ranked.removeIf(e -> e.getValue() < 2);
        ranked.sort(Comparator.<Map.Entry<String, Integer>>comparingInt(Map.Entry::getValue)
                .reversed().thenComparing(Map.Entry::getKey));
        List<String> out = new ArrayList<>();
        for (Map.Entry<String, Integer> entry : ranked) {
            out.add(spelling.get(entry.getKey()));
            if (out.size() >= limit) break;
        }
        return out;
    }

    private static String clean(String text) {
        if (text == null) return "";
        return text.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
    }

    private static String clip(String text, int max) {
        return text.length() <= max ? text : text.substring(0, max);
    }

    private record Cue(long startMs, long endMs, String text) {}
}
