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
 * Optional direct Gemini translator used by the Spanish-study overlay.
 *
 * It intentionally lives outside Morphe's normal provider setting so Google/MyMemory/OpenRouter
 * remain available as fallbacks. When enabled and configured, TranscriptTranslator delegates
 * each play-head-prioritized batch here.
 */
public final class GeminiTranslator {
    private static final int CONNECT_TIMEOUT_MS = 10_000;
    private static final int READ_TIMEOUT_MS = 20_000;
    private static final String API_ROOT =
            "https://generativelanguage.googleapis.com/v1beta/models/";

    private GeminiTranslator() {}

    public static boolean isEnabled() {
        Context context = Utils.getContext();
        return context != null
                && SpanishStudyPrefs.geminiEnabled(context)
                && !SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty();
    }

    /** Returns one translation per input segment, preserving the input ordering. */
    public static List<String> translateBatch(String videoId,
                                              List<TranscriptSegment> segments,
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

        JSONObject request = buildRequest(segments, targetLang);
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
        JSONArray translated = new JSONArray(jsonText);
        if (translated.length() != segments.size()) {
            throw new Exception("Gemini line count mismatch: expected " + segments.size()
                    + ", got " + translated.length());
        }
        List<String> result = new ArrayList<>(segments.size());
        for (int i = 0; i < translated.length(); i++) {
            String text = translated.optString(i, "").trim();
            if (text.isEmpty()) text = segments.get(i).text;
            result.add(text);
        }
        return result;
    }

    private static JSONObject buildRequest(List<TranscriptSegment> segments, String targetLang)
            throws Exception {
        boolean spanish = targetLang != null && targetLang.toLowerCase().startsWith("es");
        StringBuilder prompt = new StringBuilder(2048);
        if (spanish) {
            prompt.append("Translate each numbered line into natural conversational Spanish for dubbing. ")
                    .append("Use neutral Latin American Spanish unless the context strongly suggests otherwise. ");
        } else {
            prompt.append("Translate each numbered line naturally for spoken dubbing into language code ")
                    .append(targetLang).append(". ");
        }
        prompt.append("All lines are consecutive context from the same YouTube conversation. ")
                .append("Preserve meaning, tone, jokes, profanity strength, gamer tags, names, numbers, and gaming terminology. ")
                .append("For gaming slang, translate the intended meaning rather than the literal English words. ")
                .append("Prefer concise phrasing that can be spoken in about the same time as the source. ")
                .append("Do not explain, summarize, censor, or add information. Return exactly one output string for every input line, in order.\n\n");
        for (int i = 0; i < segments.size(); i++) {
            prompt.append(i + 1).append(": ").append(segments.get(i).text).append('\n');
        }

        JSONObject arraySchema = new JSONObject()
                .put("type", "array")
                .put("minItems", segments.size())
                .put("maxItems", segments.size())
                .put("items", new JSONObject().put("type", "string"));

        JSONObject generationConfig = new JSONObject()
                .put("responseMimeType", "application/json")
                .put("responseJsonSchema", arraySchema)
                .put("maxOutputTokens", Math.max(256, segments.size() * 100));

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
        return raw.length() > 240 ? raw.substring(0, 240) : raw;
    }
}
