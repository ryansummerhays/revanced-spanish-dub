package app.spanishstudy.vot;

import java.text.Normalizer;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Conservative source-aware guard against untranslated English leaking into Spanish dub text. */
public final class DubLanguageGuard {
    private static final Set<String> ENGLISH_CUES = new HashSet<>(Arrays.asList(
            "the", "and", "you", "your", "of", "is", "are", "was", "were", "that", "this",
            "it", "for", "with", "have", "has", "they", "not", "as", "on", "from", "or", "but",
            "if", "so", "will", "would", "what", "when", "how", "why", "who", "does", "did",
            "whose", "exactly", "into", "than", "then", "them", "their", "there", "here"
    ));
    private static final Set<String> SPANISH_CUES = new HashSet<>(Arrays.asList(
            "el", "la", "los", "las", "y", "de", "que", "en", "un", "una", "es", "son", "para",
            "por", "con", "se", "no", "como", "del", "al", "lo", "su", "sus", "si", "pero",
            "porque", "cuando", "yo", "me", "mi", "nos", "nuestro", "esta", "este", "ha", "he",
            "han", "fue", "era", "muy", "más", "ya", "todo", "todos", "toda", "todas"
    ));

    private DubLanguageGuard() {}

    /** @return null when safe, otherwise a compact diagnostic reason. */
    public static String reason(String source, String translated, String targetLang) {
        if (targetLang == null || !targetLang.toLowerCase(Locale.ROOT).startsWith("es")) return null;
        String src = normalize(source);
        String out = normalize(translated);
        if (out.isEmpty()) return src.isEmpty() ? null : "blank-output";

        String[] srcWords = words(src);
        String[] outWords = words(out);
        if (outWords.length < 3) return null;

        int english = cueHits(outWords, ENGLISH_CUES);
        int spanish = cueHits(outWords, SPANISH_CUES);
        if (!src.isEmpty() && src.equals(out) && outWords.length >= 4 && english >= 1) {
            return "unchanged-english-source";
        }

        int suspiciousRun = longestSuspiciousSharedRun(srcWords, outWords);
        if (suspiciousRun >= 2) return "source-english-run-" + suspiciousRun;

        // Pure-English or overwhelmingly English output is still rejected even when wording changed.
        if (english >= 3 && spanish == 0 && english >= Math.max(3, outWords.length / 4)) {
            return "english-function-word-density";
        }
        return null;
    }

    public static boolean isSafeTranslation(String source, String translated, String targetLang) {
        return reason(source, translated, targetLang) == null;
    }

    /**
     * Finds a source/output contiguous token run that strongly suggests untranslated English.
     * Two-token runs need an English cue (so proper names such as "Lord Vader" survive); four or
     * more identical consecutive source tokens are suspicious on their own.
     */
    private static int longestSuspiciousSharedRun(String[] source, String[] out) {
        int best = 0;
        for (int i = 0; i < source.length; i++) {
            for (int j = 0; j < out.length; j++) {
                int k = 0;
                boolean englishCue = false;
                while (i + k < source.length && j + k < out.length
                        && source[i + k].equals(out[j + k])) {
                    if (ENGLISH_CUES.contains(source[i + k])) englishCue = true;
                    k++;
                }
                if (k >= 4 || (k >= 2 && englishCue)) best = Math.max(best, k);
            }
        }
        return best;
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
}
