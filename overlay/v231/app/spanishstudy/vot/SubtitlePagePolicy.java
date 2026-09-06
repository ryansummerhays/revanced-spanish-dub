package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Display-only subtitle cleanup and conversational pagination.
 * Never changes translation input, Morphe batching, translated text, or TTS text.
 */
public final class SubtitlePagePolicy {
    public static final int TARGET_WORDS = 11;
    public static final int TARGET_CHARS = 76;
    public static final int MIN_PAGE_WORDS = 5;
    public static final int MAX_PAGE_WORDS = 16;
    public static final int HARD_MAX_CHARS = 104;

    private static final Set<String> WEAK_END_WORDS = new HashSet<>(List.of(
            "a", "al", "ante", "bajo", "con", "contra", "de", "del", "desde", "durante", "en",
            "entre", "hacia", "hasta", "para", "por", "según", "sin", "sobre", "tras", "y", "o",
            "que", "pero", "porque", "si", "como",
            "a", "an", "the", "and", "or", "but", "of", "to", "for", "with", "in", "on", "at",
            "from", "by", "that", "because", "if", "as"
    ));

    public static final class Page {
        public final String text;
        public final int weight;

        Page(String text, int weight) {
            this.text = text;
            this.weight = Math.max(1, weight);
        }
    }

    private SubtitlePagePolicy() {}

    /** Conservative presentation cleanup for caption-join spacing mistakes. */
    public static String cleanDisplayText(String raw) {
        if (raw == null || raw.isBlank()) return "";
        String text = raw.replace('\u00a0', ' ')
                .replace('\n', ' ')
                .replace('\r', ' ')
                .replace('\t', ' ')
                .replaceAll("\\s+", " ")
                .trim();

        text = text.replaceAll("\\s+([,.;:!?%])", "$1");
        text = text.replaceAll("([\\(\\[\\{¿¡])\\s+", "$1");
        text = text.replaceAll("\\s+([\\)\\]\\}])", "$1");
        text = text.replaceAll("(?<=\\p{L})\\s*['’]\\s*(?=\\p{L})", "'");
        text = text.replaceAll("([,;:!?])(?=[\\p{L}\\p{N}¿¡])", "$1 ");
        text = text.replaceAll("([.!?])(?=[A-ZÁÉÍÓÚÜÑ¿¡])", "$1 ");
        return text.replaceAll("\\s+", " ").trim();
    }

    /**
     * Build readable cards by scoring nearby break points instead of breaking at every short
     * sentence. Strongly prefers sentence/clause boundaries near a comfortable reading size and
     * avoids ending a card on prepositions/conjunctions when another natural break is nearby.
     */
    public static List<Page> paginate(String raw) {
        String text = cleanDisplayText(raw);
        if (text.isBlank()) return Collections.emptyList();
        String[] words = text.split(" ");
        ArrayList<Page> pages = new ArrayList<>();
        int start = 0;

        while (start < words.length) {
            int remaining = words.length - start;
            if (remaining <= MAX_PAGE_WORDS && joinedLength(words, start, words.length) <= HARD_MAX_CHARS) {
                addPage(pages, join(words, start, words.length));
                break;
            }

            int maxEnd = Math.min(words.length, start + MAX_PAGE_WORDS);
            int bestEnd = -1;
            double bestScore = Double.POSITIVE_INFINITY;
            for (int end = start + 1; end <= maxEnd; end++) {
                int pageWords = end - start;
                int left = words.length - end;
                if (left > 0 && left < MIN_PAGE_WORDS) continue;

                int chars = joinedLength(words, start, end);
                double score = Math.abs(pageWords - TARGET_WORDS) * 4.0
                        + Math.abs(chars - TARGET_CHARS) * 0.14;
                if (pageWords < MIN_PAGE_WORDS) score += (MIN_PAGE_WORDS - pageWords) * 18.0;
                if (chars > HARD_MAX_CHARS) score += (chars - HARD_MAX_CHARS) * 2.4;

                String last = words[end - 1];
                if (endsSentence(last)) score -= 24.0;
                else if (endsClause(last)) score -= 10.0;
                if (weakEnd(last)) score += 22.0;
                if (end < words.length && weakStart(words[end])) score += 8.0;

                if (score < bestScore) {
                    bestScore = score;
                    bestEnd = end;
                }
            }

            if (bestEnd <= start) {
                bestEnd = Math.min(words.length, start + TARGET_WORDS);
                if (words.length - bestEnd > 0 && words.length - bestEnd < MIN_PAGE_WORDS) {
                    bestEnd = Math.max(start + 1, words.length - MIN_PAGE_WORDS);
                }
            }
            addPage(pages, join(words, start, bestEnd));
            start = bestEnd;
        }

        rebalanceTinyTail(pages);
        return pages;
    }

