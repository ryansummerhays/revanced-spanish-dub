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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import app.morphe.extension.shared.Logger;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.shared.translation.TextTranslator;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Direct Gemini transcript translator for the Spanish-study overlay.
 *
 * Alignment is data integrity: Gemini must return every translation keyed to an immutable source
 * event ID and echo the raw caption text exactly. v2.3.2 additionally supplies YouTube title,
 * creator and description context and asks Gemini to infer domain terminology/jargon from the whole
 * transcript before translating. A separate correctedSource field may clean a high-confidence ASR
 * error for English subtitle display, while raw source text/timestamps remain the immutable clock.
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
     * No extra YouTube request is needed. Description is deliberately capped before it reaches the
     * repeated progressive translation prompts.
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

    /** Capture the complete immutable source transcript before Morphe splits it into batches. */
    public static synchronized void prepareTranscript(String videoId,
                                                      List<TranscriptSegment> segments,
                                                      String targetLang) {
        if (videoId == null || segments == null || segments.isEmpty()) return;
        List<TranscriptSegment> snapshot = new ArrayList<>(segments);
        PREPARED.put(cacheKey(videoId, targetLang),
                new PreparedTranscript(snapshot, buildFullContext(videoId, snapshot)));
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
                block = translateRange(prepared.fullContext, prepared.segments, start, end, targetLang);
            } catch (Exception ex) {
                Logger.printDebug(() -> "Gemini full-transcript block failed alignment/latency check; using Google fallback", ex);
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
     * Translate one progressive dispatcher batch. Gemini still receives the complete source
     * transcript plus video metadata as context, but each response item carries its immutable source
     * ID and exact raw source echo. Response ordering is therefore irrelevant.
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
                String localContext = buildFullContext(videoId, segments);
                return translateRange(localContext, segments, 0, segments.size(), targetLang);
            }
            return translateRange(prepared.fullContext, prepared.segments,
                    start, start + segments.size(), targetLang);
        } catch (Exception ex) {
            Logger.printDebug(() -> "Gemini batch timed out/failed alignment validation; using Google fallback", ex);
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

    private static List<String> translateRange(String fullContext,
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

        JSONObject request = buildRequest(fullContext, start, end, targetLang);
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
            String translation = item.optString("translation", "").trim();
            TranslationAlignmentGuard.validate(
                    canonicalSegment.text,
                    sourceEcho,
                    translation,
                    neighboringSourceTexts(segments, id));

            // Display correction is side data only. The store independently rejects broad rewrites.
            TranscriptCorrectionStore.put(canonicalSegment.startMs, canonicalSegment.endMs,
                    canonicalSegment.text, correctedSource);
            translationsById.put(id, translation);
        }

        List<String> result = new ArrayList<>(expected);
        for (int id = start; id < end; id++) {
            String translation = translationsById.get(id);
            if (translation == null || translation.isBlank()) {
                throw new Exception("Gemini omitted subtitle ID: " + id);
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

    private static String buildFullContext(String videoId, List<TranscriptSegment> segments) {
        StringBuilder context = new StringBuilder(Math.max(4600, segments.size() * 48));
        VideoMetadata metadata;
        synchronized (GeminiTranslator.class) {
            metadata = VIDEO_METADATA.get(videoId == null ? "" : videoId);
        }
        context.append("VIDEO / SUBJECT CONTEXT\n");
        if (metadata == null) {
            context.append("No reliable YouTube metadata was available. Infer subject/domain only from repeated transcript evidence.\n");
        } else {
            if (!metadata.title.isBlank()) context.append("Title: ").append(metadata.title).append('\n');
            if (!metadata.author.isBlank()) context.append("Creator/channel: ").append(metadata.author).append('\n');
            if (!metadata.description.isBlank()) context.append("Description: ").append(metadata.description).append('\n');
        }
        context.append("\nCOMPLETE RAW SOURCE TRANSCRIPT. IDs and timestamps are authoritative; wording may contain ASR errors.\n");
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment s = segments.get(i);
            context.append('[').append(i).append(" @ ")
                    .append(s.startMs).append('-').append(s.endMs).append("ms] ")
                    .append(s.text).append('\n');
        }
        return context.toString();
    }

    private static JSONObject buildRequest(String fullContext,
                                           int start,
                                           int end,
                                           String targetLang) throws Exception {
        boolean spanish = targetLang != null && targetLang.toLowerCase().startsWith("es");
        StringBuilder prompt = new StringBuilder(fullContext.length() + 6500);
        prompt.append("You are translating a complete timed YouTube transcript for an isochronous dubbed audio track and bilingual study subtitles. ");
        if (spanish) {
            prompt.append("Translate into natural conversational neutral Latin American Spanish. ");
        } else {
            prompt.append("Translate naturally for spoken dubbing into language code ")
                    .append(targetLang).append(". ");
        }
        prompt.append("First use the VIDEO / SUBJECT CONTEXT and the COMPLETE transcript to infer the video's domain, recurring entities, names, products, games, characters, technical vocabulary, slang, abbreviations, memes and jargon. ")
                .append("Treat the raw transcript as ASR that can contain homophones, bad spacing, wrong capitalization, phonetic spellings, or niche terms that a generic recognizer misunderstood. Resolve a suspicious token from global context only when evidence is strong: metadata, repeated transcript usage, nearby meaning, and well-known domain terminology should agree. For example, in a clearly Apex Legends weapon discussion, a raw token like 'DVO' may actually mean 'Devo' or 'Devotion' if the surrounding evidence strongly supports that reading. Do NOT guess merely because a correction is possible. ")
                .append("Each ID is one immutable semantic subtitle event. Never move meaning between IDs. ")
                .append("CRITICAL RAW-SOURCE RULE: copy the requested ID's raw English caption VERBATIM into source, even when you believe it contains an ASR error. This field is an integrity checksum. ")
                .append("CORRECTION RULE: correctedSource is the English text a careful human caption editor would display. Leave it IDENTICAL to source unless there is high-confidence contextual evidence of an actual transcription/parsing error. Correct proper nouns, jargon, acronyms, homophones, spacing, capitalization or punctuation; do not paraphrase, polish style, censor slang, or rewrite ordinary speech. ")
                .append("TRANSLATION RULE: translate the intended meaning represented by correctedSource, while still translating ONLY this ID. Do not borrow, anticipate, postpone, merge or redistribute meaning from neighboring IDs. ")
                .append("The translation must be a complete semantic counterpart so a learner can pause on one event and compare the two languages directly. ")
                .append("ISOCHRONY RULE: prefer the shortest natural wording that preserves the full meaning. Avoid filler, redundant pronouns, unnecessary discourse markers and wordy literal constructions so speech can finish inside the source timestamp. ")
                .append("SUBTITLE RULE: prefer compact natural clauses, but never omit required meaning just to hit a width target. The renderer can wrap unusually long natural phrases. ")
                .append("Return exactly one object for every requested ID. Object fields are id, source, correctedSource, and translation. Response order does not matter because IDs are authoritative.\n\n")
                .append(fullContext)
                .append("\nOUTPUT ONLY IDS ").append(start).append(" THROUGH ").append(end - 1).append(".\n");

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
        final String fullContext;

        PreparedTranscript(List<TranscriptSegment> segments, String fullContext) {
            this.segments = segments;
            this.fullContext = fullContext;
        }
    }
}
