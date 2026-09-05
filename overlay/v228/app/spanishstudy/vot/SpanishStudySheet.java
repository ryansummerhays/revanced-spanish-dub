package app.spanishstudy.vot;

import static app.morphe.extension.youtube.videoplayer.LegacyPlayerControlButton.fadeInDuration;
import static app.morphe.extension.youtube.videoplayer.LegacyPlayerControlButton.getDialogBackgroundColor;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
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

import app.morphe.extension.shared.theme.ThemeUtils;
import app.morphe.extension.shared.ui.Dim;
import app.morphe.extension.shared.ui.SheetBottomDialog;
import app.morphe.extension.youtube.shared.PipDismissHelper;

/** Spanish study controls, local speaker experiment, and component-selectable diagnostics. */
final class SpanishStudySheet {
    private SpanishStudySheet() {}

    static void show(Activity activity) {
        if (activity == null || activity.isFinishing()) return;
        SpanishStudyPrefs.applyDiagnosticConfig(activity);

        int fg = ThemeUtils.getAppForegroundColor();
        int secondary = secondaryColor(fg);
        SheetBottomDialog.DraggableLinearLayout root = SheetBottomDialog
                .createMainLayout(activity, getDialogBackgroundColor());

        TextView title = new TextView(activity);
        title.setText("Spanish study");
        title.setTextColor(fg);
        title.setTextSize(20);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        title.setPadding(Dim.dp16, Dim.dp8, Dim.dp16, Dim.dp12);
        root.addView(title);

        ScrollView scroll = new ScrollView(activity);
        LinearLayout content = new LinearLayout(activity);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(Dim.dp16, 0, Dim.dp16, Dim.dp16);
        scroll.addView(content);

        content.addView(section(activity, "Bilingual subtitles", secondary));
        content.addView(switchRow(activity, fg, "Spanish subtitles",
                "Displays Morphe's translated text without changing speech",
                SpanishStudyPrefs.showSubtitles(activity),
                value -> SpanishStudyPrefs.setShowSubtitles(activity, value)));
        content.addView(switchRow(activity, fg, "English subtitles",
                "Displays the matching source text underneath",
                SpanishStudyPrefs.showEnglishSubtitles(activity),
                value -> SpanishStudyPrefs.setShowEnglishSubtitles(activity, value)));
        content.addView(sliderRow(activity, fg, "Spanish text size", "sp", 8, 18,
                SpanishStudyPrefs.subtitleTextSize(activity),
                value -> SpanishStudyPrefs.setSubtitleTextSize(activity, value)));
        content.addView(sliderRow(activity, fg, "English text size", "sp", 8, 18,
                SpanishStudyPrefs.englishSubtitleTextSize(activity),
                value -> SpanishStudyPrefs.setEnglishSubtitleTextSize(activity, value)));
        content.addView(sliderRow(activity, fg, "Subtitle position", "dp", 24, 240,
                SpanishStudyPrefs.subtitlePairBottom(activity),
                value -> SpanishStudyPrefs.setSubtitlePairBottom(activity, value)));

        content.addView(section(activity, "Local speaker experiment", secondary));
        content.addView(switchRow(activity, fg, "Detect speaker A/B locally",
                "$0 API cost. Reads YouTube's AudioTrack visualization session; no microphone. Labels only in v2.28.",
                SpanishStudyPrefs.speakerExperiment(activity), value -> {
                    SpanishStudyPrefs.setSpeakerExperiment(activity, value);
                    LocalSpeakerDiarizer.setEnabled(activity, value);
                }));
        TextView speakerNote = note(activity, secondary,
                "This is a capture/clustering probe, not the final sherpa-onnx model. The diagnostics report AudioTrack attach status, waveform/FFT callbacks, voiced frames, per-segment assignments, cluster creation and similarity scores.");
        content.addView(speakerNote);

        content.addView(section(activity, "Diagnostic components", secondary));
        content.addView(diagSwitch(activity, fg, "Lifecycle / seeks / playhead",
                "Video changes, session state, playhead and seek decisions",
                SpanishStudyPrefs.logLifecycle(activity), SpanishStudyPrefs::setLogLifecycle));
        content.addView(diagSwitch(activity, fg, "Captions / segmentation",
                "Caption fetch, source lines, merged sentence boundaries",
                SpanishStudyPrefs.logCaptions(activity), SpanishStudyPrefs::setLogCaptions));
        content.addView(diagSwitch(activity, fg, "Translation / OpenRouter",
                "Batch selection, request size, streaming progress, mismatches, HTTP and latency",
                SpanishStudyPrefs.logTranslation(activity), SpanishStudyPrefs::setLogTranslation));
        content.addView(diagSwitch(activity, fg, "TTS / prefetch / cache",
                "Speak decisions, cache hit/miss, synthesis, playback windows and rates",
                SpanishStudyPrefs.logTts(activity), SpanishStudyPrefs::setLogTts));
        content.addView(diagSwitch(activity, fg, "Subtitle rendering",
                "Segment/page choice, display timing and speaker badge changes",
                SpanishStudyPrefs.logSubtitles(activity), SpanishStudyPrefs::setLogSubtitles));
        content.addView(diagSwitch(activity, fg, "Audio capture",
                "AudioTrack session, Visualizer attach and callback health",
                SpanishStudyPrefs.logAudio(activity), SpanishStudyPrefs::setLogAudio));
        content.addView(diagSwitch(activity, fg, "Speaker clustering",
                "Voiced-frame accumulation, similarity and A/B/C/D decisions",
                SpanishStudyPrefs.logSpeaker(activity), SpanishStudyPrefs::setLogSpeaker));
        content.addView(diagSwitch(activity, fg, "Include transcript text",
                "Adds truncated source/translation text to logs. Off by default to keep reports smaller.",
                SpanishStudyPrefs.logText(activity), SpanishStudyPrefs::setLogText));

        TextView note = note(activity, secondary,
                "v2.28 keeps Mistral/OpenRouter and Morphe's normal sentence-sized VOT speech. Diagnostic hooks are intended to observe the pipeline, not change its decisions.");
        content.addView(note);

        content.addView(section(activity, "Diagnostic report", secondary));
        LinearLayout diagnostics = valueRow(activity, fg, "Runtime diagnostics", "Open / copy");
        diagnostics.setOnClickListener(v -> showDiagnostics(activity));
        content.addView(diagnostics);
        LinearLayout clear = valueRow(activity, fg, "Clear event buffer", "Clear");
        clear.setOnClickListener(v -> {
            SpanishStudyDiagnostics.clear();
            Toast.makeText(activity, "Diagnostic events cleared", Toast.LENGTH_SHORT).show();
        });
        content.addView(clear);

        root.addView(scroll);
        SheetBottomDialog.SlideDialog dialog = SheetBottomDialog
                .createSlideDialog(activity, root, fadeInDuration);
        PipDismissHelper.dismissOnPip(dialog);
        dialog.show();
    }