    /** Progress is 0..1 through the audible/source window; page timing is weighted by speech text. */
    public static int pageIndex(List<Page> pages, double progress) {
        if (pages == null || pages.isEmpty()) return -1;
        if (pages.size() == 1) return 0;
        double p = Math.max(0.0, Math.min(0.999999, progress));
        int total = 0;
        for (Page page : pages) total += page.weight;
        double target = p * total;
        int cumulative = 0;
        for (int i = 0; i < pages.size(); i++) {
            cumulative += pages.get(i).weight;
            if (target < cumulative) return i;
        }
        return pages.size() - 1;
    }

    public static double progress(long timeMs, long startMs, long endMs) {
        if (endMs <= startMs) return 0.0;
        return Math.max(0.0, Math.min(1.0,
                (timeMs - startMs) / (double) (endMs - startMs)));
    }

    /** Map elapsed playback through a partially-consumed TTS segment. */
    public static double ttsProgress(long timeMs, long startMs, long endMs, double startProgress) {
        double base = Math.max(0.0, Math.min(1.0, startProgress));
        double elapsed = progress(timeMs, startMs, endMs);
        return base + (1.0 - base) * elapsed;
    }

    public static double startProgress(long totalSpeechMs, long remainingSpeechMs) {
        if (totalSpeechMs <= 0L) return 0.0;
        long remaining = Math.max(0L, Math.min(totalSpeechMs, remainingSpeechMs));
        return 1.0 - (remaining / (double) totalSpeechMs);
    }

    static int speechWeight(String text) {
        int weight = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isLetterOrDigit(c)) weight++;
        }
        return Math.max(1, weight);
    }

    private static void addPage(List<Page> pages, String raw) {
        String text = raw.trim();
        if (!text.isEmpty()) pages.add(new Page(text, speechWeight(text)));
    }

    private static boolean endsSentence(String token) {
        String t = token.toLowerCase(Locale.ROOT);
        return t.matches(".*[.!?…][\\\"'”’)]*$");
    }

    private static boolean endsClause(String token) {
        return token.matches(".*[,;:][\\\"'”’)]*$");
    }

    private static boolean weakEnd(String token) {
        String t = token.toLowerCase(Locale.ROOT).replaceAll("[^\\p{L}]", "");
        return WEAK_END_WORDS.contains(t);
    }

    private static boolean weakStart(String token) {
        String t = token.toLowerCase(Locale.ROOT).replaceAll("[^\\p{L}]", "");
        return t.equals("y") || t.equals("o") || t.equals("pero") || t.equals("porque")
                || t.equals("and") || t.equals("or") || t.equals("but") || t.equals("because");
    }

    private static int joinedLength(String[] words, int start, int end) {
        int n = 0;
        for (int i = start; i < end; i++) n += words[i].length() + (i == start ? 0 : 1);
        return n;
    }

    private static String join(String[] words, int start, int end) {
        StringBuilder b = new StringBuilder();
        for (int i = start; i < end; i++) {
            if (b.length() > 0) b.append(' ');
            b.append(words[i]);
        }
        return b.toString();
    }

    /** Avoid a final flash-card when a slightly fuller prior card reads more naturally. */
    private static void rebalanceTinyTail(ArrayList<Page> pages) {
        if (pages.size() < 2) return;
        Page tail = pages.get(pages.size() - 1);
        int tailWords = tail.text.split(" ").length;
        if (tailWords >= MIN_PAGE_WORDS) return;
        Page prior = pages.get(pages.size() - 2);
        String joined = prior.text + " " + tail.text;
        if (joined.length() <= HARD_MAX_CHARS + 14
                && joined.split(" ").length <= MAX_PAGE_WORDS + 2) {
            pages.set(pages.size() - 2, new Page(joined, speechWeight(joined)));
            pages.remove(pages.size() - 1);
        }
    }
}
