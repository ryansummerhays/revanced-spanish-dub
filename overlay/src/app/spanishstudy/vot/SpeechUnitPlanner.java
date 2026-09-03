package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/**
 * Coalesces already-natural subtitle phrases into speech units that are long enough for reliable
 * Spanish TTS playback. The semantic parser remains responsible for finding good pause boundaries;
 * this class only prevents those boundaries from creating tiny deadline windows.
 *
 * Explicit speaker turns are hard boundaries. A short line may remain short at a speaker change;
 * preserving voice ownership is more important than satisfying the normal duration floor.
 */
public final class SpeechUnitPlanner {
    /** Normal lower bound for a dub/subtitle unit after coalescing. */
    public static final long MIN_UNIT_MS = 2_400L;
    /** Never merge across a clearly separate pause; leave that silence available instead. */
    public static final long MAX_JOIN_GAP_MS = 900L;
    /** Keep one spoken unit bounded even when several tiny cues arrive together. */
    public static final long MAX_UNIT_MS = 9_000L;
    public static final int MAX_UNIT_CHARS = 150;

    private SpeechUnitPlanner() {}

    public record Unit(long startMs, long endMs, String text, boolean hardBoundaryBefore) {
        public Unit(long startMs, long endMs, String text) {
            this(startMs, endMs, text, false);
        }

        public Unit {
            if (endMs < startMs) endMs = startMs;
            text = normalize(text);
        }

        public long durationMs() {
            return Math.max(0L, endMs - startMs);
        }
    }

    public static List<Unit> coalesce(List<Unit> input) {
        List<Unit> work = new ArrayList<>();
        if (input == null) return work;
        for (Unit unit : input) {
            if (unit == null || unit.text().isEmpty()) continue;
            work.add(unit);
        }
        if (work.size() < 2) return work;

        // If a short cue is followed by genuine silence, first borrow that otherwise-unused time
        // instead of joining text across the pause. This is safe even before a speaker boundary:
        // only silence is borrowed; the next speaker's text/timestamp is never crossed.
        for (int i = 0; i + 1 < work.size(); i++) {
            Unit cur = work.get(i);
            if (cur.durationMs() >= MIN_UNIT_MS) continue;
            Unit next = work.get(i + 1);
            long gap = next.startMs() - cur.endMs();
            if (gap <= 0) continue;
            long need = MIN_UNIT_MS - cur.durationMs();
            long extension = Math.min(need, gap);
            if (extension > 0) {
                work.set(i, new Unit(cur.startMs(), cur.endMs() + extension,
                        cur.text(), cur.hardBoundaryBefore()));
            }
        }

        // Merge remaining tiny units with the least-disruptive adjacent phrase. Punctuation stays in
        // the text, so Edge SSML still produces the original comma/sentence pause inside the unit.
        // Explicit speaker turns are never crossed even if that leaves a sub-floor unit intact.
        for (int guard = 0; guard < 256; guard++) {
            int shortAt = firstMergeableShort(work);
            if (shortAt < 0) break;

            int left = shortAt - 1;
            int right = shortAt;
            boolean canLeft = left >= 0 && canMerge(work.get(left), work.get(shortAt));
            boolean canRight = shortAt + 1 < work.size()
                    && canMerge(work.get(shortAt), work.get(shortAt + 1));
            if (!canLeft && !canRight) break;

            int mergeAt;
            if (canLeft && canRight) {
                long leftCost = mergeCost(work.get(left), work.get(shortAt));
                long rightCost = mergeCost(work.get(shortAt), work.get(shortAt + 1));
                mergeAt = leftCost <= rightCost ? left : right;
            } else {
                mergeAt = canLeft ? left : right;
            }
            mergeAt(work, mergeAt);
        }
        return work;
    }

    private static int firstMergeableShort(List<Unit> work) {
        for (int i = 0; i < work.size(); i++) {
            if (work.get(i).durationMs() >= MIN_UNIT_MS) continue;
            boolean left = i > 0 && canMerge(work.get(i - 1), work.get(i));
            boolean right = i + 1 < work.size() && canMerge(work.get(i), work.get(i + 1));
            if (left || right) return i;
        }
        return -1;
    }

    private static boolean canMerge(Unit a, Unit b) {
        // b.hardBoundaryBefore means b starts a new explicit speaker turn.
        if (b.hardBoundaryBefore()) return false;
        long gap = b.startMs() - a.endMs();
        if (gap > MAX_JOIN_GAP_MS) return false;
        long start = Math.min(a.startMs(), b.startMs());
        long end = Math.max(a.endMs(), b.endMs());
        if (end - start > MAX_UNIT_MS) return false;
        return combinedText(a, b).length() <= MAX_UNIT_CHARS;
    }

    private static long mergeCost(Unit a, Unit b) {
        long start = Math.min(a.startMs(), b.startMs());
        long end = Math.max(a.endMs(), b.endMs());
        long durationPenalty = Math.abs((end - start) - 4_200L);
        long charPenalty = Math.max(0, combinedText(a, b).length() - 90) * 20L;
        return durationPenalty + charPenalty;
    }

    private static void mergeAt(List<Unit> work, int left) {
        Unit a = work.get(left);
        Unit b = work.get(left + 1);
        work.set(left, new Unit(
                Math.min(a.startMs(), b.startMs()),
                Math.max(a.endMs(), b.endMs()),
                combinedText(a, b),
                a.hardBoundaryBefore()));
        work.remove(left + 1);
    }

    private static String combinedText(Unit a, Unit b) {
        return normalize(a.text() + " " + b.text());
    }

    private static String normalize(String text) {
        return text == null ? "" : text.trim().replaceAll("\\s+", " ");
    }
}
