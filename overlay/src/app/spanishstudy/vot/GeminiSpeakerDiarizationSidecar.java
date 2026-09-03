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
import java.util.Locale;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Lightweight rolling speaker diarization for one YouTube video.
 *
 * This never listens through the device microphone or speakers. A small public-YouTube window is
 * sent directly to Gemini's video/audio understanding endpoint on a background thread. The primary
 * translation/TTS path never waits for it. Results are clustered into stable A/B/C... profiles by
 * {@link SpeakerAssignmentStore}, and confirmed profiles can drive subtitle labels and alternate
 * Spanish voices.
 */
final class GeminiSpeakerDiarizationSidecar {
    private static final String INTERACTIONS_URL =
            "https://generativelanguage.googleapis.com/v1beta/interactions";
    // 3.7 Flash is explicitly documented for YouTube audio understanding + speaker diarization.
    private static final String DIARIZATION_MODEL = "gemini-3.7-flash";
    private static final int CONNECT_TIMEOUT_MS = 7_000;
    private static final int READ_TIMEOUT_MS = 22_000;
    private static final long WINDOW_BEHIND_MS = 4_000L;
    private static final long WINDOW_AHEAD_MS = 34_000L;
    private static final long ONE_SPEAKER_CADENCE_MS = 70_000L;
    private static final long MULTI_SPEAKER_CADENCE_MS = 28_000L;
    private static final long MIN_WALL_BETWEEN_CALLS_MS = 18_000L;
    private static final long FAILURE_BACKOFF_MIN_MS = 30_000L;
    private static final long FAILURE_BACKOFF_MAX_MS = 5 * 60_000L;
    private static final int MAX_EVENTS_PER_WINDOW = 48;
    private static final int MAX_REFERENCE_SPEAKERS = 3;

    private static String currentVideoId = "";
    private static long lastWindowCenterMs = Long.MIN_VALUE;
    private static long lastAttemptWallMs;
    private static long backoffUntilWallMs;
    private static int consecutiveFailures;
    private static boolean inFlight;

    private GeminiSpeakerDiarizationSidecar() {}

    static synchronized void clear() {
        currentVideoId = "";
        lastWindowCenterMs = Long.MIN_VALUE;
        lastAttemptWallMs = 0L;
        backoffUntilWallMs = 0L;
        consecutiveFailures = 0;
        inFlight = false;
    }

    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        Context context = Utils.getContext();
        if (context == null || videoId == null || videoId.isBlank()
                || source == null || source.isEmpty()) return;
        if (!SpanishStudyPrefs.speakerRecognitionEnabled(context)) return;
        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;

