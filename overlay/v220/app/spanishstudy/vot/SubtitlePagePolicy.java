package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/** Pure display-only subtitle cleanup and pagination. Never mutates translation or TTS text. */
public final class SubtitlePagePolicy {
    public static final int TARGET_WORDS = 10;
    public static final int TARGET_CHARS = 68;
    public static final int MIN_BREAK_WORDS = 5;
    public static final int MIN_SENTENCE_WORDS = 3;

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

    public static List<Page> paginate(String raw) {
        String text = cleanDisplayText(raw);
        if (text.isBlank()) return Collections.emptyList();
        String[] tokens = text.split(" ");
        ArrayList<Page> pages = new ArrayList<>();
        StringBuilder current = new StringBuilder();
        int words = 0;

        for (String token : tokens) {
            if (token.isBlank()) continue;
            int prospectiveChars = current.length() + (current.length() == 0 ? 0 : 1) + token.length();
            boolean hardLimit = words >= TARGET_WORDS
                    || (prospectiveChars > TARGET_CHARS && words >= MIN_BREAK_WORDS);
            if (hardLimit && current.length() > 0) {
                addPage(pages, current.toString());
                current.setLength(0);
                words = 0;
            }

            if (current.length() > 0) current.append(' ');
            current.append(token);
            words++;

            boolean sentenceEnd = endsSentence(token);
            boolean clauseEnd = endsClause(token);
            boolean sentenceBreak = sentenceEnd && words >= MIN_SENTENCE_WORDS;
            boolean clauseBreak = clauseEnd && words >= MIN_BREAK_WORDS
                    && (words >= TARGET_WORDS - 2 || current.length() >= TARGET_CHARS - 12);
            if (sentenceBreak || clauseBreak) {
                addPage(pages, current.toString());
                current.setLength(0);
                words = 0;
            }
        }
        if (current.length() > 0) addPage(pages, current.toString());
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

    private static void addPage(List<Page> pages, String raw) {
        String text = raw.trim();
        if (text.isEmpty()) return;
        pages.add(new Page(text, speechWeight(text)));
    }

    private static int speechWeight(String text) {
        int weight = 0;
        for (int i = 0; i < text.length(); i++) {
            char c = text.charAt(i);
            if (Character.isLetterOrDigit(c)) weight++;
        }
        return Math.max(1, weight);
    }

    private static boolean endsSentence(String token) {
        String t = token.toLowerCase(Locale.ROOT);
        return t.endsWith(".") || t.endsWith("!") || t.endsWith("?")
                || t.endsWith(".\"") || t.endsWith("!\"") || t.endsWith("?\"");
    }

    private static boolean endsClause(String token) {
        return token.endsWith(",") || token.endsWith(";") || token.endsWith(":");
    }

    /** Avoid flashing a one- or two-word final card when it can fit on the prior page. */
    private static void rebalanceTinyTail(ArrayList<Page> pages) {
        if (pages.size() < 2) return;
        Page tail = pages.get(pages.size() - 1);
        int tailWords = tail.text.split(" ").length;
        Page prior = pages.get(pages.size() - 2);
        String joined = prior.text + " " + tail.text;
        if (tailWords <= 2 && joined.length() <= TARGET_CHARS + 12
                && joined.split(" ").length <= TARGET_WORDS + 2) {
            pages.set(pages.size() - 2, new Page(joined, speechWeight(joined)));
            pages.remove(pages.size() - 1);
        }
    }
}
