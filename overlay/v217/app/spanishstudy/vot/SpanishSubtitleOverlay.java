package app.spanishstudy.vot;

import android.app.Activity;
import android.content.res.Configuration;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Iterator;
import java.util.List;
import java.util.Map;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Bilingual subtitle UI layered on Morphe's native transcript. English follows source-caption
 * timing. Spanish normally follows the same source timing, but once Morphe starts TTS the Spanish
 * line remains visible through Morphe's own effective TTS end time.
 */
final class SpanishSubtitleOverlay {
    private static final class TtsWindow {
        final long startMs;
        final long endMs;

        TtsWindow(long startMs, long endMs) {
            this.startMs = startMs;
            this.endMs = endMs;
        }
    }

    private static Activity activity;
    private static LinearLayout pairView;
    private static TextView translatedView;
    private static TextView sourceView;
    private static List<TranscriptSegment> translatedSegments = new ArrayList<>();
    private static List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static final Map<Integer, TtsWindow> ttsWindows = new HashMap<>();
    private static int sourceCursor;

    private SpanishSubtitleOverlay() {}

    static void setTranslatedSegments(List<TranscriptSegment> snapshot) {
        translatedSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
    }

    static void setSourceSegments(List<TranscriptSegment> snapshot) {
        sourceSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        sourceCursor = 0;
        ttsWindows.clear();
    }

    static void setTtsWindow(int index, long startMs, long endMs) {
        if (index < 0 || endMs <= startMs) return;
        Iterator<Map.Entry<Integer, TtsWindow>> it = ttsWindows.entrySet().iterator();
        while (it.hasNext()) {
            TtsWindow old = it.next().getValue();
            if (old.endMs < startMs - 5_000L) it.remove();
        }
        ttsWindows.put(index, new TtsWindow(startMs, endMs));
    }

    static void update(Activity a, long timeMs) {
        if (a == null || a.isFinishing() || a.isDestroyed()) return;
        ensureAttached(a);
        updateLayout(a);

        int sourceIndex = findSourceIndex(timeMs);
        int translatedIndex = findTranslatedIndex(timeMs, sourceIndex);

        TranscriptSegment source = sourceIndex >= 0 && sourceIndex < sourceSegments.size()
                ? sourceSegments.get(sourceIndex) : null;
        TranscriptSegment translated = matchingTranslated(translatedIndex);
        String sourceText = source == null || source.text == null ? "" : source.text.trim();
        String translatedText = translated == null || translated.text == null ? "" : translated.text.trim();

        if (SpanishStudyPrefs.showSubtitles(a)
                && translated != null
                && translated.lang != null
                && translated.lang.toLowerCase().startsWith("es")
                && !translatedText.isBlank()) {
            if (!translatedText.contentEquals(translatedView.getText())) translatedView.setText(translatedText);
            translatedView.setVisibility(View.VISIBLE);
        } else {
            translatedView.setVisibility(View.GONE);
        }

        if (SpanishStudyPrefs.showEnglishSubtitles(a)
                && source != null
                && source.lang != null
                && source.lang.toLowerCase().startsWith("en")
                && !sourceText.isBlank()) {
            if (!sourceText.contentEquals(sourceView.getText())) sourceView.setText(sourceText);
            sourceView.setVisibility(View.VISIBLE);
        } else {
            sourceView.setVisibility(View.GONE);
        }

        pairView.setVisibility(translatedView.getVisibility() == View.VISIBLE
                || sourceView.getVisibility() == View.VISIBLE ? View.VISIBLE : View.GONE);
    }

    static void clear() {
        translatedSegments = new ArrayList<>();
        sourceSegments = new ArrayList<>();
        ttsWindows.clear();
        sourceCursor = 0;
        hidePair();
    }

    static void hide() {
        hidePair();
    }

    private static int findSourceIndex(long timeMs) {
        List<TranscriptSegment> local = sourceSegments;
        if (local.isEmpty()) return -1;
        if (sourceCursor >= local.size()) sourceCursor = local.size() - 1;
        while (sourceCursor > 0 && timeMs < local.get(sourceCursor).startMs) sourceCursor--;
        while (sourceCursor + 1 < local.size() && timeMs >= local.get(sourceCursor).endMs) sourceCursor++;
        TranscriptSegment source = local.get(sourceCursor);
        return timeMs >= source.startMs && timeMs < source.endMs ? sourceCursor : -1;
    }

    /** Prefer the currently spoken Morphe TTS segment; otherwise fall back to source cue timing. */
    private static int findTranslatedIndex(long timeMs, int sourceIndex) {
        int active = -1;
        long latestStart = Long.MIN_VALUE;
        for (Map.Entry<Integer, TtsWindow> entry : ttsWindows.entrySet()) {
            TtsWindow window = entry.getValue();
            if (timeMs >= window.startMs && timeMs < window.endMs && window.startMs >= latestStart) {
                active = entry.getKey();
                latestStart = window.startMs;
            }
        }
        return active >= 0 ? active : sourceIndex;
    }

