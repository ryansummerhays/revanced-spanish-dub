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
import java.util.List;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Professional-style bilingual study subtitles.
 *
 * Each event is one short semantic sentence/clause. Spanish is always the top line and the matching
 * English source is immediately below it. Both lines use the exact same immutable source event and
 * switch at the exact same instant. Each language is restricted to one line; semantic segmentation
 * targets 25-38 characters and normally caps source events at 42 characters before translation.
 *
 * The pair has one shared vertical anchor, which prevents the two languages from drifting apart
 * spatially and lets portrait mode map the whole pair proportionally into YouTube's smaller player.
 */
final class SpanishSubtitleOverlay {
    private static Activity activity;
    private static LinearLayout pairView;
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

        // Spanish is intentionally the first/top line: dual-subtitle viewers tend to give the top
        // line more visual attention, and Spanish is the target language for this study mode.
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

        if (pairView != null) {
            pairView.setVisibility(spanishView.getVisibility() == View.VISIBLE
                    || englishView.getVisibility() == View.VISIBLE ? View.VISIBLE : View.GONE);
        }
    }

    /** The English/source event is the single timing authority for both languages. */
    private static int findSourceIndex(long timeMs) {
        List<TranscriptSegment> local = englishSegments;
        if (local.isEmpty()) return -1;
        if (sourceCursor >= local.size()) sourceCursor = local.size() - 1;

        while (sourceCursor > 0 && timeMs < local.get(sourceCursor).startMs) sourceCursor--;
        while (sourceCursor + 1 < local.size() && timeMs >= local.get(sourceCursor).endMs) sourceCursor++;

        TranscriptSegment source = local.get(sourceCursor);
        return timeMs >= source.startMs && timeMs < source.endMs ? sourceCursor : -1;
    }

    /** Translation preserves 1:1 ordering; timestamps are a safe matching fallback. */
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
        if (pairView != null) pairView.setVisibility(View.GONE);
    }

    private static void ensureAttached(Activity a) {
        if (pairView != null && spanishView != null && englishView != null && activity == a
                && pairView.getParent() != null) return;

        detach(pairView);
        activity = a;

        pairView = new LinearLayout(a);
        pairView.setOrientation(LinearLayout.VERTICAL);
        pairView.setGravity(Gravity.CENTER_HORIZONTAL);
        pairView.setVisibility(View.GONE);

        spanishView = createTextView(a);
        englishView = createTextView(a);

        LinearLayout.LayoutParams spanishLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        spanishLp.gravity = Gravity.CENTER_HORIZONTAL;
        pairView.addView(spanishView, spanishLp);

        LinearLayout.LayoutParams englishLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        englishLp.gravity = Gravity.CENTER_HORIZONTAL;
        englishLp.topMargin = dp(a, 2);
        pairView.addView(englishView, englishLp);

        addPairView(a);
    }

    private static TextView createTextView(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setSingleLine(true);
        view.setMaxLines(1);
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

    private static void addPairView(Activity a) {
        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.leftMargin = dp(a, 28);
        lp.rightMargin = dp(a, 28);
        lp.bottomMargin = resolvedBottomMarginPx(a, SpanishStudyPrefs.subtitlePairBottom(a));
        a.addContentView(pairView, lp);
    }

    private static void updateLayout(Activity a) {
        updateTextSize(spanishView, SpanishStudyPrefs.subtitleTextSize(a));
        updateTextSize(englishView, SpanishStudyPrefs.englishSubtitleTextSize(a));

        View content = a.findViewById(android.R.id.content);
        if (content != null && content.getWidth() > 0) {
            int maxTextWidth = Math.max(dp(a, 120), content.getWidth() - dp(a, 56));
            spanishView.setMaxWidth(maxTextWidth);
            englishView.setMaxWidth(maxTextWidth);
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
            // A short translation may expand slightly versus English. Shrink only enough to keep a
            // professional single line; segmentation/concise translation should do most of the work.
            int minSp = Math.max(8, preferredSp - 3);
            view.setAutoSizeTextTypeUniformWithConfiguration(
                    minSp, Math.max(minSp, preferredSp), 1, TypedValue.COMPLEX_UNIT_SP);
        } else {
            view.setTextSize(TypedValue.COMPLEX_UNIT_SP, preferredSp);
        }
    }

    /**
     * Landscape/fullscreen uses the saved shared position directly. In portrait we find YouTube's
     * actual player-controls view, scale that position by current player height, and anchor the pair
     * to the real player bottom. If controls are not ready, use a temporary 16:9 estimate.
     */
    private static int resolvedBottomMarginPx(Activity a, int configuredBottomDp) {
        final int basePx = dp(a, configuredBottomDp);
        if (a.getResources().getConfiguration().orientation != Configuration.ORIENTATION_PORTRAIT) {
            return basePx;
        }

        View content = a.findViewById(android.R.id.content);
        int width = content == null ? 0 : content.getWidth();
        int height = content == null ? 0 : content.getHeight();
        if (width <= 0 || height <= 0 || height <= width) return basePx;

        int playerHeight = 0;
        int playerBottom = 0;
        View player = SpanishStudyController.playerControlsView();
        if (player != null && player.getWidth() > 0 && player.getHeight() > 0) {
            int[] contentPos = new int[2];
            int[] playerPos = new int[2];
            content.getLocationInWindow(contentPos);
            player.getLocationInWindow(playerPos);
            playerHeight = player.getHeight();
            playerBottom = playerPos[1] - contentPos[1] + playerHeight;
            if (playerBottom <= 0 || playerBottom > height + playerHeight) {
                playerHeight = 0;
                playerBottom = 0;
            }
        }

        if (playerHeight <= 0) {
            playerHeight = Math.min(height, Math.round(width * 9f / 16f));
            playerBottom = playerHeight;
        }

        float playerScale = playerHeight / (float) Math.max(1, width);
        int withinPlayer = Math.round(basePx * playerScale);
        return Math.max(0, height - playerBottom + withinPlayer);
    }

    private static void detach(View view) {
        if (view != null && view.getParent() instanceof ViewGroup)
            ((ViewGroup) view.getParent()).removeView(view);
    }

    private static int dp(Activity a, int v) {
        return Math.round(v * a.getResources().getDisplayMetrics().density);
    }
}
