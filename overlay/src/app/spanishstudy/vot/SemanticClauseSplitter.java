package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/**
 * Splits source subtitle text into natural spoken phrase units.
 *
 * Boundaries are meaning/prosody first. We never cut at an arbitrary width and we never invent a
 * pause just because a conjunction such as because/that/which appears. Terminal punctuation is the
 * strongest boundary, followed by semicolon/colon/dash and then comma. Very long events may search
 * the entire event for a trustworthy punctuation boundary rather than giving up after the first
 * ~80 characters; this prevents multi-sentence ASR captions from becoming giant clipped subtitles.
 */
public final class SemanticClauseSplitter {
    public static final int TARGET_CHARS = 42;
    public static final int SOFT_MAX_CHARS = 48;
    private static final int MIN_PHRASE_CHARS = 12;

    private SemanticClauseSplitter() {}

    public static List<String> split(String raw) {
        String text = normalize(raw);
        List<String> out = new ArrayList<>();
        if (text.isEmpty()) return out;
        splitRecursive(text, out);
        return out;
    }

    private static void splitRecursive(String text, List<String> out) {
        text = normalize(text);
        if (text.isEmpty()) return;
        if (text.length() <= SOFT_MAX_CHARS) {
            out.add(text);
            return;
        }

        int cut = findNaturalPunctuationCut(text);
        if (cut <= 0 || cut >= text.length()) {
            // No trustworthy pause cue. Keep the whole spoken thought rather than chopping the TTS
            // at an arbitrary character count; the subtitle renderer has an emergency wrap path.
            out.add(text);
            return;
        }

        String head = text.substring(0, cut).trim();
        String tail = text.substring(cut).trim();
        if (head.length() < MIN_PHRASE_CHARS || tail.length() < MIN_PHRASE_CHARS) {
            out.add(text);
            return;
        }

        // Recurse into both halves. This matters for captions that contain several complete
        // sentences: an early implementation split only the tail and could leave a 120+ character
        // first sentence untouched even though it contained additional punctuation.
        splitRecursive(head, out);
        splitRecursive(tail, out);
    }

    private static int findNaturalPunctuationCut(String text) {
        final int max = text.length() - MIN_PHRASE_CHARS;
        if (max <= MIN_PHRASE_CHARS) return -1;

        // First priority: a genuine sentence boundary anywhere in the event. Choose the sentence
        // end nearest the preferred readable length, but do not ignore one merely because it lies
        // beyond an old fixed search window.
        int terminal = bestBoundary(text, max, 3);
        if (terminal > 0) return terminal;

        // Then strong mid-sentence pauses, then commas. These are still preferable to arbitrary
        // width splitting, but only when both sides remain meaningful-sized phrases.
        int strong = bestBoundary(text, max, 2);
        if (strong > 0) return strong;
        return bestBoundary(text, max, 1);
    }

    /** kind: 3 terminal, 2 semicolon/colon/dash, 1 comma. */
    private static int bestBoundary(String text, int max, int kind) {
        int best = -1;
        int bestDistance = Integer.MAX_VALUE;
        for (int i = MIN_PHRASE_CHARS; i <= max; i++) {
            char c = text.charAt(i - 1);
            boolean matches;
            if (kind == 3) matches = c == '.' || c == '?' || c == '!' || c == '…';
            else if (kind == 2) matches = c == ';' || c == ':' || c == '—' || c == '–';
            else matches = c == ',';
            if (!matches || !isSafeTail(text, i)) continue;

            int distance = Math.abs(i - TARGET_CHARS);
            if (distance < bestDistance) {
                bestDistance = distance;
                best = i;
            }
        }
        return best;
    }

    private static boolean isSafeTail(String text, int cut) {
        return cut >= MIN_PHRASE_CHARS && text.length() - cut >= MIN_PHRASE_CHARS;
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim().replaceAll("\\s+", " ");
    }
}
