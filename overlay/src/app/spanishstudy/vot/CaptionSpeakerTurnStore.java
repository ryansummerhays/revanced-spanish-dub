package app.spanishstudy.vot;

import java.util.NavigableSet;
import java.util.TreeSet;

/**
 * Lightweight local speaker-turn side data derived from explicit caption markup such as ">>".
 *
 * A bare marker is only a boundary signal. When the caption explicitly names a speaker after the
 * marker, {@link CaptionNamedSpeakerStore} may additionally provide a trustworthy local identity.
 */
public final class CaptionSpeakerTurnStore {
    private static final NavigableSet<Long> TURN_STARTS_MS = new TreeSet<>();
    private static final long NEAR_TOLERANCE_MS = 450L;

    private CaptionSpeakerTurnStore() {}

    public static synchronized void beginTranscript() {
        TURN_STARTS_MS.clear();
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
            TURN_STARTS_MS.add(time);
            CaptionNamedSpeakerStore.markTurn(time, rawText.substring(Math.min(rawText.length(), at + 2)));
            from = at + 2;
        }
    }

    public static String stripMarkers(String rawText) {
        return rawText == null ? "" : rawText.replace(">>", " ").replaceAll("\\s+", " ").trim();
    }

    /** True when an explicit turn marker falls between two adjacent lexical words. */
    public static synchronized boolean hasBoundaryBetween(long leftEndMs, long rightStartMs) {
        long lo = Math.min(leftEndMs, rightStartMs) - NEAR_TOLERANCE_MS;
        long hi = Math.max(leftEndMs, rightStartMs) + NEAR_TOLERANCE_MS;
        Long turn = TURN_STARTS_MS.ceiling(lo);
        return turn != null && turn <= hi;
    }

    /** True when a generated phrase begins at/very near an explicit caption speaker turn. */
    public static synchronized boolean isTurnStartNear(long timeMs) {
        Long floor = TURN_STARTS_MS.floor(timeMs + NEAR_TOLERANCE_MS);
        return floor != null && Math.abs(floor - timeMs) <= NEAR_TOLERANCE_MS;
    }

    public static synchronized int count() {
        return TURN_STARTS_MS.size();
    }
}
