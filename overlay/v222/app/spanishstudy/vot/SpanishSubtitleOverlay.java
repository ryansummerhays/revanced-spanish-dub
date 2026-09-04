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
 * Readable bilingual subtitle view over Morphe's unchanged transcript/TTS segments.
 *
 * v2.22 deliberately treats actual dub audio playback as the subtitle clock. When translated
 * Spanish exists but Edge audio has not really started yet, both cards stay on their first page
 * instead of racing ahead on source-video time. Once MediaPlayer starts, both languages advance
 * from that same audible progress. The source-only fallback still follows source time.
 */
final class SpanishSubtitleOverlay {
    private static final class TtsWindow {
        final long startMs;
        final long endMs;
        final double startProgress;

        TtsWindow(long startMs, long endMs, double startProgress) {
            this.startMs = startMs;
            this.endMs = endMs;
            this.startProgress = Math.max(0.0, Math.min(1.0, startProgress));
        }

        boolean active(long timeMs) {
            return timeMs >= startMs && timeMs < endMs;
        }

        double progress(long timeMs) {
            if (timeMs <= startMs) return startProgress;
            if (timeMs >= endMs) return 1.0;
            return SubtitlePagePolicy.ttsProgress(timeMs, startMs, endMs, startProgress);
        }
    }

    private static final class ShownPage {
        final String text;
        final int pageIndex;
        final int pageCount;

        ShownPage(String text, int pageIndex, int pageCount) {
            this.text = text;
            this.pageIndex = pageIndex;
            this.pageCount = pageCount;
        }
    }

    private static Activity activity;
    private static LinearLayout pairView;
    private static LinearLayout spanishRow;
    private static TextView speakerBadgeView;
    private static TextView translatedView;
    private static TextView sourceView;
    private static List<TranscriptSegment> translatedSegments = new ArrayList<>();
    private static List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static final Map<Integer, TtsWindow> ttsWindows = new HashMap<>();
    private static final Map<Integer, List<SubtitlePagePolicy.Page>> translatedPages = new HashMap<>();
    private static final Map<Integer, List<SubtitlePagePolicy.Page>> sourcePages = new HashMap<>();
    private static final Map<Integer, Double> progressFloors = new HashMap<>();
    private static int sourceCursor;
    private static long lastUpdateTimeMs = Long.MIN_VALUE;
    private static int lastSpanishSegment = -1;
    private static int lastSpanishPage = -1;
    private static int lastEnglishSegment = -1;
    private static int lastEnglishPage = -1;

    private SpanishSubtitleOverlay() {}

    static void setTranslatedSegments(List<TranscriptSegment> snapshot) {
        translatedSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        translatedPages.clear();
    }

    static void setSourceSegments(List<TranscriptSegment> snapshot) {
        sourceSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        sourceCursor = 0;
        ttsWindows.clear();
        sourcePages.clear();
        translatedPages.clear();
        progressFloors.clear();
        lastUpdateTimeMs = Long.MIN_VALUE;
        resetPageTelemetry();
    }

    /** Called only once the actual TTS MediaPlayer has started. */
    static void setTtsWindow(int index, long startMs, long endMs, double startProgress) {
        if (index < 0 || endMs <= startMs) return;
        Iterator<Map.Entry<Integer, TtsWindow>> it = ttsWindows.entrySet().iterator();
        while (it.hasNext()) {
            TtsWindow old = it.next().getValue();
            if (old.endMs < startMs - 5_000L) it.remove();
        }
        ttsWindows.put(index, new TtsWindow(startMs, endMs, startProgress));
        // Actual audio start is a stronger clock than any earlier display-only fallback.
        progressFloors.put(index, startProgress);
    }

