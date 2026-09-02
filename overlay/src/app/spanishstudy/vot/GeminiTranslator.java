package app.spanishstudy.vot;

import android.content.Context;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import app.morphe.extension.shared.Logger;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.shared.translation.TextTranslator;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Direct Gemini transcript translator for the Spanish-study overlay.
 *
 * v2.3.3 keeps Gemini source-grounded without repeatedly stuffing an entire long transcript into
 * every request. Metadata and a compact whole-video recurring-term index provide global subject
 * context, while each request receives a bounded local transcript window. Gemini still echoes the
 * immutable raw source ID/text, and an independent Google back-translation is used as a conservative
 * faithfulness check before Spanish is accepted for subtitle/TTS playback.
 */
public final class GeminiTranslator {
    private static final int CONNECT_TIMEOUT_MS = 7_000;
    private static final int READ_TIMEOUT_MS = 15_000;
    private static final String API_ROOT =
            "https://generativelanguage.googleapis.com/v1beta/models/";

    private static final int OUTPUT_SEGMENTS_PER_REQUEST = 40;
    private static final int MAX_PREPARED_TRANSCRIPTS = 3;
    private static final int MAX_VIDEO_METADATA = 4;
    private static final int MAX_DESCRIPTION_CHARS = 2_400;
    private static final int LOCAL_CONTEXT_RADIUS = 7;
    private static final int MAX_RECURRING_TERMS = 120;

    private static final Set<String> CONTEXT_STOP_WORDS = new HashSet<>(List.of(
            "the","and","that","this","with","from","have","has","had","were","was","are","is",
            "for","you","your","they","their","our","but","not","just","like","yeah","yes","no",
            "what","when","where","which","who","why","how","would","could","should","will","can",
            "get","got","getting","going","want","wanted","really","very","more","most","some","then",
            "than","there","here","into","about","because","also","only","thing","things","something",
            "its","it's","im","i'm","dont","don't","didnt","didn't","doesnt","doesn't","gonna","wanna"
    ));

