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
import java.util.List;
import java.util.Map;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;

/** Display-only bilingual subtitles over stock Morphe VOT, with optional local speaker labels. */
final class SpanishSubtitleOverlay {
    private static final class SinglePages {
        final List<SubtitlePagePolicy.Page> pages;
        SinglePages(String raw) { pages = SubtitlePagePolicy.paginate(raw); }
        String at(double progress) {
            int i = SubtitlePagePolicy.pageIndex(pages, progress);
            return i >= 0 && i < pages.size() ? pages.get(i).text : "";
        }
        int index(double progress) { return SubtitlePagePolicy.pageIndex(pages, progress); }
        int size() { return pages.size(); }
    }

    private static Activity activity;
    private static LinearLayout outerView;
    private static TextView speakerView;
    private static LinearLayout cardView;
    private static TextView translatedView;
    private static TextView sourceView;

    private static List<TranscriptSegment> translatedSegments = new ArrayList<>();
    private static List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static final Map<Integer, BilingualCardPolicy.PairPages> pairCache = new HashMap<>();
    private static final Map<Integer, SinglePages> spanishCache = new HashMap<>();
    private static final Map<Integer, SinglePages> englishCache = new HashMap<>();

    private static int sourceCursor;
    private static int lastSegment = -1;
    private static int lastPage = -1;
    private static int lastPageCount;
    private static String lastSpeaker = "";

    private SpanishSubtitleOverlay() {}

    static void setTranslatedSegments(List<TranscriptSegment> snapshot) {
        translatedSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        pairCache.clear();
        spanishCache.clear();
    }

    static void setSourceSegments(List<TranscriptSegment> snapshot) {
        sourceSegments = snapshot == null ? new ArrayList<>() : new ArrayList<>(snapshot);
        sourceCursor = 0;
        pairCache.clear();
        spanishCache.clear();
        englishCache.clear();
        resetPageTelemetry();
    }

