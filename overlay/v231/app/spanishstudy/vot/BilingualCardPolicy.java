package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Display-only bilingual alignment. Spanish is the audible master: conversational Spanish page
 * boundaries establish shared progress anchors, and English is cut near those same cumulative
 * content positions. Translation packets and TTS segments remain untouched.
 */
public final class BilingualCardPolicy {
    private BilingualCardPolicy() {}

    public static final class PairPages {
        public final List<String> spanish;
        public final List<String> english;
        private final double[] pageEnds;

        PairPages(List<String> spanish, List<String> english, double[] pageEnds) {
            this.spanish = spanish;
            this.english = english;
            this.pageEnds = pageEnds;
        }

        public int size() { return Math.min(spanish.size(), english.size()); }

        public int index(double progress) {
            int count = size();
            if (count <= 0) return -1;
            if (count == 1) return 0;
            double p = Math.max(0.0, Math.min(0.999999, progress));
            for (int i = 0; i < pageEnds.length && i < count; i++) {
                if (p < pageEnds[i]) return i;
            }
            return count - 1;
        }

        public double endFraction(int index) {
            if (index < 0 || index >= pageEnds.length) return 1.0;
            return pageEnds[index];
        }
    }

    public static PairPages build(String spanishRaw, String englishRaw) {
        String es = SubtitlePagePolicy.cleanDisplayText(spanishRaw);
        String en = SubtitlePagePolicy.cleanDisplayText(englishRaw);
        if (es.isBlank() || en.isBlank()) {
            return new PairPages(Collections.emptyList(), Collections.emptyList(), new double[0]);
        }

        List<SubtitlePagePolicy.Page> naturalEs = SubtitlePagePolicy.paginate(es);
        List<SubtitlePagePolicy.Page> naturalEn = SubtitlePagePolicy.paginate(en);
        int maxUseful = Math.min(wordCount(es), wordCount(en));
        int count = Math.max(1, Math.min(maxUseful, Math.max(naturalEs.size(), naturalEn.size())));
        if (count == 1) {
            return new PairPages(List.of(es), List.of(en), new double[]{1.0});
        }

        double[] targets = sharedTargets(naturalEs, naturalEn, count);
        List<String> spanish = splitNearFractions(es, targets, count);

        // Recalculate from the actual Spanish cuts. MediaPlayer progress is Spanish audio progress,
        // so these are the most faithful transition fractions for both languages.
        double[] pageEnds = cumulativeEnds(spanish);
        double[] englishTargets = new double[Math.max(0, pageEnds.length - 1)];
        for (int i = 0; i < englishTargets.length; i++) englishTargets[i] = pageEnds[i];
        List<String> english = splitNearFractions(en, englishTargets, count);

        // Defensive normalization if an extreme one-word input defeated a requested split.
        int finalCount = Math.min(spanish.size(), english.size());
        if (finalCount <= 0) {
            return new PairPages(Collections.emptyList(), Collections.emptyList(), new double[0]);
        }
        if (finalCount != spanish.size()) spanish = new ArrayList<>(spanish.subList(0, finalCount));
        if (finalCount != english.size()) english = new ArrayList<>(english.subList(0, finalCount));
        pageEnds = cumulativeEnds(spanish);
        return new PairPages(spanish, english, pageEnds);
    }

    /** Retained for older pure tests/callers; v2.31 overlay uses PairPages.index(progress). */
    public static int pairIndex(int count, double progress) {
        if (count <= 0) return -1;
        if (count == 1) return 0;
        double p = Math.max(0.0, Math.min(0.999999, progress));
        return Math.min(count - 1, (int) Math.floor(p * count));
    }

    private static double[] sharedTargets(List<SubtitlePagePolicy.Page> esPages,
                                          List<SubtitlePagePolicy.Page> enPages,
                                          int count) {
        double[] esBounds = naturalBounds(esPages);
        double[] enBounds = naturalBounds(enPages);
        double[] out = new double[count - 1];
        double previous = 0.0;
        for (int i = 1; i < count; i++) {
            double ideal = i / (double) count;
            double es = nearest(esBounds, ideal);
            double en = nearest(enBounds, ideal);

            // Spanish gets the largest vote because its actual TTS audio drives the card clock.
            double target = 0.55 * es + 0.25 * en + 0.20 * ideal;
            double min = previous + 0.06;
            double max = 1.0 - 0.06 * (count - i);
            target = Math.max(min, Math.min(max, target));
            out[i - 1] = target;
            previous = target;
        }
        return out;
    }

