package app.spanishstudy.vot;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Deque;
import java.util.Locale;

/** Small in-memory diagnostic ring buffer for failures that only reproduce on the user's device. */
public final class SpanishStudyDiagnostics {
    private static final int MAX_LINES = 260;
    private static final Deque<String> LINES = new ArrayDeque<>(MAX_LINES);
    private static final SimpleDateFormat CLOCK = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US);
    private static String lastStage = "startup";
    private static String lastMessage = "No events yet";
    private static long lastPlayheadLoggedMs = Long.MIN_VALUE;

    private SpanishStudyDiagnostics() {}

    public static synchronized void record(String stage, String message) {
        String safeStage = stage == null || stage.isBlank() ? "?" : stage.trim();
        String safeMessage = sanitize(message);
        lastStage = safeStage;
        lastMessage = safeMessage;
        String line = CLOCK.format(new Date()) + " | " + safeStage + " | " + safeMessage;
        if (LINES.size() >= MAX_LINES) LINES.removeFirst();
        LINES.addLast(line);
    }

    /** Periodic playhead breadcrumb without flooding the buffer on every video-time callback. */
    public static synchronized void samplePlayhead(long timeMs) {
        if (lastPlayheadLoggedMs == Long.MIN_VALUE || Math.abs(timeMs - lastPlayheadLoggedMs) >= 10_000L) {
            lastPlayheadLoggedMs = timeMs;
            record("CLOCK", "playhead=" + timeMs + "ms");
        }
    }

    public static synchronized String summary() {
        return lastStage + ": " + lastMessage;
    }

    public static synchronized String dump() {
        StringBuilder out = new StringBuilder();
        for (String line : LINES) out.append(line).append('\n');
        return out.toString();
    }

    public static synchronized void clear() {
        LINES.clear();
        lastStage = "diagnostics";
        lastMessage = "cleared";
        lastPlayheadLoggedMs = Long.MIN_VALUE;
        record("DIAG", "cleared");
    }

    private static String sanitize(String value) {
        if (value == null) return "";
        String clean = value.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
        return clean.length() <= 300 ? clean : clean.substring(0, 300);
    }
}
