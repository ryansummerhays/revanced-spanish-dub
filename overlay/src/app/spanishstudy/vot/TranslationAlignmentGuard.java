package app.spanishstudy.vot;

import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Defensive validation for LLM-produced bilingual subtitle pairs.
 *
 * Gemini receives many source events at once for context. Even with structured output, a model can
 * occasionally attach a neighboring translation to the wrong event. Every response therefore has
 * to echo the exact English source event it translated, and a translation is rejected if it leaks a
 * distinctive numeric/model/acronym token that exists only in a neighboring source event.
 */
public final class TranslationAlignmentGuard {
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

    static String normalize(String text) {
        return text == null ? "" : text.trim().replaceAll("\\s+", " ");
    }
}