    static void update(Activity a, long timeMs) {
        if (a == null || a.isFinishing() || a.isDestroyed()) return;
        ensureAttached(a);
        updateLayout(a);

        int sourceIndex = findSourceIndex(timeMs);
        int activeSpoken = VoiceOverTranslationPatch.getActiveSpokenIndexForStudy();
        int index = validPairIndex(activeSpoken) ? activeSpoken : sourceIndex;
        if (index < 0 || index >= sourceSegments.size()) {
            hidePair();
            return;
        }

        TranscriptSegment source = sourceSegments.get(index);
        TranscriptSegment translated = matchingTranslated(index, source);
        String en = source.text == null ? "" : SubtitlePagePolicy.cleanDisplayText(source.text);
        String es = translated == null || translated.text == null
                ? "" : SubtitlePagePolicy.cleanDisplayText(translated.text);

        boolean hasSpanish = translated != null && translated.lang != null
                && translated.lang.toLowerCase().startsWith("es") && !es.isBlank();
        boolean hasEnglish = source.lang != null && source.lang.toLowerCase().startsWith("en") && !en.isBlank();
        boolean showSpanish = SpanishStudyPrefs.showSubtitles(a) && hasSpanish;
        boolean showEnglish = SpanishStudyPrefs.showEnglishSubtitles(a) && hasEnglish;
        if (!showSpanish && !showEnglish) {
            hidePair();
            return;
        }

        long windowStart = source.startMs;
        long windowEnd = source.endMs;
        if (activeSpoken == index && translated != null) {
            windowStart = translated.playbackStartMs;
            windowEnd = Math.max(translated.playbackEndMs,
                    VoiceOverTranslationPatch.getTtsEndVideoTimeMsForStudy());
            if (windowEnd <= windowStart) {
                windowStart = source.startMs;
                windowEnd = source.endMs;
            }
        }

        double progress = SubtitlePagePolicy.progress(timeMs, windowStart, windowEnd);
        String shownEs = "";
        String shownEn = "";
        int pageIndex = -1;
        int pageCount = 0;

        if (hasSpanish && hasEnglish) {
            BilingualCardPolicy.PairPages pair = pairCache.get(index);
            if (pair == null) {
                pair = BilingualCardPolicy.build(es, en);
                pairCache.put(index, pair);
            }
            pageCount = pair.size();
            pageIndex = BilingualCardPolicy.pairIndex(pageCount, progress);
            if (pageIndex >= 0 && pageIndex < pageCount) {
                shownEs = pair.spanish.get(pageIndex);
                shownEn = pair.english.get(pageIndex);
            }
        } else {
            if (hasSpanish) {
                SinglePages pages = spanishCache.computeIfAbsent(index, k -> new SinglePages(es));
                pageIndex = pages.index(progress);
                pageCount = pages.size();
                shownEs = pages.at(progress);
            }
            if (hasEnglish) {
                SinglePages pages = englishCache.computeIfAbsent(index, k -> new SinglePages(en));
                int enIndex = pages.index(progress);
                if (pageIndex < 0) {
                    pageIndex = enIndex;
                    pageCount = pages.size();
                }
                shownEn = pages.at(progress);
            }
        }

        if (showSpanish && !shownEs.isBlank()) {
            String formatted = SubtitleLinePolicy.format(shownEs);
            if (!formatted.contentEquals(translatedView.getText())) translatedView.setText(formatted);
            translatedView.setVisibility(View.VISIBLE);
        } else translatedView.setVisibility(View.GONE);

        if (showEnglish && !shownEn.isBlank()) {
            String formatted = SubtitleLinePolicy.format(shownEn);
            if (!formatted.contentEquals(sourceView.getText())) sourceView.setText(formatted);
            sourceView.setVisibility(View.VISIBLE);
        } else sourceView.setVisibility(View.GONE);

        String speaker = SpanishStudyPrefs.speakerExperiment(a)
                ? LocalSpeakerDiarizer.labelForSegment(index) : "";
        if (!speaker.isBlank()) {
            String label = "[" + speaker + "]";
            if (!label.contentEquals(speakerView.getText())) speakerView.setText(label);
            speakerView.setVisibility(View.VISIBLE);
        } else {
            speakerView.setVisibility(View.GONE);
        }

        outerView.setVisibility(translatedView.getVisibility() == View.VISIBLE
                || sourceView.getVisibility() == View.VISIBLE ? View.VISIBLE : View.GONE);

        boolean pageChanged = pageIndex >= 0 && (index != lastSegment || pageIndex != lastPage
                || pageCount != lastPageCount);
        if (pageChanged) {
            lastSegment = index;
            lastPage = pageIndex;
            lastPageCount = pageCount;
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,
                    "segment=" + index + " page=" + (pageIndex + 1) + "/" + pageCount
                            + " progress=" + String.format(java.util.Locale.US, "%.3f", progress)
                            + " activeSpeech=" + (activeSpoken == index)
                            + " sourceWindow=" + source.startMs + "-" + source.endMs
                            + " displayWindow=" + windowStart + "-" + windowEnd
                            + " speaker=" + (speaker.isBlank() ? "?" : speaker));
        }
        if (!speaker.equals(lastSpeaker)) {
            lastSpeaker = speaker;
            if (!speaker.isBlank()) {
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,
                        "speaker badge segment=" + index + " label=" + speaker
                                + " detail=" + LocalSpeakerDiarizer.assignmentDetails(index));
            }
        }
    }

    static void clear() {
        translatedSegments = new ArrayList<>();
        sourceSegments = new ArrayList<>();
        sourceCursor = 0;
        pairCache.clear();
        spanishCache.clear();
        englishCache.clear();
        resetPageTelemetry();
        hidePair();
    }

    static void hide() { hidePair(); }

    private static boolean validPairIndex(int index) {
        return index >= 0 && index < sourceSegments.size() && index < translatedSegments.size();
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

    private static TranscriptSegment matchingTranslated(int index, TranscriptSegment source) {
        if (index < 0 || index >= translatedSegments.size()) return null;
        TranscriptSegment candidate = translatedSegments.get(index);
        return candidate.startMs == source.startMs && candidate.endMs == source.endMs ? candidate : null;
    }

    private static void ensureAttached(Activity a) {
        if (outerView != null && cardView != null && translatedView != null && sourceView != null
                && activity == a && outerView.getParent() != null) return;

        detach(outerView);
        activity = a;
        outerView = new LinearLayout(a);
        outerView.setOrientation(LinearLayout.VERTICAL);
        outerView.setGravity(Gravity.CENTER_HORIZONTAL);
        outerView.setVisibility(View.GONE);

        speakerView = new TextView(a);
        speakerView.setTextColor(0xEFFFFFFF);
        speakerView.setTextSize(TypedValue.COMPLEX_UNIT_SP, 10);
        speakerView.setTypeface(Typeface.DEFAULT_BOLD);
        speakerView.setGravity(Gravity.CENTER);
        speakerView.setIncludeFontPadding(false);
        speakerView.setPadding(dp(a, 7), dp(a, 2), dp(a, 7), dp(a, 2));
        GradientDrawable speakerBg = new GradientDrawable();
        speakerBg.setColor(0xD9000000);
        speakerBg.setCornerRadius(dp(a, 12));
        speakerView.setBackground(speakerBg);
        speakerView.setVisibility(View.GONE);
        LinearLayout.LayoutParams speakerLp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        speakerLp.gravity = Gravity.CENTER_HORIZONTAL;
        speakerLp.bottomMargin = dp(a, 3);
        outerView.addView(speakerView, speakerLp);

        cardView = new LinearLayout(a);
        cardView.setOrientation(LinearLayout.VERTICAL);
        cardView.setGravity(Gravity.CENTER_HORIZONTAL);
        cardView.setPadding(dp(a, 10), dp(a, 7), dp(a, 10), dp(a, 7));
        GradientDrawable cardBg = new GradientDrawable();
        cardBg.setColor(0xD6000000);
        cardBg.setCornerRadius(dp(a, 8));
        cardView.setBackground(cardBg);
        cardView.setElevation(dp(a, 5));
        outerView.addView(cardView, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        translatedView = createTextView(a, Color.WHITE);
        sourceView = createTextView(a, 0xD9FFFFFF);
        LinearLayout.LayoutParams top = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        top.gravity = Gravity.CENTER_HORIZONTAL;
        cardView.addView(translatedView, top);
        LinearLayout.LayoutParams bottom = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        bottom.gravity = Gravity.CENTER_HORIZONTAL;
        bottom.topMargin = dp(a, 2);
        cardView.addView(sourceView, bottom);

        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        lp.leftMargin = dp(a, 28);
        lp.rightMargin = dp(a, 28);
        lp.bottomMargin = resolvedBottomMarginPx(a, SpanishStudyPrefs.subtitlePairBottom(a));
        a.addContentView(outerView, lp);
    }

    private static TextView createTextView(Activity a, int color) {
        TextView view = new TextView(a);
        view.setTextColor(color);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setIncludeFontPadding(false);
        view.setSingleLine(false);
        view.setMaxLines(SubtitleLinePolicy.MAX_LINES);
        view.setHorizontallyScrolling(false);
        view.setEllipsize(null);
        view.setVisibility(View.GONE);
        return view;
    }

    private static void updateLayout(Activity a) {
        updateTextSize(translatedView, SpanishStudyPrefs.subtitleTextSize(a));
        updateTextSize(sourceView, SpanishStudyPrefs.englishSubtitleTextSize(a));
        View content = a.findViewById(android.R.id.content);
        if (content != null && content.getWidth() > 0) {
            int maxWidth = Math.max(dp(a, 120), content.getWidth() - dp(a, 72));
            translatedView.setMaxWidth(maxWidth);
            sourceView.setMaxWidth(maxWidth);
        }
        ViewGroup.LayoutParams raw = outerView.getLayoutParams();
        if (raw instanceof FrameLayout.LayoutParams) {
            FrameLayout.LayoutParams lp = (FrameLayout.LayoutParams) raw;
            int wanted = resolvedBottomMarginPx(a, SpanishStudyPrefs.subtitlePairBottom(a));
            if (lp.bottomMargin != wanted) {
                lp.bottomMargin = wanted;
                outerView.setLayoutParams(lp);
            }
        }
    }

    private static void updateTextSize(TextView view, int preferredSp) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            int minSp = Math.max(8, preferredSp - 2);
            view.setAutoSizeTextTypeUniformWithConfiguration(
                    minSp, Math.max(minSp, preferredSp), 1, TypedValue.COMPLEX_UNIT_SP);
        } else view.setTextSize(TypedValue.COMPLEX_UNIT_SP, preferredSp);
    }

    private static int resolvedBottomMarginPx(Activity a, int configuredBottomDp) {
        int basePx = dp(a, configuredBottomDp);
        if (a.getResources().getConfiguration().orientation != Configuration.ORIENTATION_PORTRAIT) return basePx;
        View content = a.findViewById(android.R.id.content);
        if (content == null || content.getWidth() <= 0 || content.getHeight() <= content.getWidth()) return basePx;
        int playerHeight = Math.min(content.getHeight(), Math.round(content.getWidth() * 9f / 16f));
        float scale = playerHeight / (float) Math.max(1, content.getWidth());
        return Math.max(0, content.getHeight() - playerHeight + Math.round(basePx * scale));
    }

    private static void resetPageTelemetry() {
        lastSegment = -1;
        lastPage = -1;
        lastPageCount = 0;
        lastSpeaker = "";
    }

    private static void hidePair() {
        if (speakerView != null) speakerView.setVisibility(View.GONE);
        if (translatedView != null) translatedView.setVisibility(View.GONE);
        if (sourceView != null) sourceView.setVisibility(View.GONE);
        if (outerView != null) outerView.setVisibility(View.GONE);
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
