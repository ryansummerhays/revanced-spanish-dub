package app.spanishstudy.vot;

import java.util.Locale;

/**
 * Display-only two-line formatter for Spanish Study subtitle cards.
 *
 * The target follows common timed-text practice: about 42 Latin characters per line, no text
 * deletion, syntactic/punctuation-aware breaks, and a slight preference for a bottom-heavy shape.
 * This never changes translation or TTS text.
 */
public final class SubtitleLinePolicy {
    public static final int TARGET_CHARS_PER_LINE = 42;
    public static final int SOFT_MAX_CHARS_PER_LINE = 48;
    public static final int MAX_LINES = 2;

    private SubtitleLinePolicy() {}

    public static String format(String raw) {
        String text = SubtitlePagePolicy.cleanDisplayText(raw);
        if (text.isBlank() || text.length() <= TARGET_CHARS_PER_LINE) return text;

        String[] words = text.split(" ");
        if (words.length < 2) return text;

        int best = -1;
        double bestScore = Double.POSITIVE_INFINITY;
        for (int split = 1; split < words.length; split++) {
            String top = join(words, 0, split);
            String bottom = join(words, split, words.length);
            int topLen = top.length();
            int bottomLen = bottom.length();
            int topWords = split;
            int bottomWords = words.length - split;

            double score = Math.abs(topLen - TARGET_CHARS_PER_LINE)
                    + Math.abs(bottomLen - TARGET_CHARS_PER_LINE);

            // Going well past the conventional line width is possible for unusually long words,
            // but should be strongly disfavored when a cleaner break exists.
            if (topLen > SOFT_MAX_CHARS_PER_LINE)
                score += (topLen - SOFT_MAX_CHARS_PER_LINE) * 9.0;
            if (bottomLen > SOFT_MAX_CHARS_PER_LINE)
                score += (bottomLen - SOFT_MAX_CHARS_PER_LINE) * 9.0;

            // Avoid orphan-like one/two-word top lines.
            if (topWords <= 2) score += 35.0;
            if (bottomWords <= 1) score += 18.0;

            // Bottom-positioned subtitles are normally easier to scan as a bottom-heavy pyramid.
            if (bottomLen < topLen) score += (topLen - bottomLen) * 0.35;

            String previous = words[split - 1];
            String next = words[split].toLowerCase(Locale.ROOT);
            if (endsSentence(previous)) score -= 18.0;
            else if (endsClause(previous)) score -= 9.0;
            if (isPreferredLead(next)) score -= 6.0;

            if (score < bestScore) {
                bestScore = score;
                best = split;
            }
        }

        if (best <= 0) return text;
        return join(words, 0, best) + "\n" + join(words, best, words.length);
    }

    public static int lineCount(String formatted) {
        if (formatted == null || formatted.isBlank()) return 0;
        return formatted.indexOf('\n') >= 0 ? 2 : 1;
    }

    public static int maxLineLength(String formatted) {
        if (formatted == null || formatted.isBlank()) return 0;
        int max = 0;
        for (String line : formatted.split("\\n", -1)) max = Math.max(max, line.length());
        return max;
    }

    public static String removeFormatting(String formatted) {
        if (formatted == null) return "";
        return formatted.replace('\n', ' ').replaceAll("\\s+", " ").trim();
    }

    private static boolean endsSentence(String word) {
        return word.matches(".*[.!?][\\\"'”’)]*$");
    }

    private static boolean endsClause(String word) {
        return word.matches(".*[,;:][\\\"'”’)]*$");
    }

    private static boolean isPreferredLead(String word) {
        switch (word) {
            case "and": case "but": case "or": case "so": case "because": case "if":
            case "when": case "while": case "that": case "which": case "who": case "with":
            case "without": case "from": case "for": case "to": case "of": case "in":
            case "on": case "at": case "by": case "y": case "o": case "pero": case "porque":
            case "si": case "cuando": case "que": case "con": case "sin": case "de":
            case "del": case "para": case "por": case "en": case "a":
                return true;
            default:
                return false;
        }
    }

    private static String join(String[] words, int start, int end) {
        StringBuilder out = new StringBuilder();
        for (int i = start; i < end; i++) {
            if (out.length() > 0) out.append(' ');
            out.append(words[i]);
        }
        return out.toString();
    }
}