    static void update(Activity a, long timeMs) {
        if (a == null || a.isFinishing() || a.isDestroyed()) return;
        ensureAttached(a);
        updateLayout(a);

        final boolean backwardSeek = SubtitleSyncPolicy.isBackwardSeek(lastUpdateTimeMs, timeMs);
        if (backwardSeek) {
            progressFloors.clear();
            resetPageTelemetry();
            SpanishStudyDiagnostics.record("SUBTITLE-SYNC",
                    "action=backward-seek-reset from=" + lastUpdateTimeMs + " to=" + timeMs);
        }
        lastUpdateTimeMs = timeMs;

        int sourceIndex = findSourceIndex(timeMs);
        int displayIndex = findTranslatedIndex(timeMs, sourceIndex);
        int pairSourceIndex = displayIndex >= 0 && displayIndex < sourceSegments.size()
                ? displayIndex : sourceIndex;

        TranscriptSegment source = pairSourceIndex >= 0 && pairSourceIndex < sourceSegments.size()
                ? sourceSegments.get(pairSourceIndex) : null;
        TranscriptSegment translated = matchingTranslated(displayIndex);
        boolean hasDubText = translated != null
                && translated.lang != null
                && translated.lang.toLowerCase().startsWith("es")
                && translated.text != null
                && !translated.text.isBlank();

        TtsWindow window = displayIndex >= 0 ? ttsWindows.get(displayIndex) : null;
        boolean audioStarted = window != null && timeMs >= window.startMs;
        double sourceProgress = source == null ? 0.0
                : SubtitlePagePolicy.progress(timeMs, source.startMs, source.endMs);
        double audioProgress = window == null ? 0.0 : window.progress(timeMs);
        double progress = SubtitleAudioSyncPolicy.pairedProgress(
                hasDubText, audioStarted, audioProgress, sourceProgress);

        if (displayIndex >= 0) {
            double previous = progressFloors.getOrDefault(displayIndex, 0.0);
            progress = SubtitleSyncPolicy.monotonicProgress(previous, progress, backwardSeek);
            progressFloors.put(displayIndex, progress);
        }

        ShownPage sourcePage = pageFor(sourcePages, pairSourceIndex,
                source == null ? "" : source.text, progress);
        ShownPage translatedPage = pageFor(translatedPages, displayIndex,
                translated == null ? "" : translated.text, progress);

        boolean showSpanish = SpanishStudyPrefs.showSubtitles(a)
                && hasDubText && !translatedPage.text.isBlank();
        boolean showEnglish = SpanishStudyPrefs.showEnglishSubtitles(a)
                && source != null
                && source.lang != null
                && source.lang.toLowerCase().startsWith("en")
                && !sourcePage.text.isBlank();

        String speaker = SpanishStudyPrefs.speakerLabelsEnabled(a)
                ? SpanishStudyController.speakerLabel(source) : "";
        boolean showBadge = speaker != null && !speaker.isBlank() && (showSpanish || showEnglish);
        if (showBadge) {
            if (!speaker.contentEquals(speakerBadgeView.getText())) speakerBadgeView.setText(speaker);
            speakerBadgeView.setVisibility(View.VISIBLE);
        } else {
            speakerBadgeView.setVisibility(View.GONE);
        }

        if (showSpanish) {
            if (!translatedPage.text.contentEquals(translatedView.getText())) {
                translatedView.setText(translatedPage.text);
            }
            translatedView.setVisibility(View.VISIBLE);
            spanishRow.setVisibility(View.VISIBLE);
            recordPageTransition(true, displayIndex, translatedPage);
        } else {
            translatedView.setVisibility(View.GONE);
            spanishRow.setVisibility(showBadge ? View.VISIBLE : View.GONE);
        }

        if (showEnglish) {
            if (!sourcePage.text.contentEquals(sourceView.getText())) sourceView.setText(sourcePage.text);
            sourceView.setVisibility(View.VISIBLE);
            recordPageTransition(false, pairSourceIndex, sourcePage);
        } else {
            sourceView.setVisibility(View.GONE);
        }

        pairView.setVisibility(spanishRow.getVisibility() == View.VISIBLE
                || sourceView.getVisibility() == View.VISIBLE ? View.VISIBLE : View.GONE);
    }

    static void clear() {
        translatedSegments = new ArrayList<>();
        sourceSegments = new ArrayList<>();
        ttsWindows.clear();
        translatedPages.clear();
        sourcePages.clear();
        progressFloors.clear();
        lastUpdateTimeMs = Long.MIN_VALUE;
        sourceCursor = 0;
        resetPageTelemetry();
        hidePair();
    }

    static void hide() {
        hidePair();
    }

