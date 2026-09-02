package app.spanishstudy.vot;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.*;

final class SpanishStudyPrefs {
    static final String DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite";

    private static final String PREFS="spanish_study_vot",
            KNOWN="known_words",
            SHOW_SUBS="show_translated_subtitles",
            SHOW_ENGLISH_SUBS="show_english_subtitles",
            VOCAB_LIMIT="vocab_limit",
            INCLUDE_COMMON="include_common",
            SUBTITLE_WORDS="subtitle_words_per_chunk",
            SUBTITLE_TEXT_SIZE="subtitle_text_size_sp",
            ENGLISH_SUBTITLE_TEXT_SIZE="english_subtitle_text_size_sp",
            SPANISH_SUBTITLE_BOTTOM="spanish_subtitle_bottom_dp",
            ENGLISH_SUBTITLE_BOTTOM="english_subtitle_bottom_dp",
            SUBTITLE_PAIR_BOTTOM="bilingual_subtitle_bottom_dp",
            SOURCE_EXPRESSION="source_expression_enabled",
            GEMINI_ENABLED="gemini_enabled",
            GEMINI_API_KEY="gemini_api_key",
            GEMINI_MODEL="gemini_model";

    private SpanishStudyPrefs(){}

    private static SharedPreferences prefs(Context c){
        Context app=c==null?null:c.getApplicationContext();
        Context stable=app!=null?app:c;
        if(stable==null)throw new IllegalArgumentException("Context is required");
        return stable.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
    }

    // UI controls are saved synchronously. These values are tiny, and commit() guarantees the
    // position/size/toggle chosen in the sheet is already on disk before Android kills the process.
    private static void putBoolean(Context c,String key,boolean value){prefs(c).edit().putBoolean(key,value).commit();}
    private static void putInt(Context c,String key,int value){prefs(c).edit().putInt(key,value).commit();}
    private static void putString(Context c,String key,String value){prefs(c).edit().putString(key,value).commit();}
    private static int clampPosition(int v){return Math.max(24,Math.min(240,v));}

    static Set<String> knownWords(Context c){return new HashSet<>(prefs(c).getStringSet(KNOWN,Collections.emptySet()));}
    static boolean isKnown(Context c,String word){return knownWords(c).contains(VocabularyAnalyzer.normalize(word));}
    static void setKnown(Context c,String word,boolean known){Set<String> copy=knownWords(c);String n=VocabularyAnalyzer.normalize(word);if(known)copy.add(n);else copy.remove(n);prefs(c).edit().putStringSet(KNOWN,copy).apply();}
    static void clearKnown(Context c){prefs(c).edit().remove(KNOWN).apply();}

    static boolean showSubtitles(Context c){return prefs(c).getBoolean(SHOW_SUBS,true);}
    static void setShowSubtitles(Context c,boolean v){putBoolean(c,SHOW_SUBS,v);}
    static boolean showEnglishSubtitles(Context c){return prefs(c).getBoolean(SHOW_ENGLISH_SUBS,true);}
    static void setShowEnglishSubtitles(Context c,boolean v){putBoolean(c,SHOW_ENGLISH_SUBS,v);}

    // Retained for compatibility with older installs; word-count chunking is no longer used.
    static int subtitleWords(Context c){return Math.max(4,Math.min(12,prefs(c).getInt(SUBTITLE_WORDS,7)));}
    static void setSubtitleWords(Context c,int v){putInt(c,SUBTITLE_WORDS,Math.max(4,Math.min(12,v)));}
    static int subtitleTextSize(Context c){return Math.max(8,Math.min(18,prefs(c).getInt(SUBTITLE_TEXT_SIZE,12)));}
    static void setSubtitleTextSize(Context c,int v){putInt(c,SUBTITLE_TEXT_SIZE,Math.max(8,Math.min(18,v)));}
    static int englishSubtitleTextSize(Context c){return Math.max(8,Math.min(18,prefs(c).getInt(ENGLISH_SUBTITLE_TEXT_SIZE,11)));}
    static void setEnglishSubtitleTextSize(Context c,int v){putInt(c,ENGLISH_SUBTITLE_TEXT_SIZE,Math.max(8,Math.min(18,v)));}

    // Legacy independent positions are kept only to migrate an existing user's preferred area.
    static int spanishSubtitleBottom(Context c){return clampPosition(prefs(c).getInt(SPANISH_SUBTITLE_BOTTOM,72));}
    static void setSpanishSubtitleBottom(Context c,int v){putInt(c,SPANISH_SUBTITLE_BOTTOM,clampPosition(v));}
    static int englishSubtitleBottom(Context c){return clampPosition(prefs(c).getInt(ENGLISH_SUBTITLE_BOTTOM,118));}
    static void setEnglishSubtitleBottom(Context c,int v){putInt(c,ENGLISH_SUBTITLE_BOTTOM,clampPosition(v));}

    /**
     * One shared anchor keeps Spanish directly above English as a bilingual pair. For users coming
     * from an older build, start at the lower of the two legacy positions so the pair remains near
     * the area they already chose rather than jumping somewhere new.
     */
    static int subtitlePairBottom(Context c){
        SharedPreferences p=prefs(c);
        if(p.contains(SUBTITLE_PAIR_BOTTOM))return clampPosition(p.getInt(SUBTITLE_PAIR_BOTTOM,72));
        return Math.min(spanishSubtitleBottom(c),englishSubtitleBottom(c));
    }
    static void setSubtitlePairBottom(Context c,int v){putInt(c,SUBTITLE_PAIR_BOTTOM,clampPosition(v));}

    /** Experimental; opt-in because Android's playback Visualizer requires RECORD_AUDIO permission. */
    static boolean sourceExpressionEnabled(Context c){return prefs(c).getBoolean(SOURCE_EXPRESSION,false);}
    static void setSourceExpressionEnabled(Context c,boolean v){putBoolean(c,SOURCE_EXPRESSION,v);}

    static int vocabLimit(Context c){return Math.max(10,Math.min(100,prefs(c).getInt(VOCAB_LIMIT,40)));}
    static void setVocabLimit(Context c,int v){putInt(c,VOCAB_LIMIT,Math.max(10,Math.min(100,v)));}
    static boolean includeCommon(Context c){return prefs(c).getBoolean(INCLUDE_COMMON,false);}
    static void setIncludeCommon(Context c,boolean v){putBoolean(c,INCLUDE_COMMON,v);}

    static boolean geminiEnabled(Context c){return prefs(c).getBoolean(GEMINI_ENABLED,false);}
    static void setGeminiEnabled(Context c,boolean v){putBoolean(c,GEMINI_ENABLED,v);}
    static String geminiApiKey(Context c){return prefs(c).getString(GEMINI_API_KEY,"");}
    static void setGeminiApiKey(Context c,String v){putString(c,GEMINI_API_KEY,v==null?"":v.trim());}
    static String geminiModel(Context c){String v=prefs(c).getString(GEMINI_MODEL,DEFAULT_GEMINI_MODEL);return v==null||v.isBlank()?DEFAULT_GEMINI_MODEL:v;}
    static void setGeminiModel(Context c,String v){String n=v==null?"":v.trim();putString(c,GEMINI_MODEL,n.isEmpty()?DEFAULT_GEMINI_MODEL:n);}
}
