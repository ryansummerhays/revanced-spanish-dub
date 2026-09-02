package app.spanishstudy.vot;

import android.app.*;
import android.os.*;
import android.text.InputType;
import android.view.View;
import android.widget.*;
import java.lang.ref.WeakReference;
import java.util.*;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;

public final class SpanishStudyController {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static List<TranscriptSegment> latest=new ArrayList<>();
    private static int reviewGeneration;
    private static WeakReference<View> playerControlsRef=new WeakReference<>(null);

    private SpanishStudyController(){}

    /** Captures YouTube's actual player-controls bounds for responsive subtitle positioning. */
    public static void onPlayerControlsView(View view){
        playerControlsRef=new WeakReference<>(view);
    }

    static View playerControlsView(){
        View view=playerControlsRef.get();
        return view!=null&&view.isAttachedToWindow()?view:null;
    }

    public static void onTranscriptUpdated(List<TranscriptSegment> segments){
        latest=segments==null?new ArrayList<>():new ArrayList<>(segments);
        SpanishSubtitleOverlay.setSegments(latest);
    }

    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments){
        final List<TranscriptSegment> snapshot=segments==null?new ArrayList<>():new ArrayList<>(segments);
        if(Looper.myLooper()==Looper.getMainLooper())SpanishSubtitleOverlay.setSourceSegments(snapshot);
        else MAIN.post(()->SpanishSubtitleOverlay.setSourceSegments(snapshot));
    }

    public static void onVideoTimeChanged(long timeMs){
        Activity activity=Utils.getActivity();
        SpanishSubtitleOverlay.update(activity,timeMs);
        SourceExpressionMonitor.maybeEnsureAttached(activity);
    }

    public static void onVideoCleared(){
        latest=new ArrayList<>();
        SpanishSubtitleOverlay.setSegments(latest);
        SpanishSubtitleOverlay.setSourceSegments(new ArrayList<>());
        SpanishSubtitleOverlay.hide();
        SpanishWordTimingStore.clear();
        SourceExpressionMonitor.resetDynamics();
    }

    public static void onSessionDisabled(){SpanishSubtitleOverlay.hide();}

    public static boolean isGeminiEnabled(Activity activity){
        return activity!=null&&SpanishStudyPrefs.geminiEnabled(activity);
    }

    public static boolean hasGeminiApiKey(Activity activity){
        return activity!=null&&!SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty();
    }

    public static void setGeminiEnabled(Activity activity,boolean enabled){
        if(activity!=null)SpanishStudyPrefs.setGeminiEnabled(activity,enabled);
    }

    public static void configureGemini(Activity activity){showGeminiSetup(activity);}

    public static boolean sourceExpressionEnabled(Activity activity){
        return activity!=null&&SpanishStudyPrefs.sourceExpressionEnabled(activity);
    }

    public static void setSourceExpressionEnabled(Activity activity,boolean enabled){
        if(activity==null)return;
        SpanishStudyPrefs.setSourceExpressionEnabled(activity,enabled);
        SourceExpressionMonitor.setEnabled(activity,enabled);
        Toast.makeText(activity,
                enabled?"Source expression enabled":"Source expression disabled",
                Toast.LENGTH_SHORT).show();
    }

    public static boolean suppressNativeCaptions(){
        Activity activity=Utils.getActivity();
        return activity!=null&&VoiceOverTranslationPatch.isSessionEnabled()
                &&(SpanishStudyPrefs.showSubtitles(activity)||SpanishStudyPrefs.showEnglishSubtitles(activity));
    }

    /** Called by the Edge TTS engine immediately before a fresh synthesis of this exact text. */
    public static void beginWordTimings(String text){SpanishWordTimingStore.begin(text);}

    /** Called by the Edge TTS engine as word-boundary metadata arrives. */
    public static void onWordTimings(String text,String[] words,long[] startsMs,long[] durationsMs){
        SpanishWordTimingStore.append(text,words,startsMs,durationsMs);
    }

    public static void showTools(Activity activity){
        if(activity==null||activity.isFinishing())return;
        SpanishStudySheet.show(activity);
    }

    private static void showGeminiSetup(Activity activity){
        if(activity==null||activity.isFinishing())return;
        int pad=Math.round(16*activity.getResources().getDisplayMetrics().density);
        LinearLayout box=new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(pad,pad/2,pad,0);

        TextView note=new TextView(activity);
        note.setText("The key is stored only in this app's local preferences. The default model is tuned for low latency; you can replace the model name later.");
        box.addView(note);

        EditText key=new EditText(activity);
        key.setHint("Gemini API key");
        key.setSingleLine(true);
        key.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setText(SpanishStudyPrefs.geminiApiKey(activity));
        box.addView(key);

        EditText model=new EditText(activity);
        model.setHint("Gemini model");
        model.setSingleLine(true);
        model.setText(SpanishStudyPrefs.geminiModel(activity));
        box.addView(model);

        new AlertDialog.Builder(activity)
                .setTitle("Gemini translation")
                .setView(box)
                .setPositiveButton("Save",(d,w)->{
                    SpanishStudyPrefs.setGeminiApiKey(activity,key.getText().toString());
                    SpanishStudyPrefs.setGeminiModel(activity,model.getText().toString());
                    boolean ready=!SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty();
                    SpanishStudyPrefs.setGeminiEnabled(activity,ready);
                    Toast.makeText(activity,ready?"Gemini translation enabled":"Gemini disabled: no API key",Toast.LENGTH_SHORT).show();
                    if(ready)VoiceOverTranslationPatch.reloadTranscript();
                })
                .setNegativeButton("Cancel",null)
                .show();
    }

    public static void openVocabularyReview(Activity activity){
        final int g=++reviewGeneration;
        waitForTranscript(activity,g,0);
    }

    private static void waitForTranscript(Activity activity,int generation,int attempt){
        if(generation!=reviewGeneration||activity==null||activity.isFinishing())return;
        List<TranscriptSegment> snapshot=VoiceOverTranslationPatch.getTranslatedSegmentsSnapshot();
        if(!VoiceOverTranslationPatch.isTranscriptLoading()&&!snapshot.isEmpty()){
            showVocabulary(activity,snapshot);
            return;
        }
        if(attempt==0)Toast.makeText(activity,"Preparing the full translated transcript…",Toast.LENGTH_SHORT).show();
        if(attempt>=120){
            if(!snapshot.isEmpty())showVocabulary(activity,snapshot);
            else Toast.makeText(activity,"No translated transcript is available for this video.",Toast.LENGTH_LONG).show();
            return;
        }
        MAIN.postDelayed(()->waitForTranscript(activity,generation,attempt+1),500);
    }

    private static void showVocabulary(Activity activity,List<TranscriptSegment> snapshot){
        Set<String> known=SpanishStudyPrefs.knownWords(activity);
        List<VocabularyAnalyzer.Segment> simple=new ArrayList<>(snapshot.size());
        for(TranscriptSegment s:snapshot){
            if(s.lang!=null&&s.lang.toLowerCase().startsWith("es")&&s.text!=null&&!s.text.isBlank())
                simple.add(new VocabularyAnalyzer.Segment(s.startMs,s.text));
        }
        List<VocabularyEntry> entries=VocabularyAnalyzer.analyze(simple,known,SpanishStudyPrefs.vocabLimit(activity),SpanishStudyPrefs.includeCommon(activity));
        if(entries.isEmpty()){
            Toast.makeText(activity,"No new vocabulary candidates found.",Toast.LENGTH_SHORT).show();
            return;
        }
        VocabularyReviewDialog.show(activity,VoiceOverTranslationPatch.getCurrentVideoIdForStudy(),entries);
    }
}
