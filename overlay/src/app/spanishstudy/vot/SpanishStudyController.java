package app.spanishstudy.vot;

import android.app.*;
import android.os.*;
import android.text.InputType;
import android.view.ViewGroup;
import android.widget.*;
import java.util.*;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;

public final class SpanishStudyController {
    private static final Handler MAIN=new Handler(Looper.getMainLooper());
    private static List<TranscriptSegment> latest=new ArrayList<>();
    private static int reviewGeneration;

    private SpanishStudyController(){}

    public static void onTranscriptUpdated(List<TranscriptSegment> segments){
        latest=segments==null?new ArrayList<>():new ArrayList<>(segments);
        SpanishSubtitleOverlay.setSegments(latest);
    }

    public static void onVideoTimeChanged(long timeMs){
        Activity activity=Utils.getActivity();
        SpanishSubtitleOverlay.update(activity,timeMs);
    }

    public static void onVideoCleared(){
        latest=new ArrayList<>();
        SpanishSubtitleOverlay.setSegments(latest);
        SpanishSubtitleOverlay.hide();
        SpanishWordTimingStore.clear();
    }

    public static void onSessionDisabled(){SpanishSubtitleOverlay.hide();}

    /** Called by the Edge TTS engine immediately before a fresh synthesis of this exact text. */
    public static void beginWordTimings(String text){SpanishWordTimingStore.begin(text);}

    /** Called by the Edge TTS engine as word-boundary metadata arrives. */
    public static void onWordTimings(String text,String[] words,long[] startsMs,long[] durationsMs){
        SpanishWordTimingStore.append(text,words,startsMs,durationsMs);
    }

    public static void showTools(Activity activity){
        if(activity==null||activity.isFinishing())return;
        LinearLayout layout=new LinearLayout(activity);
        layout.setOrientation(LinearLayout.VERTICAL);
        int pad=Math.round(16*activity.getResources().getDisplayMetrics().density);
        layout.setPadding(pad,pad/2,pad,0);

        CheckBox subtitles=new CheckBox(activity);
        subtitles.setText("Show matching Spanish subtitles");
        subtitles.setChecked(SpanishStudyPrefs.showSubtitles(activity));
        subtitles.setOnCheckedChangeListener((v,c)->{
            SpanishStudyPrefs.setShowSubtitles(activity,c);
            if(!c)SpanishSubtitleOverlay.hide();
        });
        layout.addView(subtitles);

        TextView chunkLabel=new TextView(activity);
        chunkLabel.setText("Subtitle words per chunk");
        layout.addView(chunkLabel);
        NumberPicker chunkSize=new NumberPicker(activity);
        chunkSize.setMinValue(4);
        chunkSize.setMaxValue(12);
        chunkSize.setValue(SpanishStudyPrefs.subtitleWords(activity));
        chunkSize.setWrapSelectorWheel(false);
        chunkSize.setOnValueChangedListener((p,o,n)->SpanishStudyPrefs.setSubtitleWords(activity,n));
        layout.addView(chunkSize,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));

        CheckBox gemini=new CheckBox(activity);
        gemini.setText("Use Gemini contextual translation");
        gemini.setChecked(SpanishStudyPrefs.geminiEnabled(activity));
        gemini.setOnCheckedChangeListener((v,c)->{
            if(c&&SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty()){
                v.setChecked(false);
                Toast.makeText(activity,"Configure a Gemini API key first",Toast.LENGTH_SHORT).show();
                showGeminiSetup(activity);
                return;
            }
            SpanishStudyPrefs.setGeminiEnabled(activity,c);
            Toast.makeText(activity,c?"Gemini will be used on the next transcript reload":"Using Morphe translation provider",Toast.LENGTH_SHORT).show();
        });
        layout.addView(gemini);

        Button geminiSetup=new Button(activity);
        geminiSetup.setText("Configure Gemini");
        geminiSetup.setOnClickListener(v->showGeminiSetup(activity));
        layout.addView(geminiSetup);

        TextView geminiStatus=new TextView(activity);
        String keyStatus=SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty()?"no API key":"API key saved";
        geminiStatus.setText("Model: "+SpanishStudyPrefs.geminiModel(activity)+" · "+keyStatus);
        layout.addView(geminiStatus);

        CheckBox common=new CheckBox(activity);
        common.setText("Include very common words in vocabulary list");
        common.setChecked(SpanishStudyPrefs.includeCommon(activity));
        common.setOnCheckedChangeListener((v,c)->SpanishStudyPrefs.setIncludeCommon(activity,c));
        layout.addView(common);

        TextView vocabLabel=new TextView(activity);
        vocabLabel.setText("Vocabulary list size");
        layout.addView(vocabLabel);
        NumberPicker limit=new NumberPicker(activity);
        limit.setMinValue(10);
        limit.setMaxValue(100);
        limit.setValue(SpanishStudyPrefs.vocabLimit(activity));
        limit.setWrapSelectorWheel(false);
        limit.setOnValueChangedListener((p,o,n)->SpanishStudyPrefs.setVocabLimit(activity,n));
        layout.addView(limit,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));

        new AlertDialog.Builder(activity)
                .setTitle("Spanish study tools")
                .setView(layout)
                .setPositiveButton("Review vocabulary",(d,w)->openVocabularyReview(activity))
                .setNeutralButton("Clear known words",(d,w)->{
                    SpanishStudyPrefs.clearKnown(activity);
                    Toast.makeText(activity,"Known-word list cleared",Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Close",null)
                .show();
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
