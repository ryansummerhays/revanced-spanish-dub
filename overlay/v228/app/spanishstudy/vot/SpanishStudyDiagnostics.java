package app.spanishstudy.vot;

import java.text.SimpleDateFormat;
import java.util.ArrayDeque;
import java.util.Date;
import java.util.Deque;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

/**
 * Component-selectable in-memory diagnostic trace for Spanish Dub Study.
 *
 * This logger is deliberately independent of Morphe control flow: callers may report state,
 * timings and errors, but the logger never decides translation/TTS/subtitle behavior.
 */
public final class SpanishStudyDiagnostics {
    public static final String LIFECYCLE = "LIFECYCLE";
    public static final String CAPTIONS = "CAPTIONS";
    public static final String TRANSLATION = "TRANSLATION";
    public static final String TTS = "TTS";
    public static final String SUBTITLES = "SUBTITLES";
    public static final String AUDIO = "AUDIO";
    public static final String SPEAKER = "SPEAKER";
    public static final String ERROR = "ERROR";

    private static final int B_LIFECYCLE = 1 << 0;
    private static final int B_CAPTIONS = 1 << 1;
    private static final int B_TRANSLATION = 1 << 2;
    private static final int B_TTS = 1 << 3;
    private static final int B_SUBTITLES = 1 << 4;
    private static final int B_AUDIO = 1 << 5;
    private static final int B_SPEAKER = 1 << 6;
    private static final int ALL = B_LIFECYCLE | B_CAPTIONS | B_TRANSLATION | B_TTS
            | B_SUBTITLES | B_AUDIO | B_SPEAKER;

    // Long enough for a substantial reproduction while still bounded in memory.
    private static final int MAX_LINES = 3000;
    private static final Deque<String> LINES = new ArrayDeque<>(MAX_LINES);
    private static final Map<String, Long> COUNTS = new LinkedHashMap<>();
    private static final SimpleDateFormat CLOCK = new SimpleDateFormat("HH:mm:ss.SSS", Locale.US);

    private static volatile int enabledMask = ALL;
    private static volatile boolean includeText;
    private static long droppedLines;
    private static long lastPlayheadLoggedMs = Long.MIN_VALUE;

    private SpanishStudyDiagnostics() {}

    public static void configure(boolean lifecycle, boolean captions, boolean translation,
                                 boolean tts, boolean subtitles, boolean audio,
                                 boolean speaker, boolean text) {
        int mask = 0;
        if (lifecycle) mask |= B_LIFECYCLE;
        if (captions) mask |= B_CAPTIONS;
        if (translation) mask |= B_TRANSLATION;
        if (tts) mask |= B_TTS;
        if (subtitles) mask |= B_SUBTITLES;
        if (audio) mask |= B_AUDIO;
        if (speaker) mask |= B_SPEAKER;
        enabledMask = mask;
        includeText = text;
        recordAlways("DIAGNOSTICS", "configuration=" + maskSummary() + " includeText=" + text);
    }

    public static boolean isEnabled(String component) {
        if (ERROR.equals(component)) return true;
        return (enabledMask & bitFor(component)) != 0;
    }

    public static boolean includeText() {
        return includeText;
    }

    public static synchronized void record(String component, String message) {
        increment(component);
        if (!isEnabled(component)) return;
        append(component, message);
    }

    public static synchronized void recordAlways(String component, String message) {
        increment(component);
        append(component, message);
    }

    public static synchronized void error(String component, String message, Throwable error) {
        increment(ERROR);
        String suffix = error == null ? "" : " exception=" + error.getClass().getSimpleName()
                + ":" + String.valueOf(error.getMessage());
        append(component + "-ERROR", message + suffix);
    }

    public static synchronized void samplePlayhead(long timeMs) {
        if (!isEnabled(LIFECYCLE)) return;
        if (lastPlayheadLoggedMs == Long.MIN_VALUE || Math.abs(timeMs - lastPlayheadLoggedMs) >= 5_000L) {
            lastPlayheadLoggedMs = timeMs;
            record(LIFECYCLE, "playhead=" + timeMs + "ms");
        }
    }

    /** Truncate user/media text for diagnostics while preserving enough context to debug. */
    public static String text(String value) {
        if (!includeText || value == null) return includeText ? "" : "<text disabled>";
        String clean = value.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
        return clean.length() <= 240 ? clean : clean.substring(0, 240) + "…";
    }

    public static synchronized String maskSummary() {
        return "lifecycle=" + isEnabled(LIFECYCLE)
                + ",captions=" + isEnabled(CAPTIONS)
                + ",translation=" + isEnabled(TRANSLATION)
                + ",tts=" + isEnabled(TTS)
                + ",subtitles=" + isEnabled(SUBTITLES)
                + ",audio=" + isEnabled(AUDIO)
                + ",speaker=" + isEnabled(SPEAKER);
    }

    public static synchronized String counters() {
        StringBuilder out = new StringBuilder();
        boolean first = true;
        for (Map.Entry<String, Long> e : COUNTS.entrySet()) {
            if (!first) out.append(',');
            first = false;
            out.append(e.getKey()).append('=').append(e.getValue());
        }
        if (droppedLines > 0) {
            if (!first) out.append(',');
            out.append("dropped=").append(droppedLines);
        }
        return out.toString();
    }

    public static synchronized String dump() {
        StringBuilder out = new StringBuilder();
        out.append("diagnosticComponents=").append(maskSummary()).append('\n');
        out.append("diagnosticIncludeText=").append(includeText).append('\n');
        out.append("diagnosticEventCounts=").append(counters()).append('\n');
        out.append("diagnosticDroppedLines=").append(droppedLines).append('\n');
        for (String line : LINES) out.append(line).append('\n');
        return out.toString();
    }

    public static synchronized void clear() {
        LINES.clear();
        COUNTS.clear();
        droppedLines = 0;
        lastPlayheadLoggedMs = Long.MIN_VALUE;
        recordAlways("DIAGNOSTICS", "cleared");
    }

    private static int bitFor(String component) {
        if (LIFECYCLE.equals(component)) return B_LIFECYCLE;
        if (CAPTIONS.equals(component)) return B_CAPTIONS;
        if (TRANSLATION.equals(component)) return B_TRANSLATION;
        if (TTS.equals(component)) return B_TTS;
        if (SUBTITLES.equals(component)) return B_SUBTITLES;
        if (AUDIO.equals(component)) return B_AUDIO;
        if (SPEAKER.equals(component)) return B_SPEAKER;
        return ALL;
    }

    private static void increment(String component) {
        COUNTS.put(component, COUNTS.getOrDefault(component, 0L) + 1L);
    }

    private static void append(String component, String message) {
        String safeComponent = component == null || component.isBlank() ? "?" : component.trim();
        String safe = sanitize(message);
        if (LINES.size() >= MAX_LINES) {
            LINES.removeFirst();
            droppedLines++;
        }
        LINES.addLast(CLOCK.format(new Date()) + " | " + safeComponent + " | " + safe);
    }

    private static String sanitize(String value) {
        if (value == null) return "";
        String clean = value.replace('\n', ' ').replace('\r', ' ').replaceAll("\\s+", " ").trim();
        return clean.length() <= 900 ? clean : clean.substring(0, 900) + "…";
    }
}
