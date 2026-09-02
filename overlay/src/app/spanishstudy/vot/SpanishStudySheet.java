package app.spanishstudy.vot;

import static app.morphe.extension.youtube.videoplayer.LegacyPlayerControlButton.fadeInDuration;
import static app.morphe.extension.youtube.videoplayer.LegacyPlayerControlButton.getDialogBackgroundColor;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.view.Gravity;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.function.IntConsumer;

import app.morphe.extension.shared.ui.Dim;
import app.morphe.extension.shared.ui.SheetBottomDialog;
import app.morphe.extension.shared.theme.ThemeUtils;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;
import app.morphe.extension.youtube.settings.Settings;
import app.morphe.extension.youtube.shared.PipDismissHelper;

/** Native-style bottom sheet for the Spanish study controls. */
final class SpanishStudySheet {
    private SpanishStudySheet(){}

    static void show(Activity activity){
        if(activity==null||activity.isFinishing())return;

        final int fg=ThemeUtils.getAppForegroundColor();
        final int secondary=secondaryColor(fg);
        SheetBottomDialog.DraggableLinearLayout root=SheetBottomDialog
                .createMainLayout(activity,getDialogBackgroundColor());

        TextView title=new TextView(activity);
        title.setText("Spanish study");
        title.setTextColor(fg);
        title.setTextSize(20);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setPadding(Dim.dp16,Dim.dp8,Dim.dp16,Dim.dp12);
        root.addView(title);

        ScrollView scroll=new ScrollView(activity);
        LinearLayout content=new LinearLayout(activity);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(Dim.dp16,0,Dim.dp16,Dim.dp16);
        scroll.addView(content);

        content.addView(section(activity,"Subtitles",secondary));
        content.addView(switchRow(activity,fg,"Spanish subtitles",
                "Translated text matched to the Spanish dub",
                SpanishStudyPrefs.showSubtitles(activity),
                checked->SpanishStudyPrefs.setShowSubtitles(activity,checked)));
        content.addView(switchRow(activity,fg,"English subtitles",
                "Original English YouTube transcript rendered by this patch",
                SpanishStudyPrefs.showEnglishSubtitles(activity),
                checked->SpanishStudyPrefs.setShowEnglishSubtitles(activity,checked)));

        content.addView(sliderRow(activity,fg,"Spanish text size","sp",8,18,
                SpanishStudyPrefs.subtitleTextSize(activity),
                value->SpanishStudyPrefs.setSubtitleTextSize(activity,value)));
        content.addView(sliderRow(activity,fg,"Spanish vertical position","dp from bottom",24,240,
                SpanishStudyPrefs.spanishSubtitleBottom(activity),
                value->SpanishStudyPrefs.setSpanishSubtitleBottom(activity,value)));
        content.addView(sliderRow(activity,fg,"English text size","sp",8,18,
                SpanishStudyPrefs.englishSubtitleTextSize(activity),
                value->SpanishStudyPrefs.setEnglishSubtitleTextSize(activity,value)));
        content.addView(sliderRow(activity,fg,"English vertical position","dp from bottom",24,240,
                SpanishStudyPrefs.englishSubtitleBottom(activity),
                value->SpanishStudyPrefs.setEnglishSubtitleBottom(activity,value)));
        content.addView(sliderRow(activity,fg,"Words shown at once","words",4,12,
                SpanishStudyPrefs.subtitleWords(activity),
                value->SpanishStudyPrefs.setSubtitleWords(activity,value)));

        TextView captionNote=new TextView(activity);
        captionNote.setText("English uses the same YouTube caption transcript used for dubbing, so both languages can be sized and positioned independently. If YouTube's own CC is already on for the current video, turn CC off once to avoid a duplicate English line.");
        captionNote.setTextColor(secondary);
        captionNote.setTextSize(12);
        captionNote.setPadding(0,Dim.dp8,0,Dim.dp12);
        content.addView(captionNote);

        content.addView(section(activity,"Translation",secondary));
        LinearLayout geminiRow=valueRow(activity,fg,"Gemini settings",
                SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty()
                        ? "Not configured"
                        : SpanishStudyPrefs.geminiModel(activity));
        geminiRow.setOnClickListener(v->SpanishStudyController.configureGemini(activity));
        content.addView(geminiRow);

        content.addView(section(activity,"Audio",secondary));
        content.addView(sliderRow(activity,fg,"Original audio under dub","%",0,100,
                Settings.VOT_ORIGINAL_AUDIO_VOLUME.get(),value->{
                    Settings.VOT_ORIGINAL_AUDIO_VOLUME.save(value);
                    VoiceOverTranslationPatch.updateOriginalAudioMultiplier();
                }));
        TextView bgmNote=new TextView(activity);
        bgmNote.setText("This is the practical BGM control: it changes the original video's volume while Spanish speech is playing. YouTube supplies music and English speech as one mixed track, so this cannot isolate music by itself.");
        bgmNote.setTextColor(secondary);
        bgmNote.setTextSize(12);
        bgmNote.setPadding(0,Dim.dp4,0,Dim.dp12);
        content.addView(bgmNote);

        content.addView(section(activity,"Vocabulary",secondary));
        content.addView(switchRow(activity,fg,"Include very common words",
                "Include words normally filtered from the review list",
                SpanishStudyPrefs.includeCommon(activity),
                checked->SpanishStudyPrefs.setIncludeCommon(activity,checked)));
        content.addView(sliderRow(activity,fg,"Vocabulary list size","words",10,100,
                SpanishStudyPrefs.vocabLimit(activity),
                value->SpanishStudyPrefs.setVocabLimit(activity,value)));

        final SheetBottomDialog.SlideDialog[] dialogRef={null};
        LinearLayout review=valueRow(activity,fg,"Review vocabulary","Open");
        review.setOnClickListener(v->{
            if(dialogRef[0]!=null)dialogRef[0].dismiss();
            SpanishStudyController.openVocabularyReview(activity);
        });
        content.addView(review);

        LinearLayout clear=valueRow(activity,fg,"Clear known words","Reset");
        clear.setOnClickListener(v->{
            SpanishStudyPrefs.clearKnown(activity);
            Toast.makeText(activity,"Known-word list cleared",Toast.LENGTH_SHORT).show();
        });
        content.addView(clear);

        root.addView(scroll);
        SheetBottomDialog.SlideDialog dialog=SheetBottomDialog
                .createSlideDialog(activity,root,fadeInDuration);
        dialogRef[0]=dialog;
        PipDismissHelper.dismissOnPip(dialog);
        dialog.show();
    }

