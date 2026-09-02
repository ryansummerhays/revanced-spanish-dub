package app.spanishstudy.vot;

import android.app.Activity;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Displays one complete English source clause and its complete Spanish translation on one clock.
 *
 * v2.2.3 deliberately does NOT divide each language independently by word count. The source
 * transcript is split into compact semantic clauses before translation. Each clause is translated
 * 1:1, receives one immutable source time slot, and both boxes change on that same slot boundary.
 * Pausing therefore shows the complete meaning pair instead of two proportional word fragments.
 */
final class SpanishSubtitleOverlay {
    private static Activity activity;
    private static TextView spanishView;
    private static TextView englishView;
    private static List<TranscriptSegment> spanishSegments = new ArrayList<>();
    private static List<TranscriptSegment> englishSegments = new ArrayList<>();
    private static int sourceCursor;

    private SpanishSubtitleOverlay() {}

    static void setSegments(List<TranscriptSegment> snapshot) {
        spanishSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
    }

    static void setSourceSegments(List<TranscriptSegment> snapshot) {
        englishSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        sourceCursor = 0;
    }

    static void update(Activity a, long timeMs) {
        if (a == null || a.isFinishing() || a.isDestroyed()) return;
        ensureAttached(a);
        updateLayout(a);

        final int index = findSourceIndex(timeMs);
        if (index < 0) {
            hidePair();
            return;
        }

        TranscriptSegment english = englishSegments.get(index);
        TranscriptSegment spanish = matchingSpanish(index, english);
        updatePair(a, english, spanish);
    }

    private static void updatePair(Activity a,
                                   TranscriptSegment english,
                                   TranscriptSegment spanish) {
        String englishText = english == null || english.text == null ? "" : english.text.trim();
        String spanishText = spanish == null || spanish.text == null ? "" : spanish.text.trim();

        if (SpanishStudyPrefs.showEnglishSubtitles(a)
                && english != null
                && english.lang != null
                && english.lang.toLowerCase().startsWith("en")
                && !englishText.isBlank()) {
            if (!englishText.contentEquals(englishView.getText())) englishView.setText(englishText);
            englishView.setVisibility(View.VISIBLE);
        } else {
            englishView.setVisibility(View.GONE);
        }

        if (SpanishStudyPrefs.showSubtitles(a)
                && spanish != null
                && spanish.lang != null
                && spanish.lang.toLowerCase().startsWith("es")
                && !spanishText.isBlank()) {
            if (!spanishText.contentEquals(spanishView.getText())) spanishView.setText(spanishText);
            spanishView.setVisibility(View.VISIBLE);
        } else {
            spanishView.setVisibility(View.GONE);
        }
    }

    /** The English/source clause is the single timing authority for both languages. */
    private static int findSourceIndex(long timeMs) {
        List<TranscriptSegment> local = englishSegments;
        if (local.isEmpty()) return -1;
        if (sourceCursor >= local.size()) sourceCursor = local.size() - 1;

        while (sourceCursor > 0 && timeMs < local.get(sourceCursor).startMs) sourceCursor--;
        while (sourceCursor + 1 < local.size() && timeMs >= local.get(sourceCursor).endMs) sourceCursor++;

        TranscriptSegment source = local.get(sourceCursor);
        return timeMs >= source.startMs && timeMs < source.endMs ? sourceCursor : -1;
    }

    /**
     * Translation preserves 1:1 clause ordering. Timestamp lookup is retained as a safe fallback
     * if a provider publishes an otherwise equivalent snapshot with a different list position.
     */
    private static TranscriptSegment matchingSpanish(int sourceIndex, TranscriptSegment source) {
        if (sourceIndex >= 0 && sourceIndex < spanishSegments.size()) {
            TranscriptSegment candidate = spanishSegments.get(sourceIndex);
            if (candidate.startMs == source.startMs && candidate.endMs == source.endMs) return candidate;
        }
        for (TranscriptSegment candidate : spanishSegments) {
            if (candidate.startMs == source.startMs && candidate.endMs == source.endMs) return candidate;
        }
        return null;
    }

    static void hide() {
        hidePair();
    }

    private static void hidePair() {
        if (spanishView != null) spanishView.setVisibility(View.GONE);
        if (englishView != null) englishView.setVisibility(View.GONE);
    }

    private static void ensureAttached(Activity a) {
        if (spanishView != null && englishView != null && activity == a
                && spanishView.getParent() != null && englishView.getParent() != null) return;
        detach(spanishView);
        detach(englishView);
        activity = a;
        spanishView = createTextView(a);
        englishView = createTextView(a);
        addView(a, spanishView, SpanishStudyPrefs.spanishSubtitleBottom(a));
        addView(a, englishView, SpanishStudyPrefs.englishSubtitleBottom(a));
    }

    private static TextView createTextView(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        // Clauses are intentionally compact, but allow a third line so no relevant words are
        // silently clipped when Spanish expands relative to English.
        view.setMaxLines(3);
        view.setPadding(dp(a, 8), dp(a, 4), dp(a, 8), dp(a, 4));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xB8000000);
        bg.setCornerRadius(dp(a, 6));
        view.setBackground(bg);
        view.setElevation(dp(a, 6));
        view.setVisibility(View.GONE);
        return view;
    }

    private static void addView(Activity a, TextView view, int bottomDp) {
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.leftMargin = dp(a, 28);
        lp.rightMargin = dp(a, 28);
        lp.bottomMargin = dp(a, bottomDp);
        a.addContentView(view, lp);
    }

    private static void updateLayout(Activity a) {
        spanishView.setTextSize(SpanishStudyPrefs.subtitleTextSize(a));
        englishView.setTextSize(SpanishStudyPrefs.englishSubtitleTextSize(a));
        updateBottomMargin(a, spanishView, SpanishStudyPrefs.spanishSubtitleBottom(a));
        updateBottomMargin(a, englishView, SpanishStudyPrefs.englishSubtitleBottom(a));
    }

    private static void updateBottomMargin(Activity a, TextView view, int bottomDp) {
        ViewGroup.LayoutParams raw = view.getLayoutParams();
        if (raw instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) raw;
            int wanted = dp(a, bottomDp);
            if (lp.bottomMargin != wanted) {
                lp.bottomMargin = wanted;
                view.setLayoutParams(lp);
            }
        }
    }

    private static void detach(TextView view) {
        if (view != null && view.getParent() instanceof ViewGroup)
            ((ViewGroup) view.getParent()).removeView(view);
    }

    private static int dp(Activity a, int v) {
        return Math.round(v * a.getResources().getDisplayMetrics().density);
    }
}
