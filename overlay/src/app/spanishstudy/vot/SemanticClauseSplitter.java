package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Splits source subtitle text into natural spoken phrase units.
 *
 * v2.11 makes timing the strongest local signal when it is available. YouTube JSON3 inner-word
 * timing can reveal a real pause even when ASR emitted a run-on with no punctuation. Strong pauses
 * may restore a period; medium pauses may restore a comma. Existing punctuation is never replaced.
 * When timing is unavailable, a tiny set of high-confidence discourse markers (but/so/however/...)
 * may receive a comma in a genuinely long run-on, but weak conjunctions such as because/that/which
 * still do not invent a boundary on their own.
 */
public final class SemanticClauseSplitter {
    public static final int TARGET_CHARS = 42;
    public static final int SOFT_MAX_CHARS = 48;
    private static final int MIN_PHRASE_CHARS = 12;
    private static final int MIN_TIMED_SIDE_WORDS = 2;
    private static final long STRONG_PAUSE_MS = 480L;
    private static final long MEDIUM_PAUSE_MS = 240L;

    private static final Pattern WORD = Pattern.compile(
            "[\\p{L}\\p{N}]+(?:['’\\-][\\p{L}\\p{N}]+)*");

    private static final Set<String> DISCOURSE_OPENERS = Set.of(
            "but", "so", "then", "however", "therefore", "instead", "meanwhile",
            "although", "though", "yet");

    private SemanticClauseSplitter() {}

    public static List<String> split(String raw) {
        return splitPrepared(normalize(raw));
    }

    /**
     * Timing-aware variant. {@code interWordGapsMs[i]} is the measured silence between lexical word
     * i and i+1. A null/mismatched array safely falls back to text-only behavior.
     */
    public static List<String> split(String raw, long[] interWordGapsMs) {
        String text = restorePunctuation(raw, interWordGapsMs);
        return splitPrepared(text);
    }

    /**
     * Conservatively restores punctuation without changing lexical words.
     * This is deliberately not a general grammar model; it only marks pause evidence strong enough
     * to improve TTS phrasing and subtitle segmentation.
     */
    public static String restorePunctuation(String raw, long[] interWordGapsMs) {
        String text = normalize(raw);
        if (text.isEmpty()) return text;

        List<WordSpan> words = wordSpans(text);
        if (words.size() < 2) return text;

        boolean timingUsable = interWordGapsMs != null
                && interWordGapsMs.length == words.size() - 1;
        if (!timingUsable) return insertConservativeDiscourseComma(text, words);

        StringBuilder out = new StringBuilder(text.length() + 8);
        int cursor = 0;
        boolean inserted = false;
        for (int i = 0; i + 1 < words.size(); i++) {
            WordSpan left = words.get(i);
            WordSpan right = words.get(i + 1);
            out.append(text, cursor, left.end);

            String between = text.substring(left.end, right.start);
            if (!containsPausePunctuation(between)) {
                long gapMs = Math.max(0L, interWordGapsMs[i]);
                int leftWords = i + 1;
                int rightWords = words.size() - leftWords;
                String next = right.token.toLowerCase(Locale.ROOT);

                if (gapMs >= STRONG_PAUSE_MS
                        && leftWords >= MIN_TIMED_SIDE_WORDS
                        && rightWords >= MIN_TIMED_SIDE_WORDS) {
                    out.append('.');
                    inserted = true;
                } else if (gapMs >= MEDIUM_PAUSE_MS
                        && leftWords >= 3 && rightWords >= 2
                        && (DISCOURSE_OPENERS.contains(next)
                            || gapMs >= 330L
                            || leftWords >= 7)) {
                    out.append(',');
                    inserted = true;
                }
            }
            out.append(between);
            cursor = right.start;
        }
        out.append(text.substring(cursor));

        String restored = normalize(out.toString());
        // If timing had no useful pause cue, still allow one very conservative discourse comma in
        // a long run-on. This never treats because/that/which as a sufficient pause by themselves.
        return inserted ? restored : insertConservativeDiscourseComma(restored, wordSpans(restored));
    }

