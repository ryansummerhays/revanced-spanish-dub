package app.spanishstudy.vot;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Final provider-agnostic text firewall between translation protocols and subtitles/TTS.
 * Prompt bookkeeping such as "1: [slot=1.8s]" or "[1.8 seconds]" is never user speech.
 */
public final class DubTextSanitizer {
    private DubTextSanitizer() {}

    private static final String UNIT = "(?:s|sec|secs|second|seconds)";
    private static final Pattern REDUNDANT_ENUM_BEFORE_METADATA = Pattern.compile(
            "^\\s*\\d{1,3}\\s*[:.)-]\\s*(?=[\\[(]\\s*(?:slot\\b|\\d+(?:\\.\\d+)?\\s*" + UNIT + "))",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern SLOT_PREFIX = Pattern.compile(
            "^\\s*[\\[(]\\s*slot\\s*(?:=|:)\\s*\\d+(?:\\.\\d+)?\\s*(?:" + UNIT + ")?\\s*[\\])]\\s*:?[ \\t]*",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern BRACKET_DURATION_PREFIX = Pattern.compile(
            "^\\s*[\\[(]\\s*\\d+(?:\\.\\d+)?\\s*" + UNIT + "\\s*[\\])]\\s*:?[ \\t]*",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern BARE_SLOT_PREFIX = Pattern.compile(
            "^\\s*slot\\s*(?:=|:)\\s*\\d+(?:\\.\\d+)?\\s*(?:" + UNIT + ")?\\s*:?[ \\t]*",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern TIMESTAMP_ECHO = Pattern.compile(
            "^\\s*\\[?\\s*\\d{3,}\\s*[-–—]\\s*\\d{3,}\\s*\\]?\\s*(?:>>)?\\s*:?[ \\t]*");
    private static final Pattern ONLY_PUNCT_OR_NUMERIC = Pattern.compile("^[\\d\\s.,:;\\-–—'\"“”‘’\\[\\]()]+$");
    private static final Pattern LEADING_PROTOCOL_PUNCT = Pattern.compile("^\\s*:+\\s*(?:[\"“])?\\s*");

    /**
     * Returns clean user-facing/spoken text, or null when the value is protocol garbage.
     * Legitimate unbracketed speech such as "1.8 segundos después" is preserved.
     */
    public static String cleanForSpeech(String text) {
        if (text == null) return null;
        String value = normalizeWhitespace(text).trim();
        if (value.isEmpty()) return null;

        // Strip only protocol-shaped prefixes. Loop handles double emission such as
        // "1: [slot=1.8s] [1.8 seconds] Hola" without touching ordinary numbered speech.
        for (int pass = 0; pass < 5; pass++) {
            String before = value;
            value = REDUNDANT_ENUM_BEFORE_METADATA.matcher(value).replaceFirst("").trim();
            value = SLOT_PREFIX.matcher(value).replaceFirst("").trim();
            value = BRACKET_DURATION_PREFIX.matcher(value).replaceFirst("").trim();
            value = BARE_SLOT_PREFIX.matcher(value).replaceFirst("").trim();
            if (value.equals(before)) break;
        }

        value = LEADING_PROTOCOL_PUNCT.matcher(value).replaceFirst("").trim();
        if (value.isEmpty()) return null;
        if (TIMESTAMP_ECHO.matcher(value).find()) return null;

        String upper = value.toUpperCase(Locale.ROOT);
        if (upper.startsWith("VIDEO-SPECIFIC CONTEXT")
                || upper.startsWith("REFERENCE CONTEXT")
                || upper.equals("<MISSING>")
                || upper.startsWith("<MISSING>")) {
            return null;
        }
        if (value.startsWith("[") && !value.contains("]")) return null;
        if (ONLY_PUNCT_OR_NUMERIC.matcher(value).matches()) return null;
        return value;
    }

    public static boolean containsLeadingProtocolMetadata(String text) {
        if (text == null) return false;
        String raw = normalizeWhitespace(text).trim();
        String clean = cleanForSpeech(raw);
        return clean == null || !raw.equals(clean);
    }

    private static String normalizeWhitespace(String text) {
        return text.replace('\u00A0', ' ')
                .replace('\u2007', ' ')
                .replace('\u202F', ' ')
                .replaceAll("[\\t\\r\\n]+", " ")
                .replaceAll(" {2,}", " ");
    }
}
