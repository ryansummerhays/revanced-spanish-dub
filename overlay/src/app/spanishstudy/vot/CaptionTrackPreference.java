package app.spanishstudy.vot;

import java.util.Locale;

/**
 * Shared caption-track selection policy for the English -> Spanish study pipeline.
 *
 * The dub target must never be mistaken for the study/source language. In particular, when YouTube
 * offers both English and Spanish tracks, the English track is the source of truth for English
 * subtitles and is translated to Spanish. Non-Gemini tracks are preferred at each comparable tier.
 */
public final class CaptionTrackPreference {
    private CaptionTrackPreference() {}

    /** Lower ranks are better. */
    public static int rank(String languageTag, boolean nonGemini, String targetLanguageTag) {
        final String lang = base(languageTag);
        final String target = base(targetLanguageTag);

        if ("en".equals(lang)) return nonGemini ? 0 : 10;
        if (!target.isEmpty() && target.equals(lang)) return nonGemini ? 20 : 40;
        return nonGemini ? 30 : 50;
    }

    public static boolean isEnglish(String languageTag) {
        return "en".equals(base(languageTag));
    }

    public static String base(String languageTag) {
        if (languageTag == null) return "";
        String value = languageTag.trim().toLowerCase(Locale.ROOT).replace('_', '-');
        int dash = value.indexOf('-');
        return dash < 0 ? value : value.substring(0, dash);
    }
}
