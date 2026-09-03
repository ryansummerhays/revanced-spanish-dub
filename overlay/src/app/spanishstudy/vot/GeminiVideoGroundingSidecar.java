package app.spanishstudy.vot;

import android.content.Context;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Runs optional video/audio grounding without ever blocking the primary subtitle translation path.
 *
 * v2.6 originally awaited Gemini video understanding before ordinary text translation. On a slow,
 * rate-limited, unsupported, or temporarily unavailable interaction this could make every audible
 * batch arrive too late to be useful. This sidecar is deliberately best-effort: at most one request
 * per video is in flight, failures back off, and the text-only Gemini translator continues immediately.
 */
final class GeminiVideoGroundingSidecar {
    private static final long FAILURE_BACKOFF_MS = 5 * 60 * 1000L;
    private static final Set<String> IN_FLIGHT = new HashSet<>();
    private static final Map<String, Long> BACKOFF_UNTIL = new HashMap<>();

    private GeminiVideoGroundingSidecar() {}

    static void schedule(String videoId, List<TranscriptSegment> segments, String targetLang) {
        if (videoId == null || videoId.isBlank() || segments == null || segments.isEmpty()) return;
        Context context = Utils.getContext();
        if (context == null || !SpanishStudyPrefs.videoGroundingEnabled(context)) return;
        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;

        final long now = System.currentTimeMillis();
        synchronized (GeminiVideoGroundingSidecar.class) {
            Long until = BACKOFF_UNTIL.get(videoId);
            if (until != null && now < until) return;
            if (IN_FLIGHT.contains(videoId)) return;
            IN_FLIGHT.add(videoId);
        }

        // Immutable copy: the progressive translator may replace/update its own lists while this
        // best-effort side task is still running.
        final List<TranscriptSegment> snapshot = new ArrayList<>(segments);
        SpanishStudyDiagnostics.record("GROUND", "scheduled " + timeWindow(snapshot));
        Utils.runOnBackgroundThread(() -> {
            boolean success = false;
            try {
                List<String> grounded = GeminiVideoGrounding.translateBatch(videoId, snapshot, targetLang);
                success = grounded != null && grounded.size() == snapshot.size();
                SpanishStudyDiagnostics.record("GROUND", success
                        ? "completed " + timeWindow(snapshot)
                        : "unavailable; text-only translation remained active");
            } catch (Throwable error) {
                SpanishStudyDiagnostics.record("GROUND", "failed "
                        + error.getClass().getSimpleName() + ": " + safe(error.getMessage()));
            } finally {
                synchronized (GeminiVideoGroundingSidecar.class) {
                    IN_FLIGHT.remove(videoId);
                    if (!success) BACKOFF_UNTIL.put(videoId,
                            System.currentTimeMillis() + FAILURE_BACKOFF_MS);
                    else BACKOFF_UNTIL.remove(videoId);
                }
            }
        });
    }

    static synchronized void clearVideo(String videoId) {
        if (videoId == null) return;
        IN_FLIGHT.remove(videoId);
        BACKOFF_UNTIL.remove(videoId);
    }

    private static String timeWindow(List<TranscriptSegment> segments) {
        if (segments == null || segments.isEmpty()) return "empty";
        TranscriptSegment first = segments.get(0);
        TranscriptSegment last = segments.get(segments.size() - 1);
        return first.startMs + "-" + last.endMs + "ms (" + segments.size() + " events)";
    }

    private static String safe(String value) {
        if (value == null) return "";
        String clean = value.replaceAll("\\s+", " ").trim();
        return clean.length() <= 180 ? clean : clean.substring(0, 180);
    }
}
