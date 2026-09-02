package app.spanishstudy.vot;

import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Defensive validation for bilingual subtitle/TTS pairs.
 *
 * Alignment is treated as data integrity: Gemini must echo the exact source event it translated,
 * obvious neighboring-event token leakage is rejected, and a Spanish slot is rejected when the
 * returned text is clearly still English. The last check also protects the TTS path so English text
 * is never intentionally spoken with the selected Spanish voice.
 */
public final class TranslationAlignmentGuard {
    private static final Set<String> ENGLISH_WORDS = new HashSet<>(Arrays.asList(
            "the","a","an","and","or","but","because","if","when","with","without",
            "to","of","for","from","in","on","at","is","are","was","were","be","been",
            "this","that","these","those","it","he","she","they","we","you","i","my",
            "your","his","her","their","our","not","dont","doesnt","didnt","cant","can",
            "could","would","should","what","whats","where","why","how","who","which",
            "lets","try","okay","ok","just","really","now","then","here","there","have",
            "has","had","do","does","did","get","got","go","going","want","need","think"
    ));

    private static final Set<String> SPANISH_WORDS = new HashSet<>(Arrays.asList(
            "el","la","los","las","un","una","unos","unas","y","o","pero","porque","si",
            "cuando","con","sin","de","del","para","por","en","es","son","era","fue","ser",
            "esta","este","esto","esa","ese","eso","que","quien","cual","como","donde","porqué",
            "yo","tu","usted","él","ella","ellos","ellas","nosotros","mi","mis","su","sus",
            "no","sí","ya","ahora","aqui","aquí","alli","allí","muy","mas","más","vamos",
            "quiero","quiere","quieres","tengo","tiene","hacer","hace","puede","puedo","bien"
    ));

    private TranslationAlignmentGuard() {}

    public static void validate(String canonicalSource,
                                String echoedSource,
                                String translation,
                                List<String> neighboringSources) {
        String canonical = normalize(canonicalSource);
        String echoed = normalize(echoedSource);
        String translated = normalize(translation);

        if (!canonical.equals(echoed)) {
            throw new IllegalArgumentException("Gemini source echo does not match requested event");
        }
        if (translated.isEmpty()) {
            throw new IllegalArgumentException("Gemini returned an empty translation");
        }
        if (!isSafeSpanishTranslation(canonical, translated)) {
            throw new IllegalArgumentException("Spanish subtitle slot is clearly still English");
        }

        Set<String> ownAnchors = distinctiveAnchors(canonical);
        Set<String> translatedAnchors = distinctiveAnchors(translated);
        if (translatedAnchors.isEmpty() || neighboringSources == null) return;

        for (String neighbor : neighboringSources) {
            for (String anchor : distinctiveAnchors(neighbor)) {
                if (!ownAnchors.contains(anchor) && translatedAnchors.contains(anchor)) {
                    throw new IllegalArgumentException(
                            "Gemini translation leaked neighboring source anchor: " + anchor);
                }
            }
        }
    }

    /**
     * Conservative language guard. Ambiguous short items such as "OK" and names are allowed; we
     * reject only strong evidence that an English sentence/phrase was copied into a Spanish slot.
     */
    public static boolean isSafeSpanishTranslation(String sourceEnglish, String candidateSpanish) {
        String source = normalize(sourceEnglish);
        String candidate = normalize(candidateSpanish);
        if (candidate.isEmpty()) return false;

        // A copied multi-word English source is never a valid translated result for this feature.
        if (source.equalsIgnoreCase(candidate) && alphabeticWordCount(candidate) >= 2) return false;

        String[] words = lexicalWords(candidate);
        int english = 0;
        int spanish = 0;
        for (String word : words) {
            if (ENGLISH_WORDS.contains(word)) english++;
            if (SPANISH_WORDS.contains(word)) spanish++;
        }

        // Require multiple English signals before rejection so names, acronyms and tiny utterances
        // do not get falsely suppressed. "Oh, what's the okay" and ordinary English sentences fail.
        return !(english >= 2 && english >= spanish + 2);
    }

    /**
     * Tokens with digits (R-9, 2026, 1080p) or acronyms of 3+ letters are useful alignment
     * fingerprints because translators normally preserve them rather than inventing them.
     */
    static Set<String> distinctiveAnchors(String text) {
        Set<String> out = new HashSet<>();
        String normalized = normalize(text);
        if (normalized.isEmpty()) return out;

        String[] tokens = normalized.replaceAll("[^\\p{L}\\p{N}-]+", " ").trim().split("\\s+");
        for (String token : tokens) {
            if (token.isEmpty()) continue;
            boolean hasDigit = false;
            boolean hasLetter = false;
            boolean allLettersUpper = true;
            int letterCount = 0;
            for (int i = 0; i < token.length(); i++) {
                char c = token.charAt(i);
                if (Character.isDigit(c)) hasDigit = true;
                if (Character.isLetter(c)) {
                    hasLetter = true;
                    letterCount++;
                    if (!Character.isUpperCase(c)) allLettersUpper = false;
                }
            }
            if ((hasDigit && token.length() >= 2)
                    || (hasLetter && letterCount >= 3 && allLettersUpper)) {
                out.add(token.toUpperCase(Locale.ROOT));
            }
        }
        return out;
    }

    private static int alphabeticWordCount(String text) {
        int count = 0;
        for (String word : lexicalWords(text)) {
            if (!word.isEmpty()) count++;
        }
        return count;
    }

    private static String[] lexicalWords(String text) {
        String cleaned = normalize(text).toLowerCase(Locale.ROOT)
                .replace('’', '\'')
                .replaceAll("[^\\p{L}']+", " ")
                .replace("'", "")
                .trim();
        return cleaned.isEmpty() ? new String[0] : cleaned.split("\\s+");
    }

    static String normalize(String text) {
        return text == null ? "" : text.trim().replaceAll("\\s+", " ");
    }
}