        final long now = System.currentTimeMillis();
        final long cadence = SpeakerAssignmentStore.profileCount() > 1
                ? MULTI_SPEAKER_CADENCE_MS : ONE_SPEAKER_CADENCE_MS;
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            if (!videoId.equals(currentVideoId)) {
                currentVideoId = videoId;
                lastWindowCenterMs = Long.MIN_VALUE;
                lastAttemptWallMs = 0L;
                backoffUntilWallMs = 0L;
                consecutiveFailures = 0;
                inFlight = false;
            }
            if (inFlight || now < backoffUntilWallMs) return;
            if (lastAttemptWallMs > 0 && now - lastAttemptWallMs < MIN_WALL_BETWEEN_CALLS_MS) return;
            if (lastWindowCenterMs != Long.MIN_VALUE
                    && Math.abs(playheadMs - lastWindowCenterMs) < cadence) return;
        }

        final List<TranscriptSegment> window = selectWindow(source, playheadMs);
        if (window.isEmpty()) return;
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            if (inFlight) return;
            inFlight = true;
            lastAttemptWallMs = now;
            lastWindowCenterMs = playheadMs;
        }

        final long clipStartMs = Math.max(0L, playheadMs - WINDOW_BEHIND_MS);
        final long clipEndMs = Math.max(clipStartMs + 1_000L, playheadMs + WINDOW_AHEAD_MS);
        final List<TranscriptSegment> snapshot = new ArrayList<>(window);
        SpanishStudyDiagnostics.record("SPEAKER", "analyzing " + clipStartMs + "-" + clipEndMs
                + "ms events=" + snapshot.size() + " model=" + DIARIZATION_MODEL);

        Utils.runOnBackgroundThread(() -> {
            boolean success = false;
            try {
                List<SpeakerAssignmentStore.Proposal> proposals =
                        request(videoId, snapshot, clipStartMs, clipEndMs);
                if (proposals != null && proposals.size() == snapshot.size()) {
                    SpeakerAssignmentStore.commitBatch(snapshot, proposals);
                    success = true;
                    SpanishStudyDiagnostics.record("SPEAKER", "window complete profiles="
                            + SpeakerAssignmentStore.profileSummary());
                } else {
                    throw new Exception("speaker proposal count mismatch");
                }
            } catch (Exception ex) {
                SpanishStudyDiagnostics.record("SPEAKER", "sidecar unavailable "
                        + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));
            } finally {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    inFlight = false;
                    if (success) {
                        consecutiveFailures = 0;
                        backoffUntilWallMs = 0L;
                    } else {
                        consecutiveFailures = Math.min(6, consecutiveFailures + 1);
                        long delay = FAILURE_BACKOFF_MIN_MS << Math.min(3, consecutiveFailures - 1);
                        backoffUntilWallMs = System.currentTimeMillis()
                                + Math.min(FAILURE_BACKOFF_MAX_MS, delay);
                    }
                }
            }
        });
    }

    static synchronized String status() {
        String base = SpeakerAssignmentStore.profileSummary();
        if (inFlight) return base + " · analyzing";
        long remaining = Math.max(0L, backoffUntilWallMs - System.currentTimeMillis());
        if (remaining > 0) return base + " · retry in " + (remaining / 1000L) + "s";
        return base;
    }

    private static List<TranscriptSegment> selectWindow(List<TranscriptSegment> source, long playheadMs) {
        long from = Math.max(0L, playheadMs - WINDOW_BEHIND_MS);
        long to = playheadMs + WINDOW_AHEAD_MS;
        ArrayList<TranscriptSegment> out = new ArrayList<>();
        for (TranscriptSegment seg : source) {
            if (seg == null || seg.endMs <= from) continue;
            if (seg.startMs >= to) break;
            out.add(seg);
            if (out.size() >= MAX_EVENTS_PER_WINDOW) break;
        }
        return out;
    }

    private static List<SpeakerAssignmentStore.Proposal> request(String videoId,
                                                                  List<TranscriptSegment> segments,
                                                                  long clipStartMs,
                                                                  long clipEndMs) throws Exception {
        Context context = Utils.getContext();
        if (context == null) throw new Exception("Android context unavailable");
        String apiKey = SpanishStudyPrefs.geminiApiKey(context).trim();
        if (apiKey.isEmpty()) throw new Exception("Gemini key missing");

        JSONObject request = buildRequest(videoId, segments, clipStartMs, clipEndMs);
        HttpURLConnection conn = (HttpURLConnection) new URL(INTERACTIONS_URL).openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(READ_TIMEOUT_MS);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("x-goog-api-key", apiKey);
        conn.setRequestProperty("Api-Revision", "2026-05-20");
        conn.setDoOutput(true);
        try (OutputStream out = conn.getOutputStream()) {
            out.write(request.toString().getBytes(StandardCharsets.UTF_8));
        }

        int code = conn.getResponseCode();
        String response = readAll(code >= 200 && code < 300
                ? conn.getInputStream() : conn.getErrorStream());
        if (code < 200 || code >= 300) {
            String retry = conn.getHeaderField("Retry-After");
            throw new Exception("HTTP " + code + (retry == null ? "" : " retry-after=" + retry)
                    + " " + compactApiError(response));
        }

        String text = extractText(new JSONObject(response));
        if (text == null || text.isBlank()) throw new Exception("no diarization output text");
        JSONObject parsed = new JSONObject(text);
        JSONArray items = parsed.optJSONArray("items");
        if (items == null || items.length() != segments.size())
            throw new Exception("diarization item count " + (items == null ? -1 : items.length())
                    + "/" + segments.size());

        ArrayList<SpeakerAssignmentStore.Proposal> out = new ArrayList<>(segments.size());
        for (int i = 0; i < segments.size(); i++) out.add(null);
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.optJSONObject(i);
            if (item == null) continue;
            int id = item.optInt("id", -1);
            if (id < 0 || id >= out.size()) continue;
            out.set(id, new SpeakerAssignmentStore.Proposal(
                    item.optString("speaker", ""),
                    (float) item.optDouble("confidence", 0.0)));
        }
        return out;
    }

    private static JSONObject buildRequest(String videoId,
                                           List<TranscriptSegment> segments,
                                           long clipStartMs,
                                           long clipEndMs) throws Exception {
        JSONArray input = new JSONArray();
        JSONObject current = new JSONObject()
                .put("type", "video")
                .put("name", "current_window")
                .put("uri", "https://www.youtube.com/watch?v=" + videoId)
                .put("mime_type", "video/mp4")
                .put("processing", new JSONObject()
                        .put("type", "static")
                        .put("start_offset", clipStartMs / 1000.0)
                        .put("end_offset", clipEndMs / 1000.0)
                        // Voice identity is the goal; keep visual-token overhead tiny.
                        .put("fps", 0.1));
        input.put(current);

        // References are only needed after multiple people have actually been established. One tiny
        // digital-audio/video anchor per profile is enough to stabilize cross-window clustering.
        if (SpeakerAssignmentStore.profileCount() > 1) {
            int added = 0;
            for (SpeakerAssignmentStore.Reference ref : SpeakerAssignmentStore.references()) {
                if (added++ >= MAX_REFERENCE_SPEAKERS) break;
                double start = Math.max(0.0, ref.startMs / 1000.0 - 1.1);
                input.put(new JSONObject()
                        .put("type", "video")
                        .put("name", "speaker_" + ref.label + "_reference")
                        .put("uri", "https://www.youtube.com/watch?v=" + videoId)
                        .put("mime_type", "video/mp4")
                        .put("processing", new JSONObject()
                                .put("type", "static")
                                .put("start_offset", start)
                                .put("end_offset", start + 2.5)
                                .put("fps", 0.05)));
            }
        }

        StringBuilder prompt = new StringBuilder();
        prompt.append("Cluster the HUMAN SPEAKERS in current_window by acoustic voice identity. ")
                .append("This is diarization, not identity recognition: use anonymous labels A-H only. ")
                .append("The same person must keep the same label across the video. Do not create a new person because someone yells, whispers, laughs, changes emotion/accent/prosody, or has a temporary microphone/voice-chat effect. ")
                .append("Use named speaker_X_reference clips as acoustic anchors when present. If uncertain, prefer the established prior profile instead of inventing a switch. ")
                .append("Return exactly one item per caption event below. confidence is 0..1 and reflects acoustic speaker-identity confidence, not transcript confidence.\n")
                .append(SpeakerAssignmentStore.rosterPrompt()).append("\n\nEVENTS:\n");
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment s = segments.get(i);
            prompt.append(i).append(" | ").append(formatTime(s.startMs)).append('-')
                    .append(formatTime(s.endMs)).append(" | ")
                    .append(s.text == null ? "" : s.text.replace('\n', ' ')).append('\n');
        }
        input.put(new JSONObject().put("type", "text").put("text", prompt.toString()));

        JSONObject itemSchema = new JSONObject()
                .put("type", "object")
                .put("properties", new JSONObject()
                        .put("id", new JSONObject().put("type", "integer"))
                        .put("speaker", new JSONObject().put("type", "string"))
                        .put("confidence", new JSONObject().put("type", "number")))
                .put("required", new JSONArray().put("id").put("speaker").put("confidence"));
        JSONObject schema = new JSONObject()
                .put("type", "object")
                .put("properties", new JSONObject().put("items", new JSONObject()
                        .put("type", "array")
                        .put("minItems", segments.size())
                        .put("maxItems", segments.size())
                        .put("items", itemSchema)))
                .put("required", new JSONArray().put("items"));

        return new JSONObject()
                .put("model", DIARIZATION_MODEL)
                .put("input", input)
                .put("generation_config", new JSONObject()
                        .put("temperature", 0.0)
                        .put("max_output_tokens", Math.max(500, segments.size() * 45)))
                .put("response_format", new JSONObject()
                        .put("type", "text")
                        .put("mime_type", "application/json")
                        .put("schema", schema));
    }

    private static String extractText(JSONObject root) {
        String direct = root.optString("output_text", "");
        if (!direct.isBlank()) return direct;
        JSONArray steps = root.optJSONArray("steps");
        if (steps != null) {
            StringBuilder out = new StringBuilder();
            for (int i = 0; i < steps.length(); i++) {
                JSONObject step = steps.optJSONObject(i);
                if (step == null || !"model_output".equals(step.optString("type"))) continue;
                JSONArray content = step.optJSONArray("content");
                if (content == null) continue;
                for (int j = 0; j < content.length(); j++) {
                    JSONObject c = content.optJSONObject(j);
                    if (c != null && "text".equals(c.optString("type"))) {
                        String text = c.optString("text", "");
                        if (!text.isBlank()) out.append(text);
                    }
                }
            }
            if (out.length() > 0) return out.toString();
        }
        JSONObject interaction = root.optJSONObject("interaction");
        return interaction == null ? "" : extractText(interaction);
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

    private static String compactApiError(String raw) {
        if (raw == null || raw.isBlank()) return "unknown error";
        try {
            JSONObject root = new JSONObject(raw);
            JSONObject error = root.optJSONObject("error");
            if (error != null) {
                String status = error.optString("status", "");
                String message = error.optString("message", "");
                String clean = (status + " " + message).trim().replaceAll("\\s+", " ");
                return clean.length() <= 260 ? clean : clean.substring(0, 260);
            }
        } catch (Exception ignored) {}
        String clean = raw.replaceAll("\\s+", " ").trim();
        return clean.length() <= 260 ? clean : clean.substring(0, 260);
    }

    private static String safe(String value) {
        if (value == null) return "";
        String clean = value.replaceAll("\\s+", " ").trim();
        return clean.length() <= 240 ? clean : clean.substring(0, 240);
    }

    private static String formatTime(long ms) {
        long total = Math.max(0L, ms) / 1000L;
        long h = total / 3600L, m = (total % 3600L) / 60L, s = total % 60L;
        return h > 0 ? String.format(Locale.ROOT, "%d:%02d:%02d", h, m, s)
                : String.format(Locale.ROOT, "%02d:%02d", m, s);
    }
}