    private interface PrefSetter { void set(Context context, boolean value); }

    private static LinearLayout diagSwitch(Activity activity, int fg, String label, String desc,
                                           boolean checked, PrefSetter setter) {
        return switchRow(activity, fg, label, desc, checked, value -> {
            setter.set(activity, value);
            SpanishStudyPrefs.applyDiagnosticConfig(activity);
        });
    }

    private static TextView note(Activity activity, int color, String text) {
        TextView v = new TextView(activity);
        v.setText(text);
        v.setTextColor(color);
        v.setTextSize(12);
        v.setPadding(0, Dim.dp8, 0, Dim.dp12);
        return v;
    }

    private static void showDiagnostics(Activity activity) {
        SpanishStudyPrefs.applyDiagnosticConfig(activity);
        String report = SpanishStudyController.buildDiagnostics();
        TextView text = new TextView(activity);
        text.setText(report);
        text.setTextIsSelectable(true);
        text.setTextSize(10);
        text.setPadding(Dim.dp16, Dim.dp8, Dim.dp16, Dim.dp8);
        ScrollView scroll = new ScrollView(activity);
        scroll.addView(text);

        new AlertDialog.Builder(activity)
                .setTitle("Spanish Dub Study diagnostics")
                .setView(scroll)
                .setPositiveButton("Copy", (dialog, which) -> {
                    ClipboardManager clipboard = (ClipboardManager) activity.getSystemService(Context.CLIPBOARD_SERVICE);
                    if (clipboard != null) {
                        clipboard.setPrimaryClip(ClipData.newPlainText("Spanish Dub Study diagnostics", report));
                        Toast.makeText(activity, "Diagnostics copied", Toast.LENGTH_SHORT).show();
                    }
                })
                .setNegativeButton("Close", null)
                .show();
    }

