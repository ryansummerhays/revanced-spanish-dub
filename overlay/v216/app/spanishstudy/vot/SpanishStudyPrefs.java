package app.spanishstudy.vot;

import android.content.Context;
import android.content.SharedPreferences;

/** Minimal preferences owned by the Spanish subtitle/study layer. */
final class SpanishStudyPrefs {
    private static final String PREFS = "spanish_study_vot";
    private static final String SHOW_SUBS = "show_translated_subtitles";
    private static final String SHOW_ENGLISH_SUBS = "show_english_subtitles";
    private static final String SUBTITLE_TEXT_SIZE = "subtitle_text_size_sp";
    private static final String ENGLISH_SUBTITLE_TEXT_SIZE = "english_subtitle_text_size_sp";
    private static final String SUBTITLE_PAIR_BOTTOM = "bilingual_subtitle_bottom_dp";

    private SpanishStudyPrefs() {}

    private static SharedPreferences prefs(Context context) {
        Context app = context == null ? null : context.getApplicationContext();
        Context stable = app != null ? app : context;
        if (stable == null) throw new IllegalArgumentException("Context is required");
        return stable.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void putBoolean(Context context, String key, boolean value) {
        prefs(context).edit().putBoolean(key, value).apply();
    }

    private static void putInt(Context context, String key, int value) {
        prefs(context).edit().putInt(key, value).apply();
    }

    static boolean showSubtitles(Context context) {
        return prefs(context).getBoolean(SHOW_SUBS, true);
    }

    static void setShowSubtitles(Context context, boolean value) {
        putBoolean(context, SHOW_SUBS, value);
    }

    static boolean showEnglishSubtitles(Context context) {
        return prefs(context).getBoolean(SHOW_ENGLISH_SUBS, true);
    }

    static void setShowEnglishSubtitles(Context context, boolean value) {
        putBoolean(context, SHOW_ENGLISH_SUBS, value);
    }

    static int subtitleTextSize(Context context) {
        return Math.max(8, Math.min(18, prefs(context).getInt(SUBTITLE_TEXT_SIZE, 12)));
    }

    static void setSubtitleTextSize(Context context, int value) {
        putInt(context, SUBTITLE_TEXT_SIZE, Math.max(8, Math.min(18, value)));
    }

    static int englishSubtitleTextSize(Context context) {
        return Math.max(8, Math.min(18, prefs(context).getInt(ENGLISH_SUBTITLE_TEXT_SIZE, 11)));
    }

    static void setEnglishSubtitleTextSize(Context context, int value) {
        putInt(context, ENGLISH_SUBTITLE_TEXT_SIZE, Math.max(8, Math.min(18, value)));
    }

    static int subtitlePairBottom(Context context) {
        return Math.max(24, Math.min(240, prefs(context).getInt(SUBTITLE_PAIR_BOTTOM, 72)));
    }

    static void setSubtitlePairBottom(Context context, int value) {
        putInt(context, SUBTITLE_PAIR_BOTTOM, Math.max(24, Math.min(240, value)));
    }
}
