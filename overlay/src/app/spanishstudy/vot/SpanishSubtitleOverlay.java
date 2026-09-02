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
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;

/**
 * Displays the translated Spanish dub and English source subtitles on one shared timeline.
 *
 * The English/source transcript is authoritative for timing. Spanish is selected by the exact
 * same segment index, and both boxes use the same chunk number and chunk transition instants.
 * This prevents either language from lagging a box behind the other after seeks or when Spanish
 * and English have different word counts/speech rhythms.
 */
final class SpanishSubtitleOverlay {
    private static final Pattern TOKEN = Pattern.compile("\\S+");
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
            spanishView.setVisibility(View.GONE);
            englishView.setVisibility(View.GONE);
            return;
        }

        TranscriptSegment english = englishSegments.get(index);
        TranscriptSegment spanish = matchingSpanish(index, english);
        updatePair(a, english, spanish, timeMs);
    }

    private static void updatePair(Activity a,
                                   TranscriptSegment english,
                                   TranscriptSegment spanish,
                                   long timeMs) {
        List<String> englishTokens = tokens(english == null ? null : english.text);
        List<String> spanishTokens = tokens(spanish == null ? null : spanish.text);

        final int preferredWords = SpanishStudyPrefs.subtitleWords(a);
        SynchronizedSubtitleChunks.Window window = SynchronizedSubtitleChunks.window(
                englishTokens.size(), spanishTokens.size(), preferredWords,
                english.startMs, english.endMs, timeMs);

        if (SpanishStudyPrefs.showEnglishSubtitles(a)
                && english != null
                && english.lang != null
                && english.lang.toLowerCase().startsWith("en")
                && !englishTokens.isEmpty()) {
            String chunk = join(englishTokens, window.englishStart, window.englishEnd);
            if (!chunk.contentEquals(englishView.getText())) englishView.setText(chunk);
            englishView.setVisibility(chunk.isBlank() ? View.GONE : View.VISIBLE);
        } else {
            englishView.setVisibility(View.GONE);
        }

        if (SpanishStudyPrefs.showSubtitles(a)
                && spanish != null
                && spanish.lang != null
                && spanish.lang.toLowerCase().startsWith("es")
                && !spanishTokens.isEmpty()) {
            String chunk = join(spanishTokens, window.spanishStart, window.spanishEnd);
            if (!chunk.contentEquals(spanishView.getText())) spanishView.setText(chunk);
            spanishView.setVisibility(chunk.isBlank() ? View.GONE : View.VISIBLE);
        } else {
            spanishView.setVisibility(View.GONE);
        }
    }

    /**
     * The source/English segment is the single clock for both languages. This is intentionally
     * one cursor rather than independent English/Spanish cursors.
     */
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
     * Gemini v2.2 preserves 1:1 segment ordering. The timestamp fallback keeps the overlay safe if
     * a non-Gemini provider ever returns a differently shaped snapshot.
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

    private static List<String> tokens(String text) {
        List<String> out = new ArrayList<>();
        if (text == null || text.isBlank()) return out;
        Matcher matcher = TOKEN.matcher(text);
        while (matcher.find()) out.add(matcher.group());
        return out;
    }

    private static String join(List<String> words, int start, int end) {
        if (words.isEmpty()) return "";
        int safeStart = Math.max(0, Math.min(words.size(), start));
        int safeEnd = Math.max(safeStart, Math.min(words.size(), end));
        StringBuilder out = new StringBuilder();
        for (int i = safeStart; i < safeEnd; i++) {
            if (out.length() > 0) out.append(' ');
            out.append(words.get(i));
        }
        return out.toString();
    }

    static void hide() {
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
        view.setMaxLines(2);
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
