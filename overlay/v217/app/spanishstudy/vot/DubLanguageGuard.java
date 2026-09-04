package app.spanishstudy.vot;

import java.text.Normalizer;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Lightweight source-aware guard against untranslated English reaching Spanish TTS. */
public final class DubLanguageGuard {
    private static final Set<String> ENGLISH_CUES = new HashSet<>(Arrays.asList(
            "the", "and", "you", "your", "to", "of", "is", "are", "was", "were", "that", "this",
            "it", "for", "in", "we", "with", "be", "have", "has", "they", "not", "as", "on", "at",
            "from", "or", "by", "an", "but", "if", "so", "can", "will", "would", "just", "what",
            "when", "how", "why", "who", "do", "does", "did", "i", "me", "my", "our"
    ));
    private static final Set<String> SPANISH_CUES = new HashSet<>(Arrays.asList(
            "el", "la", "los", "las", "y", "de", "que", "en", "un", "una", "es", "son", "para",
            "por", "con", "se", "no", "como", "del", "al", "lo", "su", "sus", "si", "pero",
            "porque", "cuando", "qué", "cómo", "yo", "me", "mi", "nos", "nuestro", "esta", "este"
    ));

    private DubLanguageGuard() {}

    public static boolean isSafeTranslation(String source, String translated, String targetLang) {
        return reason(source, translated, targetLang) == null;
    }

    /** @return null when safe, otherwise a compact diagnostic reason. */
    public static String reason(String source, String translated, String targetLang) {
        if (targetLang == null || !targetLang.toLowerCase(Locale.ROOT).startsWith("es")) return null;
        String src = normalize(source);
        String out = normalize(translated);
        if (out.isEmpty()) return src.isEmpty() ? null : "blank-output";

        String[] outWords = words(out);
        if (outWords.length < 3) return null; // Names and very short interjections are too ambiguous.

        int english = cueHits(outWords, ENGLISH_CUES);
        int spanish = cueHits(outWords, SPANISH_CUES);
        boolean sameAsSource = !src.isEmpty() && src.equals(out);

        if (sameAsSource && outWords.length >= 4 && english >= 1) return "unchanged-english-source";

        double similarity = tokenSimilarity(words(src), outWords);
        if (english >= 2 && spanish == 0 && similarity >= 0.72) return "english-like-high-source-similarity";
        if (english >= 3 && spanish == 0 && english >= Math.max(3, outWords.length / 3)) return "english-function-word-density";
        return null;
    }

    private static String normalize(String text) {
        if (text == null) return "";
        String s = Normalizer.normalize(text, Normalizer.Form.NFKC).toLowerCase(Locale.ROOT);
        s = s.replaceAll("[^\\p{L}\\p{N}']+", " ").trim();
        return s.replaceAll("\\s+", " ");
    }

    private static String[] words(String normalized) {
        return normalized == null || normalized.isBlank() ? new String[0] : normalized.split(" ");
    }

    private static int cueHits(String[] words, Set<String> cues) {
        int hits = 0;
        for (String word : words) if (cues.contains(word)) hits++;
        return hits;
    }

    private static double tokenSimilarity(String[] a, String[] b) {
        if (a.length == 0 || b.length == 0) return 0.0;
        Set<String> sa = new HashSet<>(Arrays.asList(a));
        Set<String> sb = new HashSet<>(Arrays.asList(b));
        int intersection = 0;
        for (String word : sa) if (sb.contains(word)) intersection++;
        int union = sa.size() + sb.size() - intersection;
        return union == 0 ? 0.0 : intersection / (double) union;
    }
}