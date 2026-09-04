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
    private static final int MAX_METADATA_CHARS = 700;
    // Kept deliberately small because two OpenRouter microrequests may run in parallel. Nearby raw
    // caption evidence gets first claim on this budget; generic metadata only uses what remains.
    private static final int MAX_CONTEXT_CHARS = 1_600;
    private static final int MAX_NEARBY_CUES = 12;
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
    private static List<String> cachedDistinctiveTerms;

    private VideoTranslationContext() {}

    /** Changes video only when needed; safe for metadata setters and other same-video callers. */
    public static synchronized void beginVideo(String videoId) {
        String safe = clean(videoId);
        if (safe.equals(currentVideoId)) return;
        reset(safe);
    }

    /**
     * Starts a fresh caption parse even if the same video is being reloaded after a provider/setting
     * change. This prevents duplicate raw cues and term counts from accumulating across reloads.
     */
    public static synchronized void beginCaptionLoad(String videoId) {
        reset(clean(videoId));
    }

    private static void reset(String videoId) {
        currentVideoId = videoId;
        title = "";
        author = "";
        metadata = "";
        RAW.clear();
        cachedDistinctiveTerms = null;
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
        cachedDistinctiveTerms = null;
    }

    public static synchronized int rawCueCount() {
        return RAW.size();
    }

    public static synchronized boolean hasMetadata() {
        return !title.isEmpty() || !author.isEmpty() || !metadata.isEmpty();
    }

    /**
     * Builds a compact prompt context for one realtime batch. Nearby raw cues are intentionally
     * prioritized over description/keyword metadata because they retain names, fragments, markers,
     * and local wording that a later parser may accidentally erase. Repeated distinctive terms add
     * inexpensive whole-video vocabulary without sending the full transcript.
     */
    public static synchronized String contextFor(String videoId, long startMs, long endMs) {
        if (!clean(videoId).equals(currentVideoId)) return "";
        StringBuilder out = new StringBuilder();
        appendLine(out, "Title: ", title);
        appendLine(out, "Channel: ", author);

        long lo = Math.max(0L, startMs - NEARBY_WINDOW_MS);
        long hi = endMs + NEARBY_WINDOW_MS;
        int nearbyHeaderPos = out.length();
        int cues = 0;
        for (Cue cue : RAW) {
            if (cue.endMs < lo || cue.startMs > hi) continue;
            if (cues == 0) appendWithinBudget(out,
                    "Nearby raw YouTube captions (pre-parser; may contain ASR errors):\n");
            String line = "[" + cue.startMs + "-" + cue.endMs + "] " + cue.text + "\n";
            if (!appendWithinBudget(out, line)) break;
            cues++;
            if (cues >= MAX_NEARBY_CUES) break;
        }
        // Do not leave an empty section header if the first cue could not fit.
        if (cues == 0 && out.length() > nearbyHeaderPos) out.setLength(nearbyHeaderPos);

        List<String> terms = distinctiveTerms(20);
        if (!terms.isEmpty() && out.length() < MAX_CONTEXT_CHARS) {
            StringBuilder line = new StringBuilder("Repeated raw-caption terms: ");
            for (int i = 0; i < terms.size(); i++) {
                if (i > 0) line.append(", ");
                line.append(terms.get(i));
            }
            line.append('\n');
            appendWithinBudget(out, line.toString());
        }

        // Metadata is useful for subject matter and names, but it is lowest priority because raw
        // captions are closer evidence for the current spoken phrase.
        if (!metadata.isEmpty() && out.length() < MAX_CONTEXT_CHARS) {
            appendWithinBudget(out, "Video metadata: " + metadata + "\n");
        }

        // If timing metadata was unusual and no nearby cue matched, include a few raw examples only
        // if room remains after title/channel/terms/metadata.
        if (cues == 0 && !RAW.isEmpty() && out.length() < MAX_CONTEXT_CHARS) {
            appendWithinBudget(out, "Raw caption examples:\n");
            for (int i = 0; i < Math.min(3, RAW.size()); i++) {
                Cue cue = RAW.get(i);
                if (!appendWithinBudget(out,
                        "[" + cue.startMs + "-" + cue.endMs + "] " + cue.text + "\n")) break;
            }
        }
        return out.toString().trim();
    }

    private static List<String> distinctiveTerms(int limit) {
        if (cachedDistinctiveTerms == null) {
            Map<String, Integer> counts = new HashMap<>();
            Map<String, String> spelling = new HashMap<>();
            for (Cue cue : RAW) {
                Matcher matcher = TOKEN.matcher(cue.text);
                while (matcher.find()) {
                    String raw = matcher.group();
                    String key = raw.toLowerCase(Locale.ROOT).replace('’', '\'');
                    if (key.length() < 4 || STOP.contains(key)
                            || key.chars().allMatch(Character::isDigit)) continue;
                    counts.merge(key, 1, Integer::sum);
                    spelling.putIfAbsent(key, raw);
                }
            }
            List<Map.Entry<String, Integer>> ranked = new ArrayList<>(counts.entrySet());
            ranked.removeIf(e -> e.getValue() < 2);
            ranked.sort(Comparator.<Map.Entry<String, Integer>>comparingInt(Map.Entry::getValue)
                    .reversed().thenComparing(Map.Entry::getKey));
            List<String> all = new ArrayList<>();
            for (Map.Entry<String, Integer> entry : ranked) all.add(spelling.get(entry.getKey()));
            cachedDistinctiveTerms = all;
        }
        int end = Math.min(Math.max(0, limit), cachedDistinctiveTerms.size());
        return new ArrayList<>(cachedDistinctiveTerms.subList(0, end));
    }

    private static void appendLine(StringBuilder out, String label, String value) {
        if (value == null || value.isEmpty()) return;
        appendWithinBudget(out, label + value + "\n");
    }

    private static boolean appendWithinBudget(StringBuilder out, String value) {
        if (value == null || value.isEmpty() || out.length() >= MAX_CONTEXT_CHARS) return false;
        int remaining = MAX_CONTEXT_CHARS - out.length();
        if (value.length() <= remaining) {
            out.append(value);
            return true;
        }
        // Avoid half-appending caption lines/section headers. Metadata may be clipped before this
        // method, so callers simply stop when a complete unit does not fit.
        return false;
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
