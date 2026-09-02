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
 * returned text is clearly still English, malformed, or implausibly unrelated to the source.
 */
public final class TranslationAlignmentGuard {
    private static final Set<String> ENGLISH_WORDS = new HashSet<>(Arrays.asList(
            "the","a","an","and","or","but","because","if","when","with","without",
            "to","of","for","from","in","on","at","is","are","was","were","be","been",
            "this","that","these","those","it","he","she","they","we","you","i","my",
            "your","his","her","their","our","not","dont","doesnt","didnt","cant","can",
            "could","would","should","what","whats","where","why","how","who","which",
            "lets","try","okay","ok","just","really","now","then","here","there","have",
            "has","had","do","does","did","get","got","go","going","want","need","think",
            "yeah","yes","no","like","also","only","more","most","much","very","some",
            "something","anything","everything","thing","things","kind","sort","well"
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
            throw new IllegalArgumentException("Spanish subtitle slot failed language/format sanity checks");
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
     * Conservative language/shape guard. Ambiguous short items such as "OK" and names are allowed;
     * strong English-copy evidence, missing word spacing, lost numeric anchors, and extreme length
     * expansion/contraction are rejected before the text can reach Spanish TTS.
     */
    public static boolean isSafeSpanishTranslation(String sourceEnglish, String candidateSpanish) {
        String source = normalize(sourceEnglish);
        String candidate = normalize(candidateSpanish);
        if (candidate.isEmpty()) return false;

        if (!hasPlausibleWordSpacing(candidate)) return false;
        if (!hasReasonableLengthRatio(source, candidate)) return false;
        if (!preservesNumericAnchors(source, candidate)) return false;

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
        // do not get falsely suppressed.
        return !(english >= 2 && english >= spanish + 2);
    }

    /**
     * Used with an independent Google back-translation of Gemini's Spanish. This is intentionally
     * conservative: it only rejects a longer line when too little of its content survives the
     * round trip, or when a digit/acronym anchor disappears. Short conversational lines are left to
     * the deterministic guards because synonyms make lexical comparison too noisy there.
     */
    public static boolean isGroundedByBackTranslation(String intendedEnglish,
                                                       String backTranslatedEnglish) {
        String source = normalize(intendedEnglish);
        String back = normalize(backTranslatedEnglish);
        if (source.isEmpty() || back.isEmpty()) return false;
        if (!preservesNumericAnchors(source, back)) return false;

        Set<String> sourceAnchors = distinctiveAnchors(source);
        Set<String> backAnchors = distinctiveAnchors(back);
        for (String anchor : sourceAnchors) {
            if (!backAnchors.contains(anchor)) return false;
        }

        Set<String> sourceContent = contentWords(source);
        if (sourceContent.size() < 3) return true;
        Set<String> backContent = contentWords(back);
        if (backContent.isEmpty()) return false;

        int matches = 0;
        for (String token : sourceContent) {
            if (backContent.contains(token)) matches++;
        }
        if (matches >= 3) return true;
        return matches / (double) sourceContent.size() >= 0.32;
    }

    /** Reject the exact failure where a whole Spanish sentence arrives as one giant word. */
    static boolean hasPlausibleWordSpacing(String text) {
        String value = normalizeInvisibleWhitespace(text);
        int letters = 0;
        int spaces = 0;
        int run = 0;
        int longestRun = 0;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (Character.isLetter(c)) {
                letters++;
                run++;
                if (run > longestRun) longestRun = run;
            } else {
                if (Character.isWhitespace(c)) spaces++;
                run = 0;
            }
        }
        if (letters < 24) return true;
        return spaces >= 2 && longestRun < 24;
    }

    private static boolean hasReasonableLengthRatio(String source, String candidate) {
        int sourceLetters = letterCount(source);
        int candidateLetters = letterCount(candidate);
        if (sourceLetters < 18 || candidateLetters == 0) return true;
        double ratio = candidateLetters / (double) sourceLetters;
        return ratio >= 0.35 && ratio <= 2.40;
    }

    private static boolean preservesNumericAnchors(String source, String candidate) {
        Set<String> sourceNumbers = digitTokens(source);
        if (sourceNumbers.isEmpty()) return true;
        Set<String> candidateNumbers = digitTokens(candidate);
        return candidateNumbers.containsAll(sourceNumbers);
    }

    private static Set<String> digitTokens(String text) {
        Set<String> out = new HashSet<>();
        String normalized = normalize(text).replaceAll("[^\\p{L}\\p{N}.-]+", " ");
        for (String token : normalized.trim().split("\\s+")) {
            if (token.isEmpty()) continue;
            boolean hasDigit = false;
            for (int i = 0; i < token.length(); i++) {
                if (Character.isDigit(token.charAt(i))) {
                    hasDigit = true;
                    break;
                }
            }
            if (hasDigit) out.add(token.toUpperCase(Locale.ROOT));
        }
        return out;
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

    private static Set<String> contentWords(String text) {
        Set<String> out = new HashSet<>();
        for (String word : lexicalWords(text)) {
            if (word.length() < 4 || ENGLISH_WORDS.contains(word)) continue;
            out.add(lightStem(word));
        }
        return out;
    }

    private static String lightStem(String word) {
        String w = word;
        if (w.length() > 6 && w.endsWith("ing")) w = w.substring(0, w.length() - 3);
        else if (w.length() > 5 && w.endsWith("ed")) w = w.substring(0, w.length() - 2);
        else if (w.length() > 5 && w.endsWith("es")) w = w.substring(0, w.length() - 2);
        else if (w.length() > 4 && w.endsWith("s")) w = w.substring(0, w.length() - 1);
        return w;
    }

    private static int alphabeticWordCount(String text) {
        int count = 0;
        for (String word : lexicalWords(text)) {
            if (!word.isEmpty()) count++;
        }
        return count;
    }

    private static int letterCount(String text) {
        int count = 0;
        for (int i = 0; i < text.length(); i++) {
            if (Character.isLetter(text.charAt(i))) count++;
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

    private static String normalizeInvisibleWhitespace(String text) {
        return text == null ? "" : text
                .replace('\u00A0', ' ')
                .replace('\u2007', ' ')
                .replace('\u202F', ' ')
                .replace("\u200B", " ")
                .replace("\u2060", " ");
    }

    static String normalize(String text) {
        return normalizeInvisibleWhitespace(text).trim().replaceAll("\\s+", " ");
    }
}
