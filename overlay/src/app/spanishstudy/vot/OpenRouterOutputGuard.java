package app.spanishstudy.vot;

import java.util.ArrayList;
import java.util.List;

/** Pure validation/sanitization for streamed OpenRouter caption output. */
public final class OpenRouterOutputGuard {
    private OpenRouterOutputGuard() {}

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

    /** Remove every known translation-protocol marker before a result can become user text. */
    public static String sanitizeTranslation(String text) {
        return DubTextSanitizer.cleanForSpeech(text);
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
