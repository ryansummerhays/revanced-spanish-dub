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
                "Target-language line shown on top",
                SpanishStudyPrefs.showSubtitles(activity),
                checked->SpanishStudyPrefs.setShowSubtitles(activity,checked)));
        content.addView(switchRow(activity,fg,"English subtitles",
                "Matching source line shown directly underneath",
                SpanishStudyPrefs.showEnglishSubtitles(activity),
                checked->SpanishStudyPrefs.setShowEnglishSubtitles(activity,checked)));

        content.addView(sliderRow(activity,fg,"Spanish text size","sp",8,18,
                SpanishStudyPrefs.subtitleTextSize(activity),
                value->SpanishStudyPrefs.setSubtitleTextSize(activity,value)));
        content.addView(sliderRow(activity,fg,"English text size","sp",8,18,
                SpanishStudyPrefs.englishSubtitleTextSize(activity),
                value->SpanishStudyPrefs.setEnglishSubtitleTextSize(activity,value)));
        content.addView(sliderRow(activity,fg,"Bilingual vertical position","dp",24,240,
                SpanishStudyPrefs.subtitlePairBottom(activity),
                value->SpanishStudyPrefs.setSubtitlePairBottom(activity,value)));

        TextView captionNote=new TextView(activity);
        captionNote.setText("Professional bilingual layout: Spanish on top, English directly below, one line per language, and both switch on the same source-video clause boundary. Short sentences stay whole; longer speech is split at natural clause boundaries, targeting about 25–38 characters with a normal 42-character one-line ceiling. The pair position is saved and scales into the smaller portrait player. If YouTube CC is already on, turn it off once to avoid duplicate English subtitles.");
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

        TextView audioNote=new TextView(activity);
        audioNote.setText("Original-audio volume and max speech rate remain in Morphe's normal voice-over settings. The source video timeline remains authoritative; translated speech adapts to it rather than moving subtitle timing.");
        audioNote.setTextColor(secondary);
        audioNote.setTextSize(12);
        audioNote.setPadding(0,Dim.dp8,0,Dim.dp4);
        content.addView(audioNote);

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
