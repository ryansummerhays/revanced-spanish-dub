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
import java.util.List;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Direct Gemini transcript translator for the Spanish-study overlay.
 *
 * The AutoDub-style path intentionally finishes a canonical translated transcript before
 * playback uses it. Every translated string maps 1:1 to the immutable source segment index,
 * so seeking never changes translation order or invalidates timestamps.
 */
public final class GeminiTranslator {
    private static final int CONNECT_TIMEOUT_MS = 10_000;
    private static final int READ_TIMEOUT_MS = 60_000;
    private static final String API_ROOT =
            "https://generativelanguage.googleapis.com/v1beta/models/";

    // A single response can become unwieldy for very long videos. We still give every request
    // the full transcript as context, but ask it to emit only this many source segments at once.
    // Translation is completed for ALL chunks before the transcript is returned to playback.
    private static final int OUTPUT_SEGMENTS_PER_REQUEST = 120;

    private GeminiTranslator() {}

    public static boolean isEnabled() {
        Context context = Utils.getContext();
        return context != null
                && SpanishStudyPrefs.geminiEnabled(context)
                && !SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty();
    }

    /**
     * Translates the complete transcript before returning. The output list has exactly the same
     * size and ordering as {@code segments}; only text/lang change, while start/end timestamps are
     * copied verbatim and playbackStart/playbackEnd remain equal to those immutable timestamps.
     */
    public static List<TranscriptSegment> translateWholeTranscript(String videoId,
                                                                   List<TranscriptSegment> segments,
                                                                   String targetLang) throws Exception {
        if (segments == null || segments.isEmpty()) return new ArrayList<>();

        List<String> translated = new ArrayList<>(segments.size());
        for (int i = 0; i < segments.size(); i++) translated.add(null);

        final String fullContext = buildFullContext(segments);
        for (int start = 0; start < segments.size(); start += OUTPUT_SEGMENTS_PER_REQUEST) {
            int end = Math.min(segments.size(), start + OUTPUT_SEGMENTS_PER_REQUEST);
            List<String> block = translateRange(fullContext, segments, start, end, targetLang);
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
            // Explicitly pin playback windows to the source timeline. Later code in v2.2 is also
            // patched not to mutate these, but keeping this invariant here makes the contract clear.
            dst.playbackStartMs = src.startMs;
            dst.playbackEndMs = src.endMs;
            out.add(dst);
        }
        return out;
    }

    /** Kept for compatibility with older patched TranscriptTranslator code. */
    public static List<String> translateBatch(String videoId,
                                              List<TranscriptSegment> segments,
                                              String targetLang) throws Exception {
        List<TranscriptSegment> translated = translateWholeTranscript(videoId, segments, targetLang);
        List<String> out = new ArrayList<>(translated.size());
        for (TranscriptSegment s : translated) out.add(s.text);
        return out;
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
                .put("maxOutputTokens", Math.max(1024, (end - start) * 80));

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
}