    private static List<String> splitPrepared(String text) {
        List<String> out = new ArrayList<>();
        if (text == null || text.isEmpty()) return out;
        splitRecursive(text, out);
        return out;
    }

    private static void splitRecursive(String text, List<String> out) {
        text = normalize(text);
        if (text.isEmpty()) return;

        // Always respect a real/internal sentence boundary, even when two spoken sentences happen
        // to fit under the subtitle width target. This also makes restored strong-pause periods act
        // as actual phrase boundaries rather than cosmetic punctuation.
        int terminal = bestBoundary(text, text.length() - MIN_PHRASE_CHARS, 3);
        if (terminal > 0 && splitAt(text, terminal, out)) return;

        if (text.length() <= SOFT_MAX_CHARS) {
            out.add(text);
            return;
        }

        int cut = findNaturalPunctuationCut(text);
        if (cut <= 0 || cut >= text.length() || !splitAt(text, cut, out)) {
            // No trustworthy pause cue. Keep the whole spoken thought rather than chopping the TTS
            // at an arbitrary character count; the subtitle renderer has an emergency wrap path.
            out.add(text);
        }
    }

    private static boolean splitAt(String text, int cut, List<String> out) {
        if (cut <= 0 || cut >= text.length()) return false;
        String head = text.substring(0, cut).trim();
        String tail = text.substring(cut).trim();
        if (head.length() < MIN_PHRASE_CHARS || tail.length() < MIN_PHRASE_CHARS) return false;
        splitRecursive(head, out);
        splitRecursive(tail, out);
        return true;
    }

    private static int findNaturalPunctuationCut(String text) {
        final int max = text.length() - MIN_PHRASE_CHARS;
        if (max <= MIN_PHRASE_CHARS) return -1;

        int terminal = bestBoundary(text, max, 3);
        if (terminal > 0) return terminal;
        int strong = bestBoundary(text, max, 2);
        if (strong > 0) return strong;
        return bestBoundary(text, max, 1);
    }

    /** kind: 3 terminal, 2 semicolon/colon/dash, 1 comma. */
    private static int bestBoundary(String text, int max, int kind) {
        if (max <= MIN_PHRASE_CHARS) return -1;
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

    private static String insertConservativeDiscourseComma(String text, List<WordSpan> words) {
        if (text.length() < 78 || words.size() < 8) return text;

        int bestBoundary = -1;
        int bestDistance = Integer.MAX_VALUE;
        for (int i = 3; i + 3 < words.size(); i++) {
            WordSpan next = words.get(i);
            if (!DISCOURSE_OPENERS.contains(next.token.toLowerCase(Locale.ROOT))) continue;
            WordSpan previous = words.get(i - 1);
            String between = text.substring(previous.end, next.start);
            if (containsPausePunctuation(between)) continue;

            int distance = Math.abs(previous.end - TARGET_CHARS);
            if (distance < bestDistance) {
                bestDistance = distance;
                bestBoundary = previous.end;
            }
        }
        if (bestBoundary < 0) return text;
        return normalize(text.substring(0, bestBoundary) + "," + text.substring(bestBoundary));
    }

    private static boolean containsPausePunctuation(String between) {
        for (int i = 0; i < between.length(); i++) {
            char c = between.charAt(i);
            if (c == '.' || c == '?' || c == '!' || c == '…' || c == ',' || c == ';'
                    || c == ':' || c == '—' || c == '–') return true;
        }
        return false;
    }

    private static List<WordSpan> wordSpans(String text) {
        List<WordSpan> out = new ArrayList<>();
        Matcher matcher = WORD.matcher(text);
        while (matcher.find()) out.add(new WordSpan(matcher.group(), matcher.start(), matcher.end()));
        return out;
    }

    private static boolean isSafeTail(String text, int cut) {
        return cut >= MIN_PHRASE_CHARS && text.length() - cut >= MIN_PHRASE_CHARS;
    }

    private static String normalize(String raw) {
        return raw == null ? "" : raw.trim().replaceAll("\\s+", " ");
    }

    private record WordSpan(String token, int start, int end) {}
}
