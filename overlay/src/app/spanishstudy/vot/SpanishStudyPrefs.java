package app.spanishstudy.vot;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.*;

final class SpanishStudyPrefs {
    private static final String PREFS="spanish_study_vot",KNOWN="known_words",SHOW_SUBS="show_translated_subtitles",VOCAB_LIMIT="vocab_limit",INCLUDE_COMMON="include_common";
    private SpanishStudyPrefs(){}
    private static SharedPreferences prefs(Context c){return c.getSharedPreferences(PREFS,Context.MODE_PRIVATE);}
    static Set<String> knownWords(Context c){return new HashSet<>(prefs(c).getStringSet(KNOWN,Collections.emptySet()));}
    static boolean isKnown(Context c,String word){return knownWords(c).contains(VocabularyAnalyzer.normalize(word));}
    static void setKnown(Context c,String word,boolean known){Set<String> copy=knownWords(c);String n=VocabularyAnalyzer.normalize(word);if(known)copy.add(n);else copy.remove(n);prefs(c).edit().putStringSet(KNOWN,copy).apply();}
    static void clearKnown(Context c){prefs(c).edit().remove(KNOWN).apply();}
    static boolean showSubtitles(Context c){return prefs(c).getBoolean(SHOW_SUBS,true);}
    static void setShowSubtitles(Context c,boolean v){prefs(c).edit().putBoolean(SHOW_SUBS,v).apply();}
    static int vocabLimit(Context c){return Math.max(10,Math.min(100,prefs(c).getInt(VOCAB_LIMIT,40)));}
    static void setVocabLimit(Context c,int v){prefs(c).edit().putInt(VOCAB_LIMIT,Math.max(10,Math.min(100,v))).apply();}
    static boolean includeCommon(Context c){return prefs(c).getBoolean(INCLUDE_COMMON,false);}
    static void setIncludeCommon(Context c,boolean v){prefs(c).edit().putBoolean(INCLUDE_COMMON,v).apply();}
}