    private static ShownPage pageFor(Map<Integer, List<SubtitlePagePolicy.Page>> cache,
                                     int index, String raw, double progress) {
        if (index < 0 || raw == null || raw.isBlank()) return new ShownPage("", -1, 0);
        List<SubtitlePagePolicy.Page> pages = cache.get(index);
        if (pages == null) {
            pages = SubtitlePagePolicy.paginate(raw);
            cache.put(index, pages);
        }
        int pageIndex = SubtitlePagePolicy.pageIndex(pages, progress);
        if (pageIndex < 0 || pageIndex >= pages.size()) return new ShownPage("", -1, pages.size());
        return new ShownPage(pages.get(pageIndex).text, pageIndex, pages.size());
    }

    private static void recordPageTransition(boolean spanish, int segment, ShownPage page) {
        if (segment < 0 || page.pageIndex < 0 || page.pageCount <= 1) return;
        if (spanish) {
            if (segment == lastSpanishSegment && page.pageIndex == lastSpanishPage) return;
            lastSpanishSegment = segment;
            lastSpanishPage = page.pageIndex;
        } else {
            if (segment == lastEnglishSegment && page.pageIndex == lastEnglishPage) return;
            lastEnglishSegment = segment;
            lastEnglishPage = page.pageIndex;
        }
        SpanishStudyDiagnostics.record("SUBTITLE-PAGE",
                "lang=" + (spanish ? "es" : "en") + " index=" + segment
                        + " page=" + (page.pageIndex + 1) + "/" + page.pageCount);
    }

    private static void resetPageTelemetry() {
        lastSpanishSegment = -1;
        lastSpanishPage = -1;
        lastEnglishSegment = -1;
        lastEnglishPage = -1;
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

    /** Prefer an actually-playing dub segment, otherwise pair against the source cue. */
    private static int findTranslatedIndex(long timeMs, int sourceIndex) {
        int active = -1;
        long latestStart = Long.MIN_VALUE;
        for (Map.Entry<Integer, TtsWindow> entry : ttsWindows.entrySet()) {
            TtsWindow window = entry.getValue();
            if (window.active(timeMs) && window.startMs >= latestStart) {
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
        if (pairView != null && spanishRow != null && speakerBadgeView != null
                && translatedView != null && sourceView != null
                && activity == a && pairView.getParent() != null) return;

        detach(pairView);
        activity = a;
        pairView = new LinearLayout(a);
        pairView.setOrientation(LinearLayout.VERTICAL);
        pairView.setGravity(Gravity.CENTER_HORIZONTAL);
        pairView.setVisibility(View.GONE);

        spanishRow = new LinearLayout(a);
        spanishRow.setOrientation(LinearLayout.HORIZONTAL);
        spanishRow.setGravity(Gravity.CENTER_VERTICAL | Gravity.CENTER_HORIZONTAL);
        spanishRow.setVisibility(View.GONE);

        speakerBadgeView = createSpeakerBadge(a);
        LinearLayout.LayoutParams badgeLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        badgeLp.rightMargin = dp(a, 5);
        spanishRow.addView(speakerBadgeView, badgeLp);

        translatedView = createTextView(a);
        spanishRow.addView(translatedView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        LinearLayout.LayoutParams top = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        top.gravity = Gravity.CENTER_HORIZONTAL;
        pairView.addView(spanishRow, top);

        sourceView = createTextView(a);
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

    private static TextView createSpeakerBadge(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT_BOLD);
        view.setTextSize(TypedValue.COMPLEX_UNIT_SP, 11);
        view.setGravity(Gravity.CENTER);
        view.setMinWidth(dp(a, 25));
        view.setPadding(dp(a, 6), dp(a, 3), dp(a, 6), dp(a, 3));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xE84A4A4A);
        bg.setStroke(dp(a, 1), 0xE6FFFFFF);
        bg.setCornerRadius(dp(a, 12));
        view.setBackground(bg);
        view.setVisibility(View.GONE);
        return view;
    }

    private static TextView createTextView(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setSingleLine(false);
        view.setMaxLines(3);
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
            int maxWidth = Math.max(dp(a, 120), content.getWidth() - dp(a, 92));
            translatedView.setMaxWidth(maxWidth);
            sourceView.setMaxWidth(Math.max(dp(a, 120), content.getWidth() - dp(a, 56)));
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
        if (speakerBadgeView != null) speakerBadgeView.setVisibility(View.GONE);
        if (translatedView != null) translatedView.setVisibility(View.GONE);
        if (sourceView != null) sourceView.setVisibility(View.GONE);
        if (spanishRow != null) spanishRow.setVisibility(View.GONE);
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
