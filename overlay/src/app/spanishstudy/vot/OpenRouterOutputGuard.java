package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/** Pure validation/sanitization for streamed OpenRouter caption output. */
public final class OpenRouterOutputGuard {
    private OpenRouterOutputGuard() {}

    private static final Pattern SLOT_PREFIX = Pattern.compile(
            "^\\s*\\[?\\s*slot\\s*=\\s*[^]\\r\\n]+\\]?\\s*:?[ \\t]*",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern DURATION_PREFIX = Pattern.compile(
            "^\\s*\\[?\\s*\\d+(?:\\.\\d+)?\\s*s\\s*\\]?\\s*:?[ \\t]*",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern TIMESTAMP_PREFIX = Pattern.compile(
            "^\\s*\\[?\\s*\\d{3,}\\s*[-–—]\\s*\\d{3,}\\s*\\]?\\s*(?:>>)?\\s*:?[ \\t]*");
    private static final Pattern ONLY_NUMERIC = Pattern.compile("^[\\d\\s.,:;\\-–—]+$");

    public static final class ParsedLine {
        public final int index;
        public final String text;

        ParsedLine(int index, String text) {
            this.index = index;
            this.text = text;
        }
    }

    /** Parse a 1-based numbered model line and reject obvious context/metadata echoes. */
    public static ParsedLine parseNumberedLine(String line, int segmentCount) {
        if (line == null || segmentCount <= 0) return null;
        String trimmed = line.trim();
        int i = 0;
        while (i < trimmed.length() && Character.isDigit(trimmed.charAt(i))) i++;
        if (i == 0 || i >= trimmed.length()) return null;
        char sep = trimmed.charAt(i);
        if (sep != ':' && sep != '.' && sep != ')') return null;
        final int number;
        try {
            number = Integer.parseInt(trimmed.substring(0, i));
        } catch (NumberFormatException ignored) {
            return null;
        }
        if (number < 1 || number > segmentCount) return null;
        String cleaned = sanitizeTranslation(trimmed.substring(i + 1));
        if (cleaned == null) return null;
        return new ParsedLine(number - 1, cleaned);
    }

    /** Remove prompt-only duration hints while rejecting raw-caption/context echoes. */
    public static String sanitizeTranslation(String text) {
        if (text == null) return null;
        String cleaned = text.trim();
        if (cleaned.isEmpty()) return null;

        cleaned = SLOT_PREFIX.matcher(cleaned).replaceFirst("").trim();
        cleaned = DURATION_PREFIX.matcher(cleaned).replaceFirst("").trim();
        if (cleaned.isEmpty()) return null;

        if (TIMESTAMP_PREFIX.matcher(cleaned).find()) return null;
        String upper = cleaned.toUpperCase(Locale.ROOT);
        if (upper.startsWith("VIDEO-SPECIFIC CONTEXT")
                || upper.startsWith("REFERENCE CONTEXT")
                || upper.equals("<MISSING>")
                || upper.startsWith("<MISSING>")) {
            return null;
        }
        if (cleaned.startsWith("[") && !cleaned.contains("]")) return null;
        if (ONLY_NUMERIC.matcher(cleaned).matches()) return null;
        return cleaned;
    }

    /** Conservative positional recovery; every candidate must pass the same output guard. */
    public static List<String> positionalFallback(String raw, int segmentCount) {
        if (raw == null || segmentCount <= 0) return null;
        List<String> lines = new ArrayList<>(segmentCount);
        for (String line : raw.split("\\n")) {
            String trimmed = line.trim();
            if (trimmed.isEmpty()) continue;
            String cleaned = sanitizeTranslation(stripNumberPrefix(trimmed));
            if (cleaned == null) return null;
            lines.add(cleaned);
        }
        return lines.size() == segmentCount ? lines : null;
    }

    private static String stripNumberPrefix(String line) {
        int i = 0;
        while (i < line.length() && Character.isDigit(line.charAt(i))) i++;
        if (i > 0 && i < line.length()) {
            char sep = line.charAt(i);
            if (sep == ':' || sep == '.' || sep == ')') return line.substring(i + 1).trim();
        }
        return line;
    }
}