    private static double[] naturalBounds(List<SubtitlePagePolicy.Page> pages) {
        if (pages == null || pages.size() <= 1) return new double[0];
        int total = 0;
        for (SubtitlePagePolicy.Page p : pages) total += p.weight;
        double[] bounds = new double[pages.size() - 1];
        int cumulative = 0;
        for (int i = 0; i < pages.size() - 1; i++) {
            cumulative += pages.get(i).weight;
            bounds[i] = cumulative / (double) Math.max(1, total);
        }
        return bounds;
    }

    private static double nearest(double[] values, double target) {
        if (values == null || values.length == 0) return target;
        double best = values[0];
        double distance = Math.abs(best - target);
        for (int i = 1; i < values.length; i++) {
            double d = Math.abs(values[i] - target);
            if (d < distance) {
                distance = d;
                best = values[i];
            }
        }
        return best;
    }

    private static List<String> splitNearFractions(String raw, double[] targets, int requestedCount) {
        String text = SubtitlePagePolicy.cleanDisplayText(raw);
        if (text.isBlank()) return Collections.emptyList();
        String[] words = text.split(" ");
        int count = Math.max(1, Math.min(requestedCount, words.length));
        if (count == 1) return List.of(text);

        int[] weights = new int[words.length];
        int total = 0;
        for (int i = 0; i < words.length; i++) {
            weights[i] = wordWeight(words[i]) + (i == 0 ? 0 : 1);
            total += weights[i];
        }
        int[] prefix = new int[words.length + 1];
        for (int i = 0; i < words.length; i++) prefix[i + 1] = prefix[i] + weights[i];

        ArrayList<String> out = new ArrayList<>(count);
        int start = 0;
        for (int page = 0; page < count - 1; page++) {
            int pagesLeftAfter = count - page - 1;
            int minEnd = start + 1;
            int maxEnd = words.length - pagesLeftAfter;
            double target = page < targets.length ? targets[page] : (page + 1) / (double) count;
            int bestEnd = minEnd;
            double bestScore = Double.POSITIVE_INFINITY;

            for (int end = minEnd; end <= maxEnd; end++) {
                double fraction = prefix[end] / (double) Math.max(1, total);
                double score = Math.abs(fraction - target) * 100.0;
                int localWords = end - start;
                int chars = joinedLength(words, start, end);
                if (localWords < 4) score += (4 - localWords) * 8.0;
                if (chars > SubtitlePagePolicy.HARD_MAX_CHARS + 12) {
                    score += (chars - SubtitlePagePolicy.HARD_MAX_CHARS - 12) * 0.8;
                }
                String last = words[end - 1];
                if (last.matches(".*[.!?…][\\\"'”’)]*$")) score -= 6.0;
                else if (last.matches(".*[,;:][\\\"'”’)]*$")) score -= 2.5;
                if (weakBoundaryWord(last)) score += 5.0;
                if (score < bestScore) {
                    bestScore = score;
                    bestEnd = end;
                }
            }

            out.add(join(words, start, bestEnd));
            start = bestEnd;
        }
        out.add(join(words, start, words.length));
        return out;
    }

    private static double[] cumulativeEnds(List<String> pages) {
        if (pages == null || pages.isEmpty()) return new double[0];
        int total = 0;
        int[] weights = new int[pages.size()];
        for (int i = 0; i < pages.size(); i++) {
            weights[i] = SubtitlePagePolicy.speechWeight(pages.get(i));
            total += weights[i];
        }
        double[] ends = new double[pages.size()];
        int cumulative = 0;
        for (int i = 0; i < pages.size(); i++) {
            cumulative += weights[i];
            ends[i] = i == pages.size() - 1 ? 1.0 : cumulative / (double) Math.max(1, total);
        }
        return ends;
    }

    private static int wordCount(String s) { return s.isBlank() ? 0 : s.split(" ").length; }

    private static int wordWeight(String s) {
        int n = 0;
        for (int i = 0; i < s.length(); i++) if (Character.isLetterOrDigit(s.charAt(i))) n++;
        return Math.max(1, n);
    }

    private static boolean weakBoundaryWord(String token) {
        String t = token.toLowerCase(java.util.Locale.ROOT).replaceAll("[^\\p{L}]", "");
        return t.equals("de") || t.equals("del") || t.equals("a") || t.equals("al")
                || t.equals("en") || t.equals("con") || t.equals("para") || t.equals("por")
                || t.equals("que") || t.equals("y") || t.equals("o")
                || t.equals("of") || t.equals("to") || t.equals("in") || t.equals("with")
                || t.equals("for") || t.equals("that") || t.equals("and") || t.equals("or");
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
}