    private static final Map<String, PreparedTranscript> PREPARED =
            new LinkedHashMap<String, PreparedTranscript>(4, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, PreparedTranscript> eldest) {
                    return size() > MAX_PREPARED_TRANSCRIPTS;
                }
            };

    private static final Map<String, VideoMetadata> VIDEO_METADATA =
            new LinkedHashMap<String, VideoMetadata>(5, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, VideoMetadata> eldest) {
                    return size() > MAX_VIDEO_METADATA;
                }
            };

    private GeminiTranslator() {}

    public static boolean isEnabled() {
        Context context = Utils.getContext();
        return context != null
                && SpanishStudyPrefs.geminiEnabled(context)
                && !SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty();
    }

    /**
     * Called from TranscriptFetcher using the same Innertube player response that supplied captions.
     * No extra YouTube request is needed. Description is deliberately capped.
     */
    public static synchronized void prepareVideoMetadata(String videoId,
                                                         String title,
                                                         String author,
                                                         String description) {
        if (videoId == null || videoId.isBlank()) return;
        VIDEO_METADATA.put(videoId, new VideoMetadata(
                cleanMetadata(title, 500),
                cleanMetadata(author, 250),
                cleanMetadata(description, MAX_DESCRIPTION_CHARS)));
    }

    /** Capture the immutable source list and a compact whole-video subject index before batching. */
    public static synchronized void prepareTranscript(String videoId,
                                                      List<TranscriptSegment> segments,
                                                      String targetLang) {
        if (videoId == null || segments == null || segments.isEmpty()) return;
        List<TranscriptSegment> snapshot = new ArrayList<>(segments);
        PREPARED.put(cacheKey(videoId, targetLang),
                new PreparedTranscript(snapshot, buildGlobalContext(videoId, snapshot)));
    }

    /** Full blocking helper retained for compatibility/non-playback uses. */
    public static List<TranscriptSegment> translateWholeTranscript(String videoId,
                                                                   List<TranscriptSegment> segments,
                                                                   String targetLang) throws Exception {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();
        prepareTranscript(videoId, segments, targetLang);
        PreparedTranscript prepared = prepared(videoId, targetLang);
        if (prepared == null) throw new IllegalStateException("Gemini transcript context unavailable");

        List<String> translated = new ArrayList<>(segments.size());
        for (int i = 0; i < segments.size(); i++) translated.add(null);

        for (int start = 0; start < segments.size(); start += OUTPUT_SEGMENTS_PER_REQUEST) {
            int end = Math.min(segments.size(), start + OUTPUT_SEGMENTS_PER_REQUEST);
            List<String> block;
            try {
                block = translateRange(prepared.globalContext, prepared.segments, start, end, targetLang);
            } catch (Exception ex) {
                Logger.printDebug(() -> "Gemini block failed; using Google fallback: "
                        + ex.getClass().getSimpleName() + ": " + ex.getMessage());
                block = translateFallback(prepared.segments.subList(start, end), targetLang);
            }
            if (block.size() != end - start) {
                throw new Exception("Translation range count mismatch: expected " + (end - start)
                        + ", got " + block.size());
            }
            for (int i = 0; i < block.size(); i++) translated.set(start + i, block.get(i));
        }

        List<TranscriptSegment> out = new ArrayList<>(segments.size());
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment src = segments.get(i);
            String text = translated.get(i);
            if (text == null || text.isBlank()) text = src.text;
            TranscriptSegment dst = new TranscriptSegment(src.startMs, src.endMs, text, targetLang);
            dst.playbackStartMs = src.startMs;
            dst.playbackEndMs = src.endMs;
            out.add(dst);
        }
        return out;
    }

    /**
     * Translate one progressive dispatcher batch. Long videos use a bounded prompt: global metadata
     * and recurring terms + a local transcript window around the requested immutable IDs.
     */
    public static List<String> translateBatch(String videoId,
                                              List<TranscriptSegment> segments,
                                              String targetLang) throws Exception {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();

        PreparedTranscript prepared = prepared(videoId, targetLang);
        if (prepared == null) {
            prepareTranscript(videoId, segments, targetLang);
            prepared = prepared(videoId, targetLang);
        }
        if (prepared == null) return translateFallback(segments, targetLang);

        int start = findBatchStart(prepared.segments, segments);
        try {
            if (start < 0) {
                String localGlobalContext = buildGlobalContext(videoId, segments);
                return translateRange(localGlobalContext, segments, 0, segments.size(), targetLang);
            }
            return translateRange(prepared.globalContext, prepared.segments,
                    start, start + segments.size(), targetLang);
        } catch (Exception ex) {
            Logger.printDebug(() -> "Gemini batch failed; using Google fallback: "
                    + ex.getClass().getSimpleName() + ": " + ex.getMessage());
            return translateFallback(segments, targetLang);
        }
    }

    private static List<String> translateFallback(List<TranscriptSegment> segments,
                                                  String targetLang) throws Exception {
        List<String> lines = new ArrayList<>(segments.size());
        for (TranscriptSegment segment : segments) lines.add(segment.text);
        return TextTranslator.translate(lines, targetLang);
    }

    private static synchronized PreparedTranscript prepared(String videoId, String targetLang) {
        return PREPARED.get(cacheKey(videoId, targetLang));
    }

    private static String cacheKey(String videoId, String targetLang) {
        return (videoId == null ? "" : videoId) + "\n" + (targetLang == null ? "" : targetLang);
    }

    private static int findBatchStart(List<TranscriptSegment> full,
                                      List<TranscriptSegment> batch) {
        if (batch.isEmpty() || full.size() < batch.size()) return -1;
        TranscriptSegment first = batch.get(0);
        int lastStart = full.size() - batch.size();
        for (int start = 0; start <= lastStart; start++) {
            TranscriptSegment candidate = full.get(start);
            if (!sameSourceSlot(candidate, first)) continue;
            boolean matches = true;
            for (int i = 1; i < batch.size(); i++) {
                if (!sameSourceSlot(full.get(start + i), batch.get(i))) {
                    matches = false;
                    break;
                }
            }
            if (matches) return start;
        }
        return -1;
    }

    private static boolean sameSourceSlot(TranscriptSegment a, TranscriptSegment b) {
        return a != null && b != null && a.startMs == b.startMs && a.endMs == b.endMs;
    }

    private static List<String> translateRange(String globalContext,
                                               List<TranscriptSegment> segments,
                                               int start,
                                               int end,
                                               String targetLang) throws Exception {
        Context context = Utils.getContext();
        if (context == null) throw new IllegalStateException("Gemini: Android context unavailable");
        String apiKey = SpanishStudyPrefs.geminiApiKey(context).trim();
        if (apiKey.isEmpty()) throw new IllegalStateException("Gemini API key is not configured");

        String model = SpanishStudyPrefs.geminiModel(context).trim()
                .replaceAll("[^A-Za-z0-9._-]", "");
        if (model.isEmpty()) model = SpanishStudyPrefs.DEFAULT_GEMINI_MODEL;

        URL url = new URL(API_ROOT + model + ":generateContent");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(READ_TIMEOUT_MS);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("x-goog-api-key", apiKey);
        conn.setDoOutput(true);

        JSONObject request = buildRequest(globalContext, segments, start, end, targetLang);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(request.toString().getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        String response = readAll(code >= 200 && code < 300
                ? conn.getInputStream() : conn.getErrorStream());
        if (code < 200 || code >= 300) {
            throw new Exception("Gemini HTTP " + code + ": " + compactError(response));
        }

        JSONObject root = new JSONObject(response);
        JSONArray candidates = root.optJSONArray("candidates");
        if (candidates == null || candidates.length() == 0) {
            throw new Exception("Gemini returned no candidate");
        }
        JSONObject content = candidates.getJSONObject(0).optJSONObject("content");
        JSONArray parts = content == null ? null : content.optJSONArray("parts");
        if (parts == null || parts.length() == 0) throw new Exception("Gemini returned no text");

        String jsonText = parts.getJSONObject(0).optString("text", "").trim();
        JSONArray arr = new JSONArray(jsonText);
        int expected = end - start;
        if (arr.length() != expected) {
            throw new Exception("Gemini range count mismatch: expected " + expected
                    + ", got " + arr.length());
        }

        Map<Integer, String> translationsById = new HashMap<>();
        Map<Integer, String> intendedSourceById = new HashMap<>();
        for (int i = 0; i < arr.length(); i++) {
            JSONObject item = arr.optJSONObject(i);
            if (item == null) throw new Exception("Gemini item " + i + " is not an object");

            int id = item.optInt("id", Integer.MIN_VALUE);
            if (id < start || id >= end) {
                throw new Exception("Gemini returned out-of-range subtitle ID: " + id);
            }
            if (translationsById.containsKey(id)) {
                throw new Exception("Gemini returned duplicate subtitle ID: " + id);
            }

            TranscriptSegment canonicalSegment = segments.get(id);
            String sourceEcho = item.optString("source", "");
            String correctedSource = item.optString("correctedSource", sourceEcho).trim();
            String translation = TranslationAlignmentGuard.normalize(
                    item.optString("translation", ""));

            // Display correction is side data only; the store independently rejects broad rewrites.
            TranscriptCorrectionStore.put(canonicalSegment.startMs, canonicalSegment.endMs,
                    canonicalSegment.text, correctedSource);
            String acceptedSource = TranscriptCorrectionStore.get(
                    canonicalSegment.startMs, canonicalSegment.endMs, canonicalSegment.text);
            intendedSourceById.put(id, acceptedSource);

            try {
                TranslationAlignmentGuard.validate(
                        canonicalSegment.text,
                        sourceEcho,
                        translation,
                        neighboringSourceTexts(segments, id));
                translationsById.put(id, translation);
            } catch (IllegalArgumentException badLine) {
                final int badId = id;
                Logger.printDebug(() -> "Gemini subtitle rejected for slot " + badId + ": "
                        + badLine.getMessage());
                translationsById.put(id, null);
            }
        }

        // Independent semantic cross-check. Google translates Gemini's Spanish back to English in
        // one batch; a clearly unrelated round trip is rejected. If this verifier is unavailable,
        // deterministic source/spacing/language/anchor guards still remain in force.
        if (targetLang != null && targetLang.toLowerCase(Locale.ROOT).startsWith("es")) {
            List<Integer> verifyIds = new ArrayList<>();
            List<String> verifySpanish = new ArrayList<>();
            for (int id = start; id < end; id++) {
                String candidate = translationsById.get(id);
                if (candidate != null && !candidate.isBlank()) {
                    verifyIds.add(id);
                    verifySpanish.add(candidate);
                }
            }
            if (!verifySpanish.isEmpty()) {
                try {
                    List<String> backTranslations = TextTranslator.translate(verifySpanish, "en");
                    int limit = Math.min(verifyIds.size(), backTranslations.size());
                    for (int i = 0; i < limit; i++) {
                        int id = verifyIds.get(i);
                        if (!TranslationAlignmentGuard.isGroundedByBackTranslation(
                                intendedSourceById.get(id), backTranslations.get(i))) {
                            final int rejectedId = id;
                            Logger.printDebug(() -> "Gemini translation failed independent grounding check: "
                                    + rejectedId);
                            translationsById.put(id, null);
                        }
                    }
                } catch (Exception verifierError) {
                    Logger.printDebug(() -> "Independent translation verifier unavailable: "
                            + verifierError.getClass().getSimpleName() + ": "
                            + verifierError.getMessage());
                }
            }
        }

        // Rescue only rejected/missing lines, in one forward Google batch, using the accepted
        // corrected English when a conservative contextual correction survived the side-data gate.
        List<Integer> rescueIds = new ArrayList<>();
        List<String> rescueSources = new ArrayList<>();
        for (int id = start; id < end; id++) {
            String translation = translationsById.get(id);
            if (translation == null || translation.isBlank()) {
                rescueIds.add(id);
                String intended = intendedSourceById.get(id);
                rescueSources.add(intended == null || intended.isBlank()
                        ? segments.get(id).text : intended);
            }
        }
        if (!rescueSources.isEmpty()) {
            try {
                List<String> rescued = TextTranslator.translate(rescueSources, targetLang);
                int limit = Math.min(rescueIds.size(), rescued.size());
                for (int i = 0; i < limit; i++) {
                    int id = rescueIds.get(i);
                    String candidate = TranslationAlignmentGuard.normalize(rescued.get(i));
                    if (TranslationAlignmentGuard.isSafeSpanishTranslation(
                            intendedSourceById.get(id), candidate)) {
                        translationsById.put(id, candidate);
                    }
                }
            } catch (Exception rescueError) {
                Logger.printDebug(() -> "Rejected Gemini line rescue failed: "
                        + rescueError.getClass().getSimpleName() + ": " + rescueError.getMessage());
            }
        }

        List<String> result = new ArrayList<>(expected);
        for (int id = start; id < end; id++) {
            String translation = translationsById.get(id);
            if (translation == null || translation.isBlank()) {
                // Keep raw source language rather than fabricating Spanish. The downstream language
                // guard refuses to speak it with a Spanish voice, making uncertainty fail safe.
                translation = segments.get(id).text;
            }
            result.add(translation);
        }
        return result;
    }

    private static List<String> neighboringSourceTexts(List<TranscriptSegment> segments, int id) {
        List<String> neighbors = new ArrayList<>(4);
        int from = Math.max(0, id - 2);
        int to = Math.min(segments.size() - 1, id + 2);
        for (int i = from; i <= to; i++) {
            if (i != id) neighbors.add(segments.get(i).text);
        }
        return neighbors;
    }

    /**
     * Whole-video context that stays small even on a 90-minute video. Repeated unusual raw terms are
     * useful evidence for niche jargon/ASR correction without paying to resend every transcript line
     * on every progressive Gemini request.
     */
    private static String buildGlobalContext(String videoId, List<TranscriptSegment> segments) {
        StringBuilder context = new StringBuilder(5_500);
        VideoMetadata metadata;
        synchronized (GeminiTranslator.class) {
            metadata = VIDEO_METADATA.get(videoId == null ? "" : videoId);
        }
        context.append("VIDEO / SUBJECT CONTEXT\n");
        if (metadata == null) {
            context.append("No reliable YouTube metadata was available. Infer domain conservatively from local transcript evidence.\n");
        } else {
            if (!metadata.title.isBlank()) context.append("Title: ").append(metadata.title).append('\n');
            if (!metadata.author.isBlank()) context.append("Creator/channel: ").append(metadata.author).append('\n');
            if (!metadata.description.isBlank()) context.append("Description/tags: ").append(metadata.description).append('\n');
        }

        Map<String, Integer> counts = new LinkedHashMap<>();
        Map<String, String> representative = new LinkedHashMap<>();
        for (TranscriptSegment segment : segments) {
            String text = segment == null || segment.text == null ? "" : segment.text;
            for (String token : text.replaceAll("[^\\p{L}\\p{N}'-]+", " ").trim().split("\\s+")) {
                if (token.isBlank()) continue;
                String key = token.toLowerCase(Locale.ROOT);
                if (key.length() < 3 || CONTEXT_STOP_WORDS.contains(key)) continue;
                counts.put(key, counts.getOrDefault(key, 0) + 1);
                representative.putIfAbsent(key, token);
            }
        }

        context.append("Recurring/unusual raw transcript terms (may themselves contain ASR errors): ");
        int written = 0;
        for (Map.Entry<String, Integer> entry : counts.entrySet()) {
            String raw = representative.get(entry.getKey());
            int count = entry.getValue();
            boolean unusual = count >= 2 || containsDigit(raw) || isUpperAcronym(raw);
            if (!unusual) continue;
            if (written > 0) context.append(", ");
            context.append(raw).append('×').append(count);
            if (++written >= MAX_RECURRING_TERMS) break;
        }
        if (written == 0) context.append("none identified");
        context.append(".\n");
        return context.toString();
    }

    private static JSONObject buildRequest(String globalContext,
                                           List<TranscriptSegment> segments,
                                           int start,
                                           int end,
                                           String targetLang) throws Exception {
        boolean spanish = targetLang != null && targetLang.toLowerCase(Locale.ROOT).startsWith("es");
        StringBuilder prompt = new StringBuilder(globalContext.length() + 8_000);
        prompt.append("You are translating timed YouTube speech for an isochronous dubbed track and bilingual study subtitles. ");
        if (spanish) {
            prompt.append("Translate into natural conversational neutral Latin American Spanish. ");
        } else {
            prompt.append("Translate naturally for spoken dubbing into language code ")
                    .append(targetLang).append(". ");
        }
        prompt.append("Use VIDEO / SUBJECT CONTEXT only to disambiguate what the speaker meant; it is NOT permission to add facts. ")
                .append("The raw captions are ASR and can contain homophones, bad spacing, wrong capitalization, phonetic spellings, niche jargon or slang. Correct a suspicious token only when metadata, repeated usage and nearby meaning give strong evidence. If uncertain, preserve the raw wording rather than inventing a correction. ")
                .append("GROUNDING RULE: every factual/content element in translation must be licensed by that ID's correctedSource. Never add an explanation, name, weapon, item, location, number, cause, conclusion or joke merely because it appears elsewhere in the video context. ")
                .append("Each ID is immutable. Never borrow, anticipate, postpone, merge or redistribute meaning across IDs. ")
                .append("RAW-SOURCE CHECKSUM RULE: copy each requested ID's raw English caption VERBATIM into source. ")
                .append("CORRECTION RULE: correctedSource is the English text a careful human caption editor would display. Leave it IDENTICAL to source unless there is high-confidence evidence of an actual ASR/parsing error. Correct terminology/proper nouns/spacing/punctuation; do not paraphrase ordinary speech. ")
                .append("SPANISH ORTHOGRAPHY RULE: use ordinary spaces between every Spanish word. Never concatenate multiple words into one long token. ")
                .append("ISOCHRONY RULE: prefer concise natural wording that preserves complete meaning so speech can fit its source time slot. ")
                .append("Return exactly one object per requested ID with id, source, correctedSource and translation. Response order does not matter.\n\n")
                .append(globalContext)
                .append("\nLOCAL TRANSCRIPT WINDOW. Only requested IDs are translated; neighbors are context only.\n");

        int localStart = Math.max(0, start - LOCAL_CONTEXT_RADIUS);
        int localEnd = Math.min(segments.size(), end + LOCAL_CONTEXT_RADIUS);
        for (int i = localStart; i < localEnd; i++) {
            TranscriptSegment s = segments.get(i);
            prompt.append('[').append(i).append(" @ ")
                    .append(s.startMs).append('-').append(s.endMs).append("ms] ")
                    .append(s.text).append('\n');
        }
        prompt.append("\nOUTPUT ONLY IDS ").append(start).append(" THROUGH ").append(end - 1).append(".\n");

        JSONObject itemProperties = new JSONObject()
                .put("id", new JSONObject().put("type", "integer")
                        .put("minimum", start).put("maximum", end - 1))
                .put("source", new JSONObject().put("type", "string"))
                .put("correctedSource", new JSONObject().put("type", "string"))
                .put("translation", new JSONObject().put("type", "string"));
        JSONObject itemSchema = new JSONObject()
                .put("type", "object")
                .put("required", new JSONArray().put("id").put("source")
                        .put("correctedSource").put("translation"))
                .put("properties", itemProperties);
        JSONObject arraySchema = new JSONObject()
                .put("type", "array")
                .put("minItems", end - start)
                .put("maxItems", end - start)
                .put("items", itemSchema);

        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                .put("temperature", 0.0)
                .put("maxOutputTokens", Math.max(900, (end - start) * 150));

        JSONObject part = new JSONObject().put("text", prompt.toString());
        JSONObject content = new JSONObject().put("parts", new JSONArray().put(part));
        return new JSONObject()
                .put("contents", new JSONArray().put(content))
                .put("generationConfig", generationConfig);
    }

    private static boolean containsDigit(String value) {
        if (value == null) return false;
        for (int i = 0; i < value.length(); i++) {
            if (Character.isDigit(value.charAt(i))) return true;
        }
        return false;
    }

    private static boolean isUpperAcronym(String value) {
        if (value == null || value.length() < 3) return false;
        int letters = 0;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isLetter(c)) {
                letters++;
                if (!Character.isUpperCase(c)) return false;
            }
        }
        return letters >= 3;
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        StringBuilder out = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(
                new InputStreamReader(in, StandardCharsets.UTF_8))) {
            for (String line; (line = reader.readLine()) != null; ) out.append(line);
        }
        return out.toString();
    }

    private static String compactError(String raw) {
        if (raw == null || raw.isEmpty()) return "unknown error";
        try {
            JSONObject root = new JSONObject(raw);
            JSONObject error = root.optJSONObject("error");
            if (error != null) return error.optString("message", raw);
        } catch (Exception ignored) {}
        return raw.length() > 400 ? raw.substring(0, 400) : raw;
    }

    private static String cleanMetadata(String value, int maxChars) {
        if (value == null) return "";
        String clean = value.trim().replaceAll("\\s+", " ");
        if (clean.length() <= maxChars) return clean;
        return clean.substring(0, maxChars).trim();
    }

    private static final class VideoMetadata {
        final String title;
        final String author;
        final String description;

        VideoMetadata(String title, String author, String description) {
            this.title = title;
            this.author = author;
            this.description = description;
        }
    }

    private static final class PreparedTranscript {
        final List<TranscriptSegment> segments;
        final String globalContext;

        PreparedTranscript(List<TranscriptSegment> segments, String globalContext) {
            this.segments = segments;
            this.globalContext = globalContext;
        }
    }
}
