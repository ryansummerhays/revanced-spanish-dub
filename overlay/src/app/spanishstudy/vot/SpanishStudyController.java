package app.spanishstudy.vot;

import android.app.*;
import android.os.*;
import android.widget.*;
import java.util.*;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;

public final class SpanishStudyController {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static List<TranscriptSegment> latest=new ArrayList<>(); private static int reviewGeneration;
    private SpanishStudyController(){}
    public static void onTranscriptUpdated(List<TranscriptSegment> segments){latest=segments==null?new ArrayList<>():new ArrayList<>(segments);SpanishSubtitleOverlay.setSegments(latest);}
    public static void onVideoTimeChanged(long timeMs){Activity activity=Utils.getActivity();SpanishSubtitleOverlay.update(activity,timeMs);}
    public static void onVideoCleared(){latest=new ArrayList<>();SpanishSubtitleOverlay.setSegments(latest);SpanishSubtitleOverlay.hide();}
    public static void onSessionDisabled(){SpanishSubtitleOverlay.hide();}
    public static void showTools(Activity activity){if(activity==null||activity.isFinishing())return;LinearLayout layout=new LinearLayout(activity);layout.setOrientation(LinearLayout.VERTICAL);int pad=Math.round(16*activity.getResources().getDisplayMetrics().density);layout.setPadding(pad,pad/2,pad,0);CheckBox subtitles=new CheckBox(activity);subtitles.setText("Show matching Spanish subtitles");subtitles.setChecked(SpanishStudyPrefs.showSubtitles(activity));subtitles.setOnCheckedChangeListener((v,c)->{SpanishStudyPrefs.setShowSubtitles(activity,c);if(!c)SpanishSubtitleOverlay.hide();});layout.addView(subtitles);CheckBox common=new CheckBox(activity);common.setText("Include very common words in vocabulary list");common.setChecked(SpanishStudyPrefs.includeCommon(activity));common.setOnCheckedChangeListener((v,c)->SpanishStudyPrefs.setIncludeCommon(activity,c));layout.addView(common);NumberPicker limit=new NumberPicker(activity);limit.setMinValue(10);limit.setMaxValue(100);limit.setValue(SpanishStudyPrefs.vocabLimit(activity));limit.setWrapSelectorWheel(false);limit.setOnValueChangedListener((p,o,n)->SpanishStudyPrefs.setVocabLimit(activity,n));layout.addView(limit);new AlertDialog.Builder(activity).setTitle("Spanish study tools").setView(layout).setPositiveButton("Review vocabulary",(d,w)->openVocabularyReview(activity)).setNeutralButton("Clear known words",(d,w)->{SpanishStudyPrefs.clearKnown(activity);Toast.makeText(activity,"Known-word list cleared",Toast.LENGTH_SHORT).show();}).setNegativeButton("Close",null).show();}
    public static void openVocabularyReview(Activity activity){final int g=++reviewGeneration;waitForTranscript(activity,g,0);}
    private static void waitForTranscript(Activity activity,int generation,int attempt){if(generation!=reviewGeneration||activity==null||activity.isFinishing())return;List<TranscriptSegment> snapshot=VoiceOverTranslationPatch.getTranslatedSegmentsSnapshot();if(!VoiceOverTranslationPatch.isTranscriptLoading()&&!snapshot.isEmpty()){showVocabulary(activity,snapshot);return;}if(attempt==0)Toast.makeText(activity,"Preparing the full translated transcript…",Toast.LENGTH_SHORT).show();if(attempt>=120){if(!snapshot.isEmpty())showVocabulary(activity,snapshot);else Toast.makeText(activity,"No translated transcript is available for this video.",Toast.LENGTH_LONG).show();return;}MAIN.postDelayed(()->waitForTranscript(activity,generation,attempt+1),500);}
    private static void showVocabulary(Activity activity,List<TranscriptSegment> snapshot){Set<String> known=SpanishStudyPrefs.knownWords(activity);List<VocabularyAnalyzer.Segment> simple=new ArrayList<>(snapshot.size());for(TranscriptSegment s:snapshot){if(s.lang!=null&&s.lang.toLowerCase().startsWith("es")&&s.text!=null&&!s.text.isBlank())simple.add(new VocabularyAnalyzer.Segment(s.startMs,s.text));}List<VocabularyEntry> entries=VocabularyAnalyzer.analyze(simple,known,SpanishStudyPrefs.vocabLimit(activity),SpanishStudyPrefs.includeCommon(activity));if(entries.isEmpty()){Toast.makeText(activity,"No new vocabulary candidates found.",Toast.LENGTH_SHORT).show();return;}VocabularyReviewDialog.show(activity,VoiceOverTranslationPatch.getCurrentVideoIdForStudy(),entries);}
}
