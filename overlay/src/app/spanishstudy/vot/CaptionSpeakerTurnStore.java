package app.spanishstudy.vot;

import java.util.NavigableSet;
import java.util.TreeSet;

/**
 * Lightweight local caption-turn side data derived from explicit markup such as ">>".
 *
 * A bare ">>" is not trustworthy evidence that the human speaker changed: some YouTube tracks use
 * it as a cue/paragraph marker on nearly every caption. We retain every marker for diagnostics and
 * named-speaker extraction, but only an explicitly labelled marker such as ">> JOHN:" becomes a
 * hard speaker boundary. Future local acoustic diarization can add stronger boundaries upstream.
 */
public final class CaptionSpeakerTurnStore {
    private static final NavigableSet<Long> ALL_MARKERS_MS = new TreeSet<>();
    private static final NavigableSet<Long> HARD_TURN_STARTS_MS = new TreeSet<>();
    private static final long NEAR_TOLERANCE_MS = 450L;

    private CaptionSpeakerTurnStore() {}

    public static synchronized void beginTranscript() {
        ALL_MARKERS_MS.clear();
        HARD_TURN_STARTS_MS.clear();
        CaptionNamedSpeakerStore.beginTranscript();
    }

    /**
     * Records every explicit ">>" marker in one timed JSON3 inner chunk. If a marker occurs inside
     * the chunk rather than at its start, its timestamp is approximated by character position.
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

            String after = rawText.substring(Math.min(rawText.length(), at + 2));
            CaptionNamedSpeakerStore.markTurn(time, after);
            if (CaptionNamedSpeakerStore.extractName(after) != null) {
                HARD_TURN_STARTS_MS.add(time);
            }
            from = at + 2;
        }
    }

    public static String stripMarkers(String rawText) {
        return rawText == null ? "" : rawText.replace(">>", " ").replaceAll("\\s+", " ").trim();
    }

    /** True only when a high-confidence explicitly-labelled speaker boundary falls between words. */
    public static synchronized boolean hasBoundaryBetween(long leftEndMs, long rightStartMs) {
        long lo = Math.min(leftEndMs, rightStartMs) - NEAR_TOLERANCE_MS;
        long hi = Math.max(leftEndMs, rightStartMs) + NEAR_TOLERANCE_MS;
        Long turn = HARD_TURN_STARTS_MS.ceiling(lo);
        return turn != null && turn <= hi;
    }

    /** True only when a generated phrase begins near a labelled caption speaker turn. */
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
