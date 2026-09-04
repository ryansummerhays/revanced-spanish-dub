package app.spanishstudy.vot;

import java.util.NavigableSet;
import java.util.TreeSet;

/**
 * Lightweight local caption-turn side data derived from explicit markup such as ">>".
 *
 * A bare ">>" is NOT trustworthy evidence that the human speaker changed. Some YouTube tracks use
 * it very frequently as a cue/paragraph marker even when the same person continues speaking. We
 * therefore retain every marker for diagnostics, but only promote a marker to a hard speaker
 * boundary when the caption itself includes an explicit speaker label such as ">> JOHN:" or
 * ">> Narrator:". Local acoustic diarization can add stronger boundaries later.
 */
public final class CaptionSpeakerTurnStore {
    private static final NavigableSet<Long> ALL_MARKERS_MS = new TreeSet<>();
    private static final NavigableSet<Long> HARD_TURN_STARTS_MS = new TreeSet<>();
    private static final long NEAR_TOLERANCE_MS = 450L;
    private static final int MAX_LABEL_CHARS = 32;

    private CaptionSpeakerTurnStore() {}

    public static synchronized void beginTranscript() {
        ALL_MARKERS_MS.clear();
        HARD_TURN_STARTS_MS.clear();
    }

    /**
     * Records every ">>" marker in one timed JSON3 inner chunk. Marker timing is approximated from
     * character position. Only explicitly labelled markers are promoted to hard speaker boundaries.
     */
    public static synchronized void markFromChunk(long startMs, long endMs, String rawText) {
        if (rawText == null || rawText.isEmpty()) return;
        long safeStart = Math.max(0L, startMs);
        long safeEnd = Math.max(safeStart + 1L, endMs);
        long span = safeEnd - safeStart;
        int from = 0;
        while (true) {
            int at = rawText.indexOf(">>", from);
            if (at < 0) break;
            double fraction = at / (double) Math.max(1, rawText.length());
            long time = safeStart + Math.round(span * fraction);
            time = Math.max(safeStart, Math.min(safeEnd, time));
            ALL_MARKERS_MS.add(time);
            if (hasExplicitSpeakerLabel(rawText, at + 2)) {
                HARD_TURN_STARTS_MS.add(time);
            }
            from = at + 2;
        }
    }

    /** Conservative explicit-label detector: accepts short capitalized/all-caps labels before ':'. */
    static boolean hasExplicitSpeakerLabel(String rawText, int markerEnd) {
        if (rawText == null || markerEnd < 0 || markerEnd >= rawText.length()) return false;
        int i = markerEnd;
        while (i < rawText.length() && Character.isWhitespace(rawText.charAt(i))) i++;
        if (i >= rawText.length()) return false;

        int colon = rawText.indexOf(':', i);
        if (colon < 0 || colon - i < 1 || colon - i > MAX_LABEL_CHARS) return false;
        String label = rawText.substring(i, colon).trim();
        if (label.startsWith("[") && label.endsWith("]") && label.length() > 2) {
            label = label.substring(1, label.length() - 1).trim();
        }
        if (label.isEmpty() || label.length() > MAX_LABEL_CHARS) return false;

        int words = 1;
        boolean hasLetter = false;
        for (int p = 0; p < label.length(); p++) {
            char c = label.charAt(p);
            if (Character.isLetter(c)) hasLetter = true;
            if (Character.isWhitespace(c) && p > 0 && !Character.isWhitespace(label.charAt(p - 1))) words++;
            if (!(Character.isLetterOrDigit(c) || Character.isWhitespace(c)
                    || c == '-' || c == '_' || c == '\'' || c == '.')) return false;
        }
        if (!hasLetter || words > 4) return false;

        // Requiring a capitalized label avoids treating ordinary constructions like
        // ">> well: I think..." as identities while still accepting "John:" and "NARRATOR:".
        char first = label.charAt(0);
        return Character.isUpperCase(first);
    }

    public static String stripMarkers(String rawText) {
        return rawText == null ? "" : rawText.replace(">>", " ").replaceAll("\\s+", " ").trim();
    }

    /** True only for a high-confidence, explicitly-labelled speaker boundary. */
    public static synchronized boolean hasBoundaryBetween(long leftEndMs, long rightStartMs) {
        long lo = Math.min(leftEndMs, rightStartMs) - NEAR_TOLERANCE_MS;
        long hi = Math.max(leftEndMs, rightStartMs) + NEAR_TOLERANCE_MS;
        Long turn = HARD_TURN_STARTS_MS.ceiling(lo);
        return turn != null && turn <= hi;
    }

    /** True only when a generated phrase starts near a high-confidence labelled speaker turn. */
    public static synchronized boolean isTurnStartNear(long timeMs) {
        Long floor = HARD_TURN_STARTS_MS.floor(timeMs + NEAR_TOLERANCE_MS);
        return floor != null && Math.abs(floor - timeMs) <= NEAR_TOLERANCE_MS;
    }

    /** Number of high-confidence caption-provided speaker boundaries. */
    public static synchronized int count() {
        return HARD_TURN_STARTS_MS.size();
    }

    /** Number of raw ">>" cue markers, including markers that are not speaker evidence. */
    public static synchronized int markerCount() {
        return ALL_MARKERS_MS.size();
    }
}
