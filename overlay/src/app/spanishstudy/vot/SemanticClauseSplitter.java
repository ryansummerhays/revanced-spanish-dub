package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/**
 * Splits source subtitle text into natural spoken phrase units.
 *
 * Text-driven splitting is intentionally conservative: only punctuation that normally corresponds
 * to a real prosodic break may create a new phrase. We do NOT cut merely because a line is wide,
 * and we do NOT guess a pause at conjunctions such as because/that/which. Unpunctuated ASR speech
 * is already segmented upstream from its real caption timing gaps; if no pause signal exists, a
 * slightly longer one-line subtitle is preferable to making TTS stop halfway through a thought.
 */
public final class SemanticClauseSplitter {
    public static final int TARGET_CHARS = 42;
    public static final int SOFT_MAX_CHARS = 48;
    public static final int NATURAL_BOUNDARY_SEARCH_MAX = 78;
    private static final int MIN_PHRASE_CHARS = 12;

    private SemanticClauseSplitter() {}

    public static List<String> split(String raw) {
        String text = normalize(raw);
        List<String> out = new ArrayList<>();
        if (text.isEmpty()) return out;

        String remaining = text;
        while (remaining.length() > SOFT_MAX_CHARS) {
            int cut = findNaturalPunctuationCut(remaining);

            // No trustworthy pause cue: keep the phrase whole. The view may shrink a little to
            // preserve one line, but audio is never chopped at an arbitrary word boundary.
            if (cut <= 0 || cut >= remaining.length()) break;

            String head = remaining.substring(0, cut).trim();
            String tail = remaining.substring(cut).trim();
            if (head.length() < MIN_PHRASE_CHARS || tail.length() < MIN_PHRASE_CHARS) break;
            out.add(head);
            remaining = tail;
        }

        if (!remaining.isEmpty()) out.add(remaining);
        return out;
    }

    private static int findNaturalPunctuationCut(String text) {
        int max = Math.min(NATURAL_BOUNDARY_SEARCH_MAX,
                text.length() - MIN_PHRASE_CHARS);
        if (max <= MIN_PHRASE_CHARS) return -1;

        int best = -1;
        int bestScore = Integer.MIN_VALUE;
        for (int i = MIN_PHRASE_CHARS; i <= max; i++) {
            char c = text.charAt(i - 1);
            int semantic;
            if (c == '.' || c == '?' || c == '!' || c == '…') semantic = 150;
            else if (c == ';' || c == ':') semantic = 135;
            else if (c == '—' || c == '–') semantic = 125;
            else if (c == ',') semantic = 112;
            else continue;

            if (!isSafeTail(text, i)) continue;
            int score = semantic - Math.abs(i - TARGET_CHARS);
            if (score > bestScore) {
                bestScore = score;
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
