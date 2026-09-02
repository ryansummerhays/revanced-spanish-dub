package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/**
 * Splits source subtitle text into short, meaning-preserving clauses.
 *
 * The goal is not word-count equality between languages. Instead, each source slot should contain
 * one compact sentence/clause that can be translated 1:1 and normally fit on one subtitle line in
 * both languages. Short sentences stay whole; longer sentences split at natural clause boundaries.
 */
public final class SemanticClauseSplitter {
    // Tuned for one-line bilingual study subtitles. Spanish often expands relative to English, so
    // keep the English source slot comfortably shorter than a normal two-line caption.
    private static final int TARGET_CHARS = 46;
    private static final int SOFT_MAX_CHARS = 54;
    private static final int HARD_MAX_CHARS = 68;
    private static final int MIN_CLAUSE_CHARS = 16;

    private static final String[] CONJUNCTIONS = {
            " and ", " but ", " because ", " so ", " while ", " although ", " though ",
            " when ", " if ", " which ", " who ", " that ", " then ", " yet "
    };

    private SemanticClauseSplitter() {}

    public static List<String> split(String raw) {
        String text = normalize(raw);
        List<String> out = new ArrayList<>();
        if (text.isEmpty()) return out;

        String remaining = text;
        while (remaining.length() > SOFT_MAX_CHARS) {
            int cut = findSemanticCut(remaining);
            if (cut <= 0 || cut >= remaining.length()) {
                if (remaining.length() <= HARD_MAX_CHARS) break;
                cut = nearestSpace(remaining, TARGET_CHARS, HARD_MAX_CHARS);
            }
            if (cut <= 0 || cut >= remaining.length()) break;

            String head = remaining.substring(0, cut).trim();
            String tail = remaining.substring(cut).trim();
            if (head.length() < MIN_CLAUSE_CHARS || tail.length() < MIN_CLAUSE_CHARS) break;
            out.add(head);
            remaining = tail;
        }

        if (!remaining.isEmpty()) out.add(remaining);
        return out;
    }

    private static int findSemanticCut(String text) {
        int max = Math.min(HARD_MAX_CHARS, text.length() - MIN_CLAUSE_CHARS);
        int min = MIN_CLAUSE_CHARS;
        if (max <= min) return -1;

        int best = -1;
        int bestScore = Integer.MIN_VALUE;

        for (int i = min; i <= max; i++) {
            char c = text.charAt(i - 1);
            int semantic = 0;
            if (c == '.' || c == '?' || c == '!') semantic = 120;
            else if (c == ';' || c == ':') semantic = 105;
            else if (c == ',' || c == '—' || c == '–') semantic = 90;
            if (semantic > 0 && isSafeTail(text, i)) {
                int score = semantic - Math.abs(i - TARGET_CHARS);
                if (score > bestScore) {
                    bestScore = score;
                    best = i;
                }
            }
        }

        String lower = text.toLowerCase();
        for (String conjunction : CONJUNCTIONS) {
            int from = Math.max(0, min - conjunction.length());
            while (true) {
                int at = lower.indexOf(conjunction, from);
                if (at < 0 || at > max) break;
                int cut = at;
                if (cut >= min && cut <= max && isSafeTail(text, cut)) {
                    int score = 68 - Math.abs(cut - TARGET_CHARS);
                    if (score > bestScore) {
                        bestScore = score;
                        best = cut;
                    }
                }
                from = at + conjunction.length();
            }
        }

        return best;
    }

    private static boolean isSafeTail(String text, int cut) {
        return cut >= MIN_CLAUSE_CHARS && text.length() - cut >= MIN_CLAUSE_CHARS;
    }

    private static int nearestSpace(String text, int target, int hardMax) {
        int max = Math.min(hardMax, text.length() - MIN_CLAUSE_CHARS);
        if (max <= MIN_CLAUSE_CHARS) return -1;
        target = Math.max(MIN_CLAUSE_CHARS, Math.min(target, max));

        for (int delta = 0; delta <= max; delta++) {
            int left = target - delta;
            if (left >= MIN_CLAUSE_CHARS && Character.isWhitespace(text.charAt(left))) return left;
            int right = target + delta;
            if (right <= max && Character.isWhitespace(text.charAt(right))) return right;
        }
        return -1;
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim().replaceAll("\\s+", " ");
    }
}
