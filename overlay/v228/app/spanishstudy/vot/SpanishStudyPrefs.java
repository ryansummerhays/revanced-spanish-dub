package app.spanishstudy.vot;

import android.content.Context;
import android.content.SharedPreferences;

/** Settings owned only by the Spanish study overlay/diagnostic experiment. */
final class SpanishStudyPrefs {
    private static final String PREFS = "spanish_study_vot";

    private static final String SHOW_SUBS = "show_translated_subtitles";
    private static final String SHOW_ENGLISH_SUBS = "show_english_subtitles";
    private static final String SUBTITLE_TEXT_SIZE = "subtitle_text_size_sp";
    private static final String ENGLISH_SUBTITLE_TEXT_SIZE = "english_subtitle_text_size_sp";
    private static final String SUBTITLE_PAIR_BOTTOM = "bilingual_subtitle_bottom_dp";

    private static final String SPEAKER_EXPERIMENT = "speaker_local_experiment_v228";

    private static final String LOG_LIFECYCLE = "diag_lifecycle";
    private static final String LOG_CAPTIONS = "diag_captions";
    private static final String LOG_TRANSLATION = "diag_translation";
    private static final String LOG_TTS = "diag_tts";
    private static final String LOG_SUBTITLES = "diag_subtitles";
    private static final String LOG_AUDIO = "diag_audio";
    private static final String LOG_SPEAKER = "diag_speaker";
    private static final String LOG_TEXT = "diag_include_text";

    private SpanishStudyPrefs() {}

    private static SharedPreferences prefs(Context context) {
        Context app = context == null ? null : context.getApplicationContext();
        Context stable = app != null ? app : context;
        if (stable == null) throw new IllegalArgumentException("Context is required");
        return stable.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private static void putBoolean(Context c, String key, boolean value) {
        prefs(c).edit().putBoolean(key, value).apply();
    }
    private static void putInt(Context c, String key, int value) {
        prefs(c).edit().putInt(key, value).apply();
    }

    static boolean showSubtitles(Context c) { return prefs(c).getBoolean(SHOW_SUBS, true); }
    static void setShowSubtitles(Context c, boolean v) { putBoolean(c, SHOW_SUBS, v); }
    static boolean showEnglishSubtitles(Context c) { return prefs(c).getBoolean(SHOW_ENGLISH_SUBS, true); }
    static void setShowEnglishSubtitles(Context c, boolean v) { putBoolean(c, SHOW_ENGLISH_SUBS, v); }

    static int subtitleTextSize(Context c) {
        return Math.max(8, Math.min(18, prefs(c).getInt(SUBTITLE_TEXT_SIZE, 12)));
    }
    static void setSubtitleTextSize(Context c, int v) { putInt(c, SUBTITLE_TEXT_SIZE, Math.max(8, Math.min(18, v))); }
    static int englishSubtitleTextSize(Context c) {
        return Math.max(8, Math.min(18, prefs(c).getInt(ENGLISH_SUBTITLE_TEXT_SIZE, 11)));
    }
    static void setEnglishSubtitleTextSize(Context c, int v) { putInt(c, ENGLISH_SUBTITLE_TEXT_SIZE, Math.max(8, Math.min(18, v))); }
    static int subtitlePairBottom(Context c) {
        return Math.max(24, Math.min(240, prefs(c).getInt(SUBTITLE_PAIR_BOTTOM, 72)));
    }
    static void setSubtitlePairBottom(Context c, int v) { putInt(c, SUBTITLE_PAIR_BOTTOM, Math.max(24, Math.min(240, v))); }

    static boolean speakerExperiment(Context c) { return prefs(c).getBoolean(SPEAKER_EXPERIMENT, true); }
    static void setSpeakerExperiment(Context c, boolean v) { putBoolean(c, SPEAKER_EXPERIMENT, v); }

    static boolean logLifecycle(Context c) { return prefs(c).getBoolean(LOG_LIFECYCLE, true); }
    static void setLogLifecycle(Context c, boolean v) { putBoolean(c, LOG_LIFECYCLE, v); }
    static boolean logCaptions(Context c) { return prefs(c).getBoolean(LOG_CAPTIONS, true); }
    static void setLogCaptions(Context c, boolean v) { putBoolean(c, LOG_CAPTIONS, v); }
    static boolean logTranslation(Context c) { return prefs(c).getBoolean(LOG_TRANSLATION, true); }
    static void setLogTranslation(Context c, boolean v) { putBoolean(c, LOG_TRANSLATION, v); }
    static boolean logTts(Context c) { return prefs(c).getBoolean(LOG_TTS, true); }
    static void setLogTts(Context c, boolean v) { putBoolean(c, LOG_TTS, v); }
    static boolean logSubtitles(Context c) { return prefs(c).getBoolean(LOG_SUBTITLES, true); }
    static void setLogSubtitles(Context c, boolean v) { putBoolean(c, LOG_SUBTITLES, v); }
    static boolean logAudio(Context c) { return prefs(c).getBoolean(LOG_AUDIO, true); }
    static void setLogAudio(Context c, boolean v) { putBoolean(c, LOG_AUDIO, v); }
    static boolean logSpeaker(Context c) { return prefs(c).getBoolean(LOG_SPEAKER, true); }
    static void setLogSpeaker(Context c, boolean v) { putBoolean(c, LOG_SPEAKER, v); }
    static boolean logText(Context c) { return prefs(c).getBoolean(LOG_TEXT, false); }
    static void setLogText(Context c, boolean v) { putBoolean(c, LOG_TEXT, v); }

    static void applyDiagnosticConfig(Context c) {
        SpanishStudyDiagnostics.configure(
                logLifecycle(c), logCaptions(c), logTranslation(c), logTts(c),
                logSubtitles(c), logAudio(c), logSpeaker(c), logText(c));
    }
}
