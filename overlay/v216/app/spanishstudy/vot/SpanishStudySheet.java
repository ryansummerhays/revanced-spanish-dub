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
import android.view.View;
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

/** Focused UI for features that stock Morphe does not provide: bilingual subtitles and diagnostics. */
final class SpanishStudySheet {
    private SpanishStudySheet() {}

    static void show(Activity activity) {
        if (activity == null || activity.isFinishing()) return;

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
                "Uses Morphe's translated segment and timing",
                SpanishStudyPrefs.showSubtitles(activity),
                value -> SpanishStudyPrefs.setShowSubtitles(activity, value)));
        content.addView(switchRow(activity, fg, "English subtitles",
                "Shows the exact matching source segment underneath",
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

        TextView note = new TextView(activity);
        note.setText("v2.16 deliberately leaves Morphe's caption segmentation, translation batching, seek prioritization, Edge TTS cache/prefetch and playback timing untouched. This layer only displays the source and translated Morphe segments together.");
        note.setTextColor(secondary);
        note.setTextSize(12);
        note.setPadding(0, Dim.dp8, 0, Dim.dp12);
        content.addView(note);

        content.addView(section(activity, "Diagnostics", secondary));
        LinearLayout diagnostics = valueRow(activity, fg, "Runtime diagnostics", "Open");
        diagnostics.setOnClickListener(v -> showDiagnostics(activity));
        content.addView(diagnostics);

        root.addView(scroll);
        SheetBottomDialog.SlideDialog dialog = SheetBottomDialog
                .createSlideDialog(activity, root, fadeInDuration);
        PipDismissHelper.dismissOnPip(dialog);
        dialog.show();
    }

    private static void showDiagnostics(Activity activity) {
        String report = SpanishStudyController.buildDiagnostics();
        TextView text = new TextView(activity);
        text.setText(report);
        text.setTextIsSelectable(true);
        text.setTextSize(11);
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
