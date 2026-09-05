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
import app.morphe.extension.youtube.settings.Settings;

/**
 * Cheap, isolated whole-video speaker sidecar.
 *
 * Kept under the historical class name so older controller call sites remain compatible. v2.25
 * uses the user's existing Morphe OpenRouter key, pins YouTube URL processing to Google AI Studio,
 * and starts with Gemini 3.5 Flash Lite Flex in agentic video mode. A stronger Gemini 3.7 Flash
 * pass is used at most once, and only when the cheap map is semantically unusable.
 */
final class GeminiSpeakerDiarizationSidecar {
    private static final String OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions";
    private static final String CHEAP_MODEL = "google/gemini-3.5-flash-lite";
    private static final String FALLBACK_MODEL = "google/gemini-3.7-flash";
    private static final String GOOGLE_PROVIDER = "google-ai-studio";
    private static final int CONNECT_TIMEOUT_MS = 8_000;
    private static final int READ_TIMEOUT_MS = 180_000;
    private static final int MAX_EVENTS = 650;
    private static final long SOURCE_STABLE_MS = 1_500L;
    private static final long QUOTA_BACKOFF_MS = 10 * 60_000L;
    private static final long FAILURE_BACKOFF_MS = 60_000L;

    private static String currentVideoId = "";
    private static boolean inFlight;
    private static boolean analysisComplete;
    private static long requestGeneration;
    private static long backoffUntilWallMs;
    private static int observedSourceSize = -1;
    private static long sourceStableSinceWallMs;

    private static int requests;
    private static int succeeded;
    private static int failed;
    private static int staleDrops;
    private static int flexRetries;
    private static int strongFallbacks;
    private static long inputTokens;
    private static long outputTokens;
    private static long totalTokens;
    private static double actualCostUsd;
    private static int lastHttpStatus;
    private static long lastLatencyMs;
    private static String lastModel = "none";
    private static String lastTier = "none";
    private static String lastProvider = "none";
    private static String lastError = "none";

    private GeminiSpeakerDiarizationSidecar() {}

    static synchronized void clear() {
        currentVideoId = "";
        inFlight = false;
        analysisComplete = false;
        requestGeneration++;
        backoffUntilWallMs = 0L;
        observedSourceSize = -1;
        sourceStableSinceWallMs = 0L;
        requests = succeeded = failed = staleDrops = flexRetries = strongFallbacks = 0;
        inputTokens = outputTokens = totalTokens = 0L;
        actualCostUsd = 0.0;
        lastHttpStatus = 0;
        lastLatencyMs = 0L;
        lastModel = lastTier = lastProvider = "none";
        lastError = "none";
    }

    static synchronized void onSessionBoundary() {
        requestGeneration++;
        inFlight = false;
    }

    static void maybeSchedule(String videoId, List<TranscriptSegment> source, long playheadMs) {
        Context context = Utils.getContext();
        if (context == null || videoId == null || videoId.isBlank() || source == null || source.isEmpty()) return;
        if (!SpanishStudyPrefs.speakerRecognitionEnabled(context)) return;
        String key = Settings.VOT_OPENROUTER_API_KEY.get().trim();
        if (key.isEmpty()) return;

        long now = System.currentTimeMillis();
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            if (!videoId.equals(currentVideoId)) {
                currentVideoId = videoId;
                inFlight = false;
                analysisComplete = false;
                requestGeneration++;
                backoffUntilWallMs = 0L;
                observedSourceSize = -1;
                sourceStableSinceWallMs = now;
            }
            if (analysisComplete || inFlight || now < backoffUntilWallMs) return;
            if (source.size() != observedSourceSize) {
                observedSourceSize = source.size();
                sourceStableSinceWallMs = now;
                return;
            }
            if (now - sourceStableSinceWallMs < SOURCE_STABLE_MS) return;
            inFlight = true;
        }

        final List<TranscriptSegment> snapshot = sampleTimeline(source);
        if (snapshot.isEmpty()) {
            synchronized (GeminiSpeakerDiarizationSidecar.class) { inFlight = false; }
            return;
        }
        final String transcriptCorpus = transcriptCorpus(snapshot);
        final long requestEpoch = SpanishStudyRuntimeTelemetry.currentEpoch();
        final long generation;
        synchronized (GeminiSpeakerDiarizationSidecar.class) { generation = requestGeneration; }

        SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                + " action=start events=" + snapshot.size() + " backend=openrouter model=" + CHEAP_MODEL
                + " tier=flex processing=agentic");

        Utils.runOnBackgroundThread(() -> {
            long started = System.currentTimeMillis();
            boolean success = false;
            boolean stale = false;
            try {
                Analysis result;
                try {
                    result = requestMap(key, videoId, snapshot, CHEAP_MODEL, "flex");
                } catch (Exception flexEx) {
                    if (!retryableTransport(flexEx)) throw flexEx;
                    synchronized (GeminiSpeakerDiarizationSidecar.class) { flexRetries++; }
                    SpanishStudyDiagnostics.record("SPEAKER-WORKER",
                            "action=flex-retry model=" + CHEAP_MODEL + " reason=" + safe(flexEx.getMessage()));
                    result = requestMap(key, videoId, snapshot, CHEAP_MODEL, null);
                }

                if (!usable(result, snapshot.size())) {
                    synchronized (GeminiSpeakerDiarizationSidecar.class) { strongFallbacks++; }
                    SpanishStudyDiagnostics.record("SPEAKER-WORKER",
                            "action=quality-fallback coverage=" + String.format(Locale.ROOT, "%.2f", result.coverage)
                                    + " globalConfidence=" + String.format(Locale.ROOT, "%.2f", result.globalConfidence)
                                    + " model=" + FALLBACK_MODEL);
                    result = requestMap(key, videoId, snapshot, FALLBACK_MODEL, "flex");
                }
                if (!usable(result, snapshot.size()))
                    throw new Exception("speaker map below quality floor coverage=" + result.coverage
                            + " confidence=" + result.globalConfidence);

                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    stale = generation != requestGeneration
                            || !SpanishStudyController.isSpeakerRequestCurrent(requestEpoch, videoId);
                    if (stale) staleDrops++;
                }
                if (!stale) {
                    SpeakerAssignmentStore.commitBatch(snapshot, result.proposals);
                    for (NameProposal name : result.names) {
                        SpeakerAssignmentStore.setProfileName(name.speaker, name.name,
                                name.confidence, name.evidence, transcriptCorpus);
                    }
                    SpanishStudyController.refreshSpeakerVoices();
                    synchronized (GeminiSpeakerDiarizationSidecar.class) {
                        analysisComplete = true;
                        succeeded++;
                        lastError = "none";
                    }
                    success = true;
                    SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                            + " action=success events=" + snapshot.size() + " profiles="
                            + SpeakerAssignmentStore.profileSummary() + " costUsd="
                            + String.format(Locale.ROOT, "%.6f", actualCostUsd));
                } else {
                    SpanishStudyDiagnostics.record("SPEAKER-WORKER", "requestEpoch=" + requestEpoch
                            + " currentEpoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                            + " action=stale-drop");
                }
            } catch (Exception ex) {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    failed++;
                    lastError = safe(ex.getMessage());
                    long delay = lastHttpStatus == 429 ? QUOTA_BACKOFF_MS : FAILURE_BACKOFF_MS;
                    backoffUntilWallMs = Math.max(backoffUntilWallMs, System.currentTimeMillis() + delay);
                }
                SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                        + " action=failed error=" + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));
            } finally {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    if (generation == requestGeneration) inFlight = false;
                    lastLatencyMs = System.currentTimeMillis() - started;
                    if (!success && stale) backoffUntilWallMs = 0L;
                }
            }
        });
    }

    private static Analysis requestMap(String apiKey, String videoId, List<TranscriptSegment> segments,
                                       String model, String serviceTier) throws Exception {
        JSONObject body = buildRequest(videoId, segments, model, serviceTier);
        HttpURLConnection conn = (HttpURLConnection) new URL(OPENROUTER_URL).openConnection();
        conn.setRequestMethod("POST");
        conn.setConnectTimeout(CONNECT_TIMEOUT_MS);
        conn.setReadTimeout(READ_TIMEOUT_MS);
        conn.setRequestProperty("Content-Type", "application/json; charset=utf-8");
        conn.setRequestProperty("Authorization", "Bearer " + apiKey);
        conn.setRequestProperty("X-Title", "Spanish Dub Study");
        conn.setDoOutput(true);

        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            requests++;
            lastModel = model;
            lastTier = serviceTier == null ? "standard" : serviceTier;
        }
        long started = System.currentTimeMillis();
        try (OutputStream out = conn.getOutputStream()) {
            out.write(body.toString().getBytes(StandardCharsets.UTF_8));
        }
        int code = conn.getResponseCode();
        String response = readAll(code >= 200 && code < 300 ? conn.getInputStream() : conn.getErrorStream());
        synchronized (GeminiSpeakerDiarizationSidecar.class) { lastHttpStatus = code; }
        if (code < 200 || code >= 300) {
            String retry = conn.getHeaderField("Retry-After");
            throw new Exception("HTTP " + code + (retry == null ? "" : " retry-after=" + retry)
                    + " " + compactApiError(response));
        }

        JSONObject root = new JSONObject(response);
        recordUsage(root.optJSONObject("usage"));
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            lastProvider = root.optString("provider", GOOGLE_PROVIDER);
            lastLatencyMs = System.currentTimeMillis() - started;
        }
        String text = extractAssistantText(root);
        if (text.isBlank()) throw new Exception("OpenRouter returned no speaker JSON");
        return parseAnalysis(new JSONObject(text), segments.size());
    }

    private static JSONObject buildRequest(String videoId, List<TranscriptSegment> segments,
                                           String model, String serviceTier) throws Exception {
        String prompt = buildPrompt(segments);
        JSONArray content = new JSONArray()
                .put(new JSONObject().put("type", "text").put("text", prompt))
                .put(new JSONObject().put("type", "video_url")
                        .put("video_url", new JSONObject()
                                .put("url", "https://www.youtube.com/watch?v=" + videoId))
                        // Agentic video understanding dynamically loads only the transcript/audio/frames
                        // it needs, which is both better suited and cheaper for long-form diarization.
                        .put("processing", "agentic"));

        JSONObject item = new JSONObject().put("type", "object")
                .put("additionalProperties", false)
                .put("properties", new JSONObject()
                        .put("id", new JSONObject().put("type", "integer"))
                        .put("speaker", new JSONObject().put("type", "string"))
                        .put("confidence", new JSONObject().put("type", "number")))
                .put("required", new JSONArray().put("id").put("speaker").put("confidence"));
        JSONObject profile = new JSONObject().put("type", "object")
                .put("additionalProperties", false)
                .put("properties", new JSONObject()
                        .put("speaker", new JSONObject().put("type", "string"))
                        .put("name", new JSONObject().put("type", "string"))
                        .put("name_confidence", new JSONObject().put("type", "number"))
                        .put("name_evidence", new JSONObject().put("type", "string")))
                .put("required", new JSONArray().put("speaker").put("name")
                        .put("name_confidence").put("name_evidence"));
        JSONObject schema = new JSONObject().put("type", "object")
                .put("additionalProperties", false)
                .put("properties", new JSONObject()
                        .put("speaker_count", new JSONObject().put("type", "integer"))
                        .put("global_confidence", new JSONObject().put("type", "number"))
                        .put("items", new JSONObject().put("type", "array")
                                .put("minItems", segments.size()).put("maxItems", segments.size())
                                .put("items", item))
                        .put("profiles", new JSONObject().put("type", "array").put("items", profile)))
                .put("required", new JSONArray().put("speaker_count").put("global_confidence")
                        .put("items").put("profiles"));

        JSONObject body = new JSONObject()
                .put("model", model)
                .put("messages", new JSONArray().put(new JSONObject()
                        .put("role", "user").put("content", content)))
                .put("temperature", 0.0)
                .put("max_tokens", Math.min(60_000, Math.max(1800, segments.size() * 65)))
                .put("provider", new JSONObject()
                        .put("only", new JSONArray().put(GOOGLE_PROVIDER))
                        .put("allow_fallbacks", false)
                        .put("require_parameters", true))
                .put("plugins", new JSONArray().put(new JSONObject().put("id", "response-healing")))
                .put("response_format", new JSONObject()
                        .put("type", "json_schema")
                        .put("json_schema", new JSONObject()
                                .put("name", "speaker_timeline")
                                .put("strict", true)
                                .put("schema", schema)));
        if (serviceTier != null) body.put("service_tier", serviceTier);
        return body;
    }

    private static String buildPrompt(List<TranscriptSegment> segments) {
        StringBuilder p = new StringBuilder();
        p.append("Create an anonymous speaker diarization map for the supplied public YouTube video. ")
                .append("Use DIGITAL AUDIO voice identity for speaker A-H clustering, not wording alone. ")
                .append("The same human must keep the same letter throughout the video despite yelling, whispering, laughter, emotion, accent/prosody changes, or microphone effects. ")
                .append("Navigate to the supplied timestamps and compare voices globally before inventing a new speaker. ")
                .append("Return exactly one items entry for every caption id below in the same id range. ")
                .append("confidence is acoustic speaker-identity confidence from 0 to 1.\n\n")
                .append("OPTIONAL NAMES: names are NOT voice or face recognition. You may set a profile name only when the caption text below explicitly establishes that name through an introduction, self-introduction, direct address, or similarly clear textual evidence. ")
                .append("Never infer a real-world identity from voice, face, appearance, channel knowledge, title knowledge, or general world knowledge. ")
                .append("If the captions do not establish a name, use an empty name. name_evidence must be a short EXACT quote copied from the supplied caption text and must contain the proposed name. Otherwise leave name, name_evidence empty and name_confidence 0.\n\n")
                .append("CAPTION EVENTS:\n");
        for (int i = 0; i < segments.size(); i++) {
            TranscriptSegment s = segments.get(i);
            String text = s.text == null ? "" : s.text.replace('\n', ' ').replace('\r', ' ');
            p.append(i).append(" | ").append(formatTime(s.startMs)).append('-')
                    .append(formatTime(s.endMs)).append(" | ").append(text).append('\n');
        }
        return p.toString();
    }

    private static Analysis parseAnalysis(JSONObject parsed, int expected) throws Exception {
        JSONArray items = parsed.optJSONArray("items");
        if (items == null || items.length() != expected)
            throw new Exception("speaker item count " + (items == null ? -1 : items.length()) + "/" + expected);
        ArrayList<SpeakerAssignmentStore.Proposal> proposals = new ArrayList<>(expected);
        for (int i = 0; i < expected; i++) proposals.add(null);
        int accepted = 0;
        for (int i = 0; i < items.length(); i++) {
            JSONObject o = items.optJSONObject(i);
            if (o == null) continue;
            int id = o.optInt("id", -1);
            String speaker = o.optString("speaker", "");
            float confidence = (float) o.optDouble("confidence", 0.0);
            if (id < 0 || id >= expected || !speaker.matches("(?i)(speaker[ _]?)?[A-H1-8]")) continue;
            proposals.set(id, new SpeakerAssignmentStore.Proposal(speaker, confidence));
            if (confidence >= 0.65f) accepted++;
        }
        ArrayList<NameProposal> names = new ArrayList<>();
        JSONArray profiles = parsed.optJSONArray("profiles");
        if (profiles != null) for (int i = 0; i < profiles.length(); i++) {
            JSONObject o = profiles.optJSONObject(i);
            if (o == null) continue;
            names.add(new NameProposal(o.optString("speaker", ""), o.optString("name", ""),
                    o.optDouble("name_confidence", 0.0), o.optString("name_evidence", "")));
        }
        double global = parsed.optDouble("global_confidence", 0.0);
        return new Analysis(proposals, names, global, expected == 0 ? 0.0 : accepted / (double) expected);
    }

    private static boolean usable(Analysis a, int expected) {
        return a != null && a.proposals.size() == expected && a.coverage >= 0.72 && a.globalConfidence >= 0.62;
    }

    private static List<TranscriptSegment> sampleTimeline(List<TranscriptSegment> source) {
        ArrayList<TranscriptSegment> valid = new ArrayList<>();
        for (TranscriptSegment s : source) if (s != null && s.text != null && !s.text.isBlank()) valid.add(s);
        if (valid.size() <= MAX_EVENTS) return valid;

        // Keep introductions especially well represented, then uniformly cover the remainder.
        int head = Math.min(70, MAX_EVENTS / 5);
        int tail = Math.min(20, MAX_EVENTS / 12);
        ArrayList<TranscriptSegment> out = new ArrayList<>(MAX_EVENTS);
        for (int i = 0; i < head; i++) out.add(valid.get(i));
        int middleSlots = MAX_EVENTS - head - tail;
        int middleStart = head;
        int middleEnd = valid.size() - tail;
        for (int i = 0; i < middleSlots; i++) {
            int index = middleStart + (int) Math.round(i * Math.max(0, middleEnd - middleStart - 1.0)
                    / Math.max(1.0, middleSlots - 1.0));
            TranscriptSegment s = valid.get(Math.min(valid.size() - 1, index));
            if (out.isEmpty() || out.get(out.size() - 1) != s) out.add(s);
        }
        for (int i = Math.max(head, valid.size() - tail); i < valid.size() && out.size() < MAX_EVENTS; i++)
            out.add(valid.get(i));
        return out;
    }

    private static String transcriptCorpus(List<TranscriptSegment> source) {
        StringBuilder out = new StringBuilder();
        for (TranscriptSegment s : source) {
            if (s == null || s.text == null || s.text.isBlank()) continue;
            if (out.length() > 0) out.append(' ');
            out.append(s.text.replace('\n', ' ').replace('\r', ' '));
        }
        return out.toString();
    }

    private static String extractAssistantText(JSONObject root) {
        JSONArray choices = root.optJSONArray("choices");
        if (choices == null || choices.length() == 0) return "";
        JSONObject message = choices.optJSONObject(0) == null ? null : choices.optJSONObject(0).optJSONObject("message");
        if (message == null) return "";
        Object content = message.opt("content");
        if (content instanceof String) return ((String) content).trim();
        if (content instanceof JSONArray) {
            StringBuilder out = new StringBuilder();
            JSONArray parts = (JSONArray) content;
            for (int i = 0; i < parts.length(); i++) {
                JSONObject part = parts.optJSONObject(i);
                if (part != null && "text".equals(part.optString("type"))) out.append(part.optString("text", ""));
            }
            return out.toString().trim();
        }
        return "";
    }

    private static synchronized void recordUsage(JSONObject usage) {
        if (usage == null) return;
        inputTokens += Math.max(0L, usage.optLong("prompt_tokens", 0L));
        outputTokens += Math.max(0L, usage.optLong("completion_tokens", 0L));
        totalTokens += Math.max(0L, usage.optLong("total_tokens", 0L));
        double cost = usage.optDouble("cost", 0.0);
        if (Double.isFinite(cost) && cost > 0.0) actualCostUsd += cost;
    }

    static synchronized String status() {
        if (Settings.VOT_OPENROUTER_API_KEY.get().trim().isEmpty()) return "OpenRouter key missing";
        String base = SpeakerAssignmentStore.profileSummary();
        if (inFlight) return base + " · mapping full video";
        if (analysisComplete) return base + " · mapped";
        long remaining = Math.max(0L, backoffUntilWallMs - System.currentTimeMillis());
        if (remaining > 0 && lastHttpStatus == 429) return base + " · OpenRouter quota/rate limited";
        if (remaining > 0) return base + " · retry later";
        return base;
    }

    static synchronized String usageStatus() {
        return requests + " call" + (requests == 1 ? "" : "s") + " · $"
                + String.format(Locale.ROOT, "%.4f", actualCostUsd) + " actual";
    }

    static synchronized String usageDetails() {
        return "OpenRouter whole-video speaker analysis\n"
                + "Normal model: " + CHEAP_MODEL + " (Google AI Studio Flex, agentic video)\n"
                + "Fallback model: " + FALLBACK_MODEL + " (only if the cheap map is unusable)\n"
                + "Requests: " + requests + " · successes: " + succeeded + " · failures: " + failed + "\n"
                + "Flex retries: " + flexRetries + " · strong fallbacks: " + strongFallbacks + "\n"
                + "Input tokens: " + inputTokens + " · output tokens: " + outputTokens
                + " · total tokens: " + totalTokens + "\n"
                + "Actual OpenRouter billed cost: $" + String.format(Locale.ROOT, "%.6f", actualCostUsd) + "\n"
                + "Last model: " + lastModel + " · tier: " + lastTier + " · provider: " + lastProvider + "\n"
                + "Last HTTP: " + lastHttpStatus + " · latency: " + lastLatencyMs + " ms\n"
                + "Last error: " + lastError + "\n\n"
                + "Speaker letters come from digital-audio diarization. Human names are accepted only when verified against explicit transcript evidence; voice/face identity recognition is not used.";
    }

    static synchronized String diagnostics() {
        return "speakerBackend=openrouter-google-ai-studio-agentic\n"
                + "speakerPrimaryModel=" + CHEAP_MODEL + "\n"
                + "speakerFallbackModel=" + FALLBACK_MODEL + "\n"
                + "speakerRequests=" + requests + '\n'
                + "speakerSucceeded=" + succeeded + '\n'
                + "speakerFailed=" + failed + '\n'
                + "speakerStaleDrops=" + staleDrops + '\n'
                + "speakerFlexRetries=" + flexRetries + '\n'
                + "speakerStrongFallbacks=" + strongFallbacks + '\n'
                + "speakerInputTokens=" + inputTokens + '\n'
                + "speakerOutputTokens=" + outputTokens + '\n'
                + "speakerTotalTokens=" + totalTokens + '\n'
                + "speakerActualCostUsd=" + String.format(Locale.ROOT, "%.6f", actualCostUsd) + '\n'
                + "speakerLastHttpStatus=" + lastHttpStatus + '\n'
                + "speakerLastLatencyMs=" + lastLatencyMs + '\n'
                + "speakerLastModel=" + lastModel + '\n'
                + "speakerLastTier=" + lastTier + '\n'
                + "speakerLastProvider=" + lastProvider + '\n'
                + "speakerLastError=" + safe(lastError) + '\n';
    }

    private static boolean retryableTransport(Exception ex) {
        String m = safe(ex.getMessage()).toLowerCase(Locale.ROOT);
        return m.contains("http 429") || m.contains("http 500") || m.contains("http 502")
                || m.contains("http 503") || m.contains("http 504") || m.contains("timed out")
                || m.contains("timeout") || m.contains("connection reset");
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        StringBuilder out = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(in, StandardCharsets.UTF_8))) {
            for (String line; (line = reader.readLine()) != null; ) out.append(line);
        }
        return out.toString();
    }

    private static String compactApiError(String raw) {
        if (raw == null || raw.isBlank()) return "unknown error";
        try {
            JSONObject root = new JSONObject(raw);
            JSONObject error = root.optJSONObject("error");
            if (error != null) return safe(error.optString("message", error.toString()));
        } catch (Exception ignored) {}
        return safe(raw);
    }

    private static String safe(String s) {
        if (s == null) return "";
        String v = s.replace('\n', ' ').replace('\r', ' ').trim();
        return v.length() > 360 ? v.substring(0, 360) : v;
    }

    private static String formatTime(long ms) {
        long total = Math.max(0L, ms) / 1000L, h = total / 3600L,
                m = (total % 3600L) / 60L, s = total % 60L;
        return h > 0 ? String.format(Locale.ROOT, "%d:%02d:%02d", h, m, s)
                : String.format(Locale.ROOT, "%02d:%02d", m, s);
    }

    private static final class NameProposal {
        final String speaker, name, evidence;
        final double confidence;
        NameProposal(String speaker, String name, double confidence, String evidence) {
            this.speaker = speaker; this.name = name; this.confidence = confidence; this.evidence = evidence;
        }
    }

    private static final class Analysis {
        final List<SpeakerAssignmentStore.Proposal> proposals;
        final List<NameProposal> names;
        final double globalConfidence, coverage;
        Analysis(List<SpeakerAssignmentStore.Proposal> proposals, List<NameProposal> names,
                 double globalConfidence, double coverage) {
            this.proposals = proposals; this.names = names;
            this.globalConfidence = globalConfidence; this.coverage = coverage;
        }
    }
}