    private static TextView section(Activity activity,String text,int color){
        TextView view=new TextView(activity);
        view.setText(text);
        view.setTextColor(color);
        view.setTextSize(13);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setPadding(0,Dim.dp16,0,Dim.dp4);
        return view;
    }

    private interface BoolConsumer{void accept(boolean value);}

    private static LinearLayout switchRow(Activity activity,int fg,String label,String description,
                                          boolean checked,BoolConsumer consumer){
        LinearLayout row=new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Dim.dp48+Dim.dp8);

        LinearLayout textBox=new LinearLayout(activity);
        textBox.setOrientation(LinearLayout.VERTICAL);
        textBox.setLayoutParams(new LinearLayout.LayoutParams(0,LinearLayout.LayoutParams.WRAP_CONTENT,1f));
        TextView labelView=new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(16);
        textBox.addView(labelView);
        TextView descView=new TextView(activity);
        descView.setText(description);
        descView.setTextColor(secondaryColor(fg));
        descView.setTextSize(12);
        textBox.addView(descView);
        row.addView(textBox);

        Switch toggle=new Switch(activity);
        toggle.setChecked(checked);
        toggle.setOnCheckedChangeListener((button,value)->consumer.accept(value));
        row.addView(toggle);
        return row;
    }

    private static LinearLayout sliderRow(Activity activity,int fg,String label,String suffix,
                                          int min,int max,int value,IntConsumer consumer){
        LinearLayout box=new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(0,Dim.dp6,0,Dim.dp6);

        LinearLayout header=new LinearLayout(activity);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView labelView=new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(15);
        labelView.setLayoutParams(new LinearLayout.LayoutParams(0,LinearLayout.LayoutParams.WRAP_CONTENT,1f));
        header.addView(labelView);
        TextView valueView=new TextView(activity);
        valueView.setText(value+" "+suffix);
        valueView.setTextColor(secondaryColor(fg));
        valueView.setTextSize(13);
        header.addView(valueView);
        box.addView(header);

        SeekBar seek=new SeekBar(activity);
        seek.setMax(max-min);
        seek.setProgress(Math.max(0,Math.min(max-min,value-min)));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            @Override public void onProgressChanged(SeekBar bar,int progress,boolean fromUser){
                int actual=min+progress;
                valueView.setText(actual+" "+suffix);
                if(fromUser)consumer.accept(actual);
            }
            @Override public void onStartTrackingTouch(SeekBar bar){}
            @Override public void onStopTrackingTouch(SeekBar bar){}
        });
        box.addView(seek);
        return box;
    }

    private static LinearLayout valueRow(Activity activity,int fg,String label,String value){
        LinearLayout row=new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Dim.dp48);
        TextView labelView=new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(16);
        labelView.setLayoutParams(new LinearLayout.LayoutParams(0,LinearLayout.LayoutParams.WRAP_CONTENT,1f));
        row.addView(labelView);
        TextView valueView=new TextView(activity);
        valueView.setText(value+"  ›");
        valueView.setTextColor(secondaryColor(fg));
        valueView.setTextSize(14);
        row.addView(valueView);
        return row;
    }

    private static int secondaryColor(int fg){
        return Color.argb(170,Color.red(fg),Color.green(fg),Color.blue(fg));
    }
}
