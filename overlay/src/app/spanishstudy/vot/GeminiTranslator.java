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
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Direct Gemini transcript translator for the Spanish-study overlay.
 *
 * v2.2.2 keeps the complete source transcript available as context for every Gemini request,
 * but no longer waits for the complete translated video before the first Spanish line can play.
 * Morphe's progressive dispatcher can publish the first small translated block immediately while
 * the remaining immutable timeline is translated in larger background blocks.
 */
public final class GeminiTranslator {
    private static final int CONNECT_TIMEOUT_MS = 10_000;
    private static final int READ_TIMEOUT_MS = 60_000;
    private static final String API_ROOT =
            "https://generativelanguage.googleapis.com/v1beta/models/";

    // Used only by translateWholeTranscript(), which remains available as a compatibility/helper
    // path. Normal v2.2.2 playback uses translateBatch() through Morphe's progressive dispatcher.
    private static final int OUTPUT_SEGMENTS_PER_REQUEST = 120;

    // Keep a few prepared source transcripts so an abandoned video's final request cannot be
    // confused with a newly opened video. Each prepared transcript is immutable.
    private static final int MAX_PREPARED_TRANSCRIPTS = 3;
    private static final Map<String, PreparedTranscript> PREPARED =
            new LinkedHashMap<String, PreparedTranscript>(4, 0.75f, true) {
                @Override
                protected boolean removeEldestEntry(Map.Entry<String, PreparedTranscript> eldest) {
                    return size() > MAX_PREPARED_TRANSCRIPTS;
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
     * Captures the entire immutable source transcript before Morphe splits it into playback-sized
     * translation batches. Every later batch can therefore use whole-video context even though the
     * first batch is returned quickly.
     */
    public static synchronized void prepareTranscript(String videoId,
                                                      List<TranscriptSegment> segments,
                                                      String targetLang) {
        if (videoId == null || segments == null || segments.isEmpty()) return;
        List<TranscriptSegment> snapshot = new ArrayList<>(segments);
        PREPARED.put(cacheKey(videoId, targetLang),
                new PreparedTranscript(snapshot, buildFullContext(snapshot)));
    }

    /**
     * Full blocking translation retained for compatibility and non-playback uses. Segment ordering
     * and source timestamps remain unchanged.
     */
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
            List<String> block = translateRange(prepared.fullContext, prepared.segments,
                    start, end, targetLang);
            if (block.size() != end - start) {
                throw new Exception("Gemini range count mismatch: expected " + (end - start)
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
     * Translate one dispatcher batch while still supplying Gemini with the COMPLETE source
     * transcript. The batch itself is mapped back to its canonical source IDs/timestamps.
     */
    public static List<String> translateBatch(String videoId,
                                              List<TranscriptSegment> segments,
                                              String targetLang) throws Exception {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();

        PreparedTranscript prepared = prepared(videoId, targetLang);
        if (prepared == null) {
            // Defensive fallback. Normal playback always calls prepareTranscript() before batching.
            prepareTranscript(videoId, segments, targetLang);
            prepared = prepared(videoId, targetLang);
        }
        if (prepared == null) throw new IllegalStateException("Gemini transcript context unavailable");

        int start = findBatchStart(prepared.segments, segments);
        if (start < 0) {
            // Never silently attach a batch to the wrong IDs. If an unexpected provider reshapes
            // the list, use the local batch as its own canonical context instead.
            String localContext = buildFullContext(segments);
            return translateRange(localContext, segments, 0, segments.size(), targetLang);
        }
        int end = start + segments.size();
        return translateRange(prepared.fullContext, prepared.segments, start, end, targetLang);
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

        JSONObject request = buildRequest(fullContext, segments, start, end, targetLang);
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
        List<String> result = new ArrayList<>(arr.length());
        for (int i = 0; i < arr.length(); i++) {
            String text = arr.optString(i, "").trim();
            if (text.isEmpty()) text = segments.get(start + i).text;
            result.add(text);
        }
        return result;
    }

    private static String buildFullContext(List<TranscriptSegment> segments) {
        StringBuilder context = new StringBuilder(Math.max(4096, segments.size() * 48));
        context.append("COMPLETE SOURCE TRANSCRIPT. IDs and timestamps are authoritative.\n");
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment s = segments.get(i);
            context.append('[').append(i).append(" @ ")
                    .append(s.startMs).append('-').append(s.endMs).append("ms] ")
                    .append(s.text).append('\n');
        }
        return context.toString();
    }

    private static JSONObject buildRequest(String fullContext,
                                           List<TranscriptSegment> segments,
                                           int start,
                                           int end,
                                           String targetLang) throws Exception {
        boolean spanish = targetLang != null && targetLang.toLowerCase().startsWith("es");
        StringBuilder prompt = new StringBuilder(fullContext.length() + 4096);
        prompt.append("You are translating a complete timed YouTube transcript for a dubbed audio track. ");
        if (spanish) {
            prompt.append("Translate into natural conversational neutral Latin American Spanish. ");
        } else {
            prompt.append("Translate naturally for spoken dubbing into language code ")
                    .append(targetLang).append(". ");
        }
        prompt.append("Use the COMPLETE transcript below to resolve names, jokes, pronouns, terminology, speaker intent, and recurring phrases. ")
                .append("Do not summarize or omit. Keep each requested output concise enough to fit approximately the same source time window. ")
                .append("Preserve tone, profanity strength, names, gamer tags, numbers, and domain-specific terminology. ")
                .append("Return exactly one translated string for each requested ID, in ascending ID order.\n\n")
                .append(fullContext)
                .append("\nOUTPUT ONLY IDS ").append(start).append(" THROUGH ").append(end - 1).append(".\n");

        JSONObject arraySchema = new JSONObject()
                .put("type", "array")
                .put("minItems", end - start)
                .put("maxItems", end - start)
                .put("items", new JSONObject().put("type", "string"));

        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                .put("temperature", 0.2)
                .put("maxOutputTokens", Math.max(512, (end - start) * 80));

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

    private static final class PreparedTranscript {
        final List<TranscriptSegment> segments;
        final String fullContext;

        PreparedTranscript(List<TranscriptSegment> segments, String fullContext) {
            this.segments = segments;
            this.fullContext = fullContext;
        }
    }
}
