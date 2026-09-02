package app.spanishstudy.vot;

/**
 * Builds a conservative SSML fragment from already-grounded Spanish text.
 *
 * This deliberately uses NO microphone, playback visualizer, speaker analysis, or room audio.
 * Edge already interprets ordinary punctuation well, so we only add short explicit pauses at
 * punctuation that represents a strong natural speech break. Commas are left alone to avoid the
 * chopped, over-paused delivery that earlier builds sometimes produced.
 */
public final class NaturalProsodyFormatter {
    private NaturalProsodyFormatter() {}

    public static String toSsmlFragment(String text) {
        if (text == null || text.isBlank()) return "";
        String clean = text.trim().replaceAll("\\s+", " ");
        StringBuilder out = new StringBuilder(clean.length() + 96);

        for (int i = 0; i < clean.length(); i++) {
            char c = clean.charAt(i);

            // Preserve ellipses as one semantic pause instead of three punctuation events.
            if (c == '.' && i + 2 < clean.length()
                    && clean.charAt(i + 1) == '.' && clean.charAt(i + 2) == '.') {
                out.append("…<break time='180ms'/>");
                i += 2;
                continue;
            }

            appendEscaped(out, c);
            if (c == ';' || c == ':') {
                out.append("<break time='95ms'/>");
            } else if (c == '—' || c == '–') {
                out.append("<break time='130ms'/>");
            }
        }
        return out.toString();
    }

    private static void appendEscaped(StringBuilder out, char c) {
        switch (c) {
            case '&' -> out.append("&amp;");
            case '<' -> out.append("&lt;");
            case '>' -> out.append("&gt;");
            case '\'' -> out.append("&apos;");
            case '"' -> out.append("&quot;");
            default -> out.append(c);
        }
    }
}