    private static TextView section(Activity activity, String text, int color) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextColor(color);
        view.setTextSize(13);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setPadding(0, Dim.dp16, 0, Dim.dp4);
        return view;
    }

    private interface BoolConsumer { void accept(boolean value); }

    private static LinearLayout switchRow(Activity activity, int fg, String label, String description,
                                          boolean checked, BoolConsumer consumer) {
        LinearLayout row = new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Dim.dp48 + Dim.dp8);

        LinearLayout textBox = new LinearLayout(activity);
        textBox.setOrientation(LinearLayout.VERTICAL);
        textBox.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        TextView labelView = new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(16);
        textBox.addView(labelView);
        TextView descView = new TextView(activity);
        descView.setText(description);
        descView.setTextColor(secondaryColor(fg));
        descView.setTextSize(12);
        textBox.addView(descView);
        row.addView(textBox);

        Switch toggle = new Switch(activity);
        toggle.setChecked(checked);
        toggle.setOnCheckedChangeListener((button, value) -> consumer.accept(value));
        row.addView(toggle);
        return row;
    }

    private static LinearLayout sliderRow(Activity activity, int fg, String label, String suffix,
                                          int min, int max, int value, IntConsumer consumer) {
        LinearLayout box = new LinearLayout(activity);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(0, Dim.dp6, 0, Dim.dp6);
        LinearLayout header = new LinearLayout(activity);
        header.setOrientation(LinearLayout.HORIZONTAL);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView labelView = new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(15);
        labelView.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        header.addView(labelView);
        TextView valueView = new TextView(activity);
        valueView.setText(value + " " + suffix);
        valueView.setTextColor(secondaryColor(fg));
        valueView.setTextSize(13);
        header.addView(valueView);
        box.addView(header);

        SeekBar seek = new SeekBar(activity);
        seek.setMax(max - min);
        seek.setProgress(Math.max(0, Math.min(max - min, value - min)));
        seek.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                int actual = min + progress;
                valueView.setText(actual + " " + suffix);
                if (fromUser) consumer.accept(actual);
            }
            @Override public void onStartTrackingTouch(SeekBar bar) {}
            @Override public void onStopTrackingTouch(SeekBar bar) {}
        });
        box.addView(seek);
        return box;
    }

    private static LinearLayout valueRow(Activity activity, int fg, String label, String value) {
        LinearLayout row = new LinearLayout(activity);
        row.setOrientation(LinearLayout.HORIZONTAL);
        row.setGravity(Gravity.CENTER_VERTICAL);
        row.setMinimumHeight(Dim.dp48);
        TextView labelView = new TextView(activity);
        labelView.setText(label);
        labelView.setTextColor(fg);
        labelView.setTextSize(16);
        labelView.setLayoutParams(new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f));
        row.addView(labelView);
        TextView valueView = new TextView(activity);
        valueView.setText(value + "  ›");
        valueView.setTextColor(secondaryColor(fg));
        valueView.setTextSize(14);
        row.addView(valueView);
        return row;
    }

    private static int secondaryColor(int fg) {
        return Color.argb(170, Color.red(fg), Color.green(fg), Color.blue(fg));
    }
}
