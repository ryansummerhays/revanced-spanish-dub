package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/**
 * Splits source subtitle text into natural spoken phrase units.
 *
 * This deliberately does NOT cut at an arbitrary character/word boundary just to make a line
 * shorter. A slightly long one-line subtitle is preferable to making the dub voice stop halfway
 * through a syntactic thought. The preferred boundaries mirror places a human speaker would
 * naturally pause: sentence punctuation first, then semicolon/colon/dash/comma, and only for very
 * long unpunctuated stretches a small set of strong clause conjunctions.
 */
public final class SemanticClauseSplitter {
    public static final int TARGET_CHARS = 42;
    public static final int SOFT_MAX_CHARS = 48;
    public static final int NATURAL_BOUNDARY_SEARCH_MAX = 72;
    private static final int MIN_PHRASE_CHARS = 12;

    private static final String[] STRONG_CONJUNCTIONS = {
            " but ", " because ", " so ", " although ", " though ", " yet ", " while "
    };

    private SemanticClauseSplitter() {}

    public static List<String> split(String raw) {
        String text = normalize(raw);
        List<String> out = new ArrayList<>();
        if (text.isEmpty()) return out;

        String remaining = text;
        while (remaining.length() > SOFT_MAX_CHARS) {
            int cut = findNaturalPunctuationCut(remaining);
            if (cut < 0 && remaining.length() > NATURAL_BOUNDARY_SEARCH_MAX) {
                cut = findStrongConjunctionCut(remaining);
            }

            // No natural pause exists in a sensible window. Keep the phrase whole rather than
            // creating the audible mid-thought stop that arbitrary character/word chunking causes.
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

    private static int findStrongConjunctionCut(String text) {
        String lower = text.toLowerCase();
        int max = Math.min(NATURAL_BOUNDARY_SEARCH_MAX,
                text.length() - MIN_PHRASE_CHARS);
        int best = -1;
        int bestScore = Integer.MIN_VALUE;

        for (String conjunction : STRONG_CONJUNCTIONS) {
            int from = MIN_PHRASE_CHARS;
            while (true) {
                int at = lower.indexOf(conjunction, from);
                if (at < 0 || at > max) break;
                // Cut BEFORE the conjunction so the following phrase begins naturally with
                // "but", "because", etc., exactly as a speaker would after a brief pause.
                if (isSafeTail(text, at)) {
                    int score = 80 - Math.abs(at - TARGET_CHARS);
                    if (score > bestScore) {
                        bestScore = score;
                        best = at;
                    }
                }
                from = at + conjunction.length();
            }
        }

        // "and" is weak and occurs inside many noun/verb phrases. Use it only as a last-resort
        // boundary for a genuinely long stretch with substantial material on both sides.
        if (best < 0 && text.length() > 88) {
            int from = 20;
            while (true) {
                int at = lower.indexOf(" and ", from);
                if (at < 0 || at > max) break;
                if (at >= 20 && text.length() - at >= 20) {
                    int score = 55 - Math.abs(at - TARGET_CHARS);
                    if (score > bestScore) {
                        bestScore = score;
                        best = at;
                    }
                }
                from = at + 5;
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
