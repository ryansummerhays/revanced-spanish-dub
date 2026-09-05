package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Splits Spanish and English into the same number of non-empty display cards. */
public final class BilingualCardPolicy {
    private BilingualCardPolicy() {}

    public static final class PairPages {
        public final List<String> spanish;
        public final List<String> english;
        PairPages(List<String> spanish, List<String> english) {
            this.spanish = spanish;
            this.english = english;
        }
        public int size() { return Math.min(spanish.size(), english.size()); }
    }

    public static PairPages build(String spanishRaw, String englishRaw) {
        String es = SubtitlePagePolicy.cleanDisplayText(spanishRaw);
        String en = SubtitlePagePolicy.cleanDisplayText(englishRaw);
        if (es.isBlank() || en.isBlank()) return new PairPages(Collections.emptyList(), Collections.emptyList());

        int preferred = Math.max(SubtitlePagePolicy.paginate(es).size(), SubtitlePagePolicy.paginate(en).size());
        int maxUseful = Math.min(wordCount(es), wordCount(en));
        int count = Math.max(1, Math.min(preferred, maxUseful));
        return new PairPages(splitExact(es, count), splitExact(en, count));
    }

    public static int pairIndex(int count, double progress) {
        if (count <= 0) return -1;
        if (count == 1) return 0;
        double p = Math.max(0.0, Math.min(0.999999, progress));
        return Math.min(count - 1, (int) Math.floor(p * count));
    }

    static List<String> splitExact(String raw, int requestedCount) {
        String text = SubtitlePagePolicy.cleanDisplayText(raw);
        if (text.isBlank()) return Collections.emptyList();
        String[] words = text.split(" ");
        int count = Math.max(1, Math.min(requestedCount, words.length));
        if (count == 1) return List.of(text);

        int[] weight = new int[words.length];
        int total = 0;
        for (int i = 0; i < words.length; i++) {
            weight[i] = speechWeight(words[i]) + (i == 0 ? 0 : 1);
            total += weight[i];
        }

        ArrayList<String> out = new ArrayList<>(count);
        int start = 0;
        int consumed = 0;
        for (int page = 0; page < count - 1; page++) {
            int pagesLeftAfter = count - page - 1;
            int minEnd = start + 1;
            int maxEnd = words.length - pagesLeftAfter;
            double ideal = total * ((page + 1) / (double) count);
            int bestEnd = minEnd;
            double bestScore = Double.POSITIVE_INFINITY;
            int running = consumed;
            for (int end = start + 1; end <= maxEnd; end++) {
                running += weight[end - 1];
                double score = Math.abs(running - ideal);
                String w = words[end - 1];
                if (endsSentence(w)) score -= Math.max(8.0, total * 0.018);
                else if (endsClause(w)) score -= Math.max(3.0, total * 0.007);
                if (score < bestScore) {
                    bestScore = score;
                    bestEnd = end;
                }
                if (running > ideal + Math.max(20, total / count)) break;
            }
            out.add(join(words, start, bestEnd));
            for (int i = start; i < bestEnd; i++) consumed += weight[i];
            start = bestEnd;
        }
        out.add(join(words, start, words.length));
        return out;
    }

    private static int wordCount(String s) { return s.isBlank() ? 0 : s.split(" ").length; }
    private static int speechWeight(String s) {
        int n = 0;
        for (int i = 0; i < s.length(); i++) if (Character.isLetterOrDigit(s.charAt(i))) n++;
        return Math.max(1, n);
    }
    private static boolean endsSentence(String s) { return s.matches(".*[.!?][\\\"'”’)]*$"); }
    private static boolean endsClause(String s) { return s.matches(".*[,;:][\\\"'”’)]*$"); }
    private static String join(String[] words, int start, int end) {
        StringBuilder b = new StringBuilder();
        for (int i = start; i < end; i++) { if (b.length() > 0) b.append(' '); b.append(words[i]); }
        return b.toString();
    }
}