    private static TranscriptSegment matchingTranslated(int index) {
        if (index < 0 || index >= translatedSegments.size() || index >= sourceSegments.size()) return null;
        TranscriptSegment source = sourceSegments.get(index);
        TranscriptSegment candidate = translatedSegments.get(index);
        if (candidate.startMs == source.startMs && candidate.endMs == source.endMs) return candidate;
        return null;
    }

    private static void ensureAttached(Activity a) {
        if (pairView != null && translatedView != null && sourceView != null
                && activity == a && pairView.getParent() != null) return;

        detach(pairView);
        activity = a;
        pairView = new LinearLayout(a);
        pairView.setOrientation(LinearLayout.VERTICAL);
        pairView.setGravity(Gravity.CENTER_HORIZONTAL);
        pairView.setVisibility(View.GONE);

        translatedView = createTextView(a);
        sourceView = createTextView(a);

        LinearLayout.LayoutParams top = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        top.gravity = Gravity.CENTER_HORIZONTAL;
        pairView.addView(translatedView, top);

        LinearLayout.LayoutParams bottom = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bottom.gravity = Gravity.CENTER_HORIZONTAL;
        bottom.topMargin = dp(a, 2);
        pairView.addView(sourceView, bottom);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.leftMargin = dp(a, 28);
        lp.rightMargin = dp(a, 28);
        lp.bottomMargin = resolvedBottomMarginPx(a, SpanishStudyPrefs.subtitlePairBottom(a));
        a.addContentView(pairView, lp);
    }

    private static TextView createTextView(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setSingleLine(false);
        // v2.16 hard-capped this at two lines, which clipped longer Morphe sentence segments.
        // Four lines keeps the overlay bounded while allowing autosize to preserve the full cue.
        view.setMaxLines(4);
        view.setHorizontallyScrolling(false);
        view.setEllipsize(null);
        view.setPadding(dp(a, 8), dp(a, 3), dp(a, 8), dp(a, 3));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xB8000000);
        bg.setCornerRadius(dp(a, 6));
        view.setBackground(bg);
        view.setElevation(dp(a, 6));
        view.setVisibility(View.GONE);
        return view;
    }

    private static void updateLayout(Activity a) {
        updateTextSize(translatedView, SpanishStudyPrefs.subtitleTextSize(a));
        updateTextSize(sourceView, SpanishStudyPrefs.englishSubtitleTextSize(a));

        View content = a.findViewById(android.R.id.content);
        if (content != null && content.getWidth() > 0) {
            int maxWidth = Math.max(dp(a, 120), content.getWidth() - dp(a, 56));
            translatedView.setMaxWidth(maxWidth);
            sourceView.setMaxWidth(maxWidth);
        }

        ViewGroup.LayoutParams raw = pairView.getLayoutParams();
        if (raw instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) raw;
            int wanted = resolvedBottomMarginPx(a, SpanishStudyPrefs.subtitlePairBottom(a));
            if (lp.bottomMargin != wanted) {
                lp.bottomMargin = wanted;
                pairView.setLayoutParams(lp);
            }
        }
    }

    private static void updateTextSize(TextView view, int preferredSp) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            int minSp = Math.max(7, preferredSp - 4);
            view.setAutoSizeTextTypeUniformWithConfiguration(
                    minSp, Math.max(minSp, preferredSp), 1, TypedValue.COMPLEX_UNIT_SP);
        } else {
            view.setTextSize(TypedValue.COMPLEX_UNIT_SP, preferredSp);
        }
    }

    /** Keep the configured offset inside the video area in portrait; direct from bottom in landscape. */
    private static int resolvedBottomMarginPx(Activity a, int configuredBottomDp) {
        int basePx = dp(a, configuredBottomDp);
        if (a.getResources().getConfiguration().orientation != Configuration.ORIENTATION_PORTRAIT) {
            return basePx;
        }
        View content = a.findViewById(android.R.id.content);
        if (content == null || content.getWidth() <= 0 || content.getHeight() <= content.getWidth()) return basePx;
        int playerHeight = Math.min(content.getHeight(), Math.round(content.getWidth() * 9f / 16f));
        float scale = playerHeight / (float) Math.max(1, content.getWidth());
        return Math.max(0, content.getHeight() - playerHeight + Math.round(basePx * scale));
    }

    private static void hidePair() {
        if (translatedView != null) translatedView.setVisibility(View.GONE);
        if (sourceView != null) sourceView.setVisibility(View.GONE);
        if (pairView != null) pairView.setVisibility(View.GONE);
    }

    private static void detach(View view) {
        if (view != null && view.getParent() instanceof ViewGroup) {
            ((ViewGroup) view.getParent()).removeView(view);
        }
    }

    private static int dp(Activity a, int value) {
        return Math.round(value * a.getResources().getDisplayMetrics().density);
    }
}