package app.spanishstudy.vot;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.*;

final class SpanishStudyPrefs {
    static final String DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite";

    private static final String PREFS="spanish_study_vot",
            KNOWN="known_words",
            SHOW_SUBS="show_translated_subtitles",
            VOCAB_LIMIT="vocab_limit",
            INCLUDE_COMMON="include_common",
            SUBTITLE_WORDS="subtitle_words_per_chunk",
            SUBTITLE_TEXT_SIZE="subtitle_text_size_sp",
            GEMINI_ENABLED="gemini_enabled",
            GEMINI_API_KEY="gemini_api_key",
            GEMINI_MODEL="gemini_model";

    private SpanishStudyPrefs(){}
    private static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);}

    static Set<String> knownWords(Context c){return new HashSet<>(prefs(c).getStringSet(KNOWN,Collections.emptySet()));}
    static boolean isKnown(Context c,String word){return knownWords(c).contains(VocabularyAnalyzer.normalize(word));}
    static void setKnown(Context c,String word,boolean known){Set<String> copy=knownWords(c);String n=VocabularyAnalyzer.normalize(word);if(known)copy.add(n);else copy.remove(n);prefs(c).edit().putStringSet(KNOWN,copy).apply();}
    static void clearKnown(Context c){prefs(c).edit().remove(KNOWN).apply();}

    static boolean showSubtitles(Context c){return prefs(c).getBoolean(SHOW_SUBS,true);}
    static void setShowSubtitles(Context c,boolean v){prefs(c).edit().putBoolean(SHOW_SUBS,v).apply();}
    static int subtitleWords(Context c){return Math.max(4,Math.min(12,prefs(c).getInt(SUBTITLE_WORDS,7)));}
    static void setSubtitleWords(Context c,int v){prefs(c).edit().putInt(SUBTITLE_WORDS,Math.max(4,Math.min(12,v))).apply();}
    static int subtitleTextSize(Context c){return Math.max(8,Math.min(18,prefs(c).getInt(SUBTITLE_TEXT_SIZE,12)));}
    static void setSubtitleTextSize(Context c,int v){prefs(c).edit().putInt(SUBTITLE_TEXT_SIZE,Math.max(8,Math.min(18,v))).apply();}

    static int vocabLimit(Context c){return Math.max(10,Math.min(100,prefs(c).getInt(VOCAB_LIMIT,40)));}
    static void setVocabLimit(Context c,int v){prefs(c).edit().putInt(VOCAB_LIMIT,Math.max(10,Math.min(100,v))).apply();}
    static boolean includeCommon(Context c){return prefs(c).getBoolean(INCLUDE_COMMON,false);}
    static void setIncludeCommon(Context c,boolean v){prefs(c).edit().putBoolean(INCLUDE_COMMON,v).apply();}

    static boolean geminiEnabled(Context c){return prefs(c).getBoolean(GEMINI_ENABLED,false);}
    static void setGeminiEnabled(Context c,boolean v){prefs(c).edit().putBoolean(GEMINI_ENABLED,v).apply();}
    static String geminiApiKey(Context c){return prefs(c).getString(GEMINI_API_KEY,"");}
    static void setGeminiApiKey(Context c,String v){prefs(c).edit().putString(GEMINI_API_KEY,v==null?"":v.trim()).apply();}
    static String geminiModel(Context c){String v=prefs(c).getString(GEMINI_MODEL,DEFAULT_GEMINI_MODEL);return v==null||v.isBlank()?DEFAULT_GEMINI_MODEL:v;}
    static void setGeminiModel(Context c,String v){String n=v==null?"":v.trim();prefs(c).edit().putString(GEMINI_MODEL,n.isEmpty()?DEFAULT_GEMINI_MODEL:n).apply();}
}
