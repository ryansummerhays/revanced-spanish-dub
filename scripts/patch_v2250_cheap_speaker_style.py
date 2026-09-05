#!/usr/bin/env python3
from pathlib import Path
import shutil, sys


def rep(path, old, new, label, count=1):
    text = path.read_text(encoding='utf-8')
    found = text.count(old)
    if found != count:
        raise RuntimeError(f'{label}: expected {count}, found {found} in {path}')
    path.write_text(text.replace(old, new, count), encoding='utf-8')
    print('patched:', label)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: patch_v2250_cheap_speaker_style.py <morphe-root> <repo-root>')
    root = Path(sys.argv[1]).resolve(); repo = Path(sys.argv[2]).resolve()
    study = root/'extensions/youtube/src/main/java/app/spanishstudy/vot'
    controller = study/'SpanishStudyController.java'
    sheet = study/'SpanishStudySheet.java'
    overlay = study/'SpanishSubtitleOverlay.java'

    for p in (controller, sheet, overlay):
        if not p.is_file(): raise RuntimeError(f'missing generated source: {p}')

    v225 = repo/'overlay/v225/app/spanishstudy/vot'
    for name in ('SubtitleLinePolicy.java', 'SpeakerNamePolicy.java',
                 'SpeakerAssignmentStore.java', 'GeminiSpeakerDiarizationSidecar.java'):
        shutil.copy2(v225/name, study/name)
        print('copied:', name)

    # Display a transcript-verified name when available, while speakerIndex() continues to use A-H.
    rep(controller,
'''    public static String speakerLabel(TranscriptSegment segment) {
        return SpeakerAssignmentStore.speakerLabel(segment);
    }''',
'''    public static String speakerLabel(TranscriptSegment segment) {
        return SpeakerAssignmentStore.displayLabel(segment);
    }''', 'use display name only in subtitle/UI label')

    # Diagnostics must describe the real OpenRouter backend rather than the old direct Gemini key.
    rep(controller,
        'report.append("Spanish Dub Study v2.24.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.25.0 diagnostics\\n");', 'bump diagnostics')
    rep(controller,
        'report.append("subtitleLinePolicy=lossless-bilingual-pagination-13words-88chars+3-line-safety\\n");',
        'report.append("subtitleLinePolicy=lossless-bilingual-pagination-13words-88chars+42char-target+2-lines-per-language\\n");\n        report.append("subtitleVisualStyle=single-dark-card+primary-spanish+secondary-english+bracket-speaker-id\\n");',
        'publish subtitle layout policy')
    rep(controller,
        'report.append("speakerBackend=gemini-3.7-flash-youtube-audio-sidecar\\n");',
        'report.append("speakerBackend=openrouter-google-ai-studio-agentic-cheap-first\\n");',
        'publish OpenRouter speaker backend')
    rep(controller,
'''        report.append("speakerKeyConfigured=").append(activity != null
                && !SpanishStudyPrefs.speakerApiKey(activity).isEmpty()).append('\\n');''',
'''        report.append("speakerOpenRouterKeyConfigured=").append(
                !Settings.VOT_OPENROUTER_API_KEY.get().trim().isEmpty()).append('\\n');''',
        'publish shared OpenRouter key state')
    rep(controller,
        'report.append("speakerCostTelemetry=interactions-usage+hypothetical-paid-estimate\\n");',
        'report.append("speakerCostTelemetry=openrouter-response-usage-actual-cost\\n");\n        report.append("speakerNamePolicy=transcript-evidence-only+no-voice-face-identity\\n");',
        'publish actual speaker cost and name policy')

    # The separate Gemini key is obsolete. Keep the legacy preference methods for compatibility but
    # remove the active row and explain that speaker analysis reuses Morphe's OpenRouter key.
    rep(sheet,
'''        content.addView(switchRow(activity, fg, "Recognize different speakers",
                "Anonymous A/B/C acoustic profiles from the public YouTube audio; never uses the phone microphone",
                SpanishStudyPrefs.speakerRecognitionEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerRecognitionEnabled(activity, value)));''',
'''        content.addView(switchRow(activity, fg, "Recognize different speakers",
                "Cheap whole-video analysis uses your existing OpenRouter key; the stronger model runs only if the cheap map fails",
                SpanishStudyPrefs.speakerRecognitionEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerRecognitionEnabled(activity, value)));''',
        'describe cheap shared-key speaker analysis')
    rep(sheet,
'''        content.addView(switchRow(activity, fg, "Show speaker labels",
                "Show A, B, C… beside bilingual subtitles when the acoustic profile is confident",
                SpanishStudyPrefs.speakerLabelsEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerLabelsEnabled(activity, value)));''',
'''        content.addView(switchRow(activity, fg, "Show speaker labels",
                "Shows [A]/[B], or a name only when the transcript itself clearly establishes it",
                SpanishStudyPrefs.speakerLabelsEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerLabelsEnabled(activity, value)));''',
        'describe transcript-verified speaker names')
    rep(sheet,
'''        LinearLayout speakerKey = valueRow(activity, fg, "Speaker analysis API key",
                SpanishStudyPrefs.speakerApiKey(activity).isEmpty() ? "Not set" : "Configured");
        speakerKey.setOnClickListener(v -> showSpeakerKeyDialog(activity));
        content.addView(speakerKey);
''', '', 'remove obsolete separate Gemini speaker key row')

    # Format each language card into conventional two-line subtitle shapes without deleting text.
    rep(overlay,
'''            if (!translatedPage.text.contentEquals(translatedView.getText())) {
                translatedView.setText(translatedPage.text);
            }''',
'''            String formattedSpanish = SubtitleLinePolicy.format(translatedPage.text);
            if (!formattedSpanish.contentEquals(translatedView.getText())) {
                translatedView.setText(formattedSpanish);
            }''', 'format Spanish as two-line timed text')
    rep(overlay,
'''            if (!sourcePage.text.contentEquals(sourceView.getText())) sourceView.setText(sourcePage.text);''',
'''            String formattedEnglish = SubtitleLinePolicy.format(sourcePage.text);
            if (!formattedEnglish.contentEquals(sourceView.getText())) sourceView.setText(formattedEnglish);''',
        'format English as two-line timed text')

    # Bracketed speaker IDs/names are the conventional speaker identifier form.
    rep(overlay,
'''            if (!speaker.contentEquals(speakerBadgeView.getText())) speakerBadgeView.setText(speaker);''',
'''            String shownSpeaker = "[" + speaker + "]";
            if (!shownSpeaker.contentEquals(speakerBadgeView.getText())) speakerBadgeView.setText(shownSpeaker);''',
        'render bracketed speaker identifier')

    # One coherent card instead of separate black capsules behind every line.
    rep(overlay,
'''        pairView.setGravity(Gravity.CENTER_HORIZONTAL);
        pairView.setVisibility(View.GONE);''',
'''        pairView.setGravity(Gravity.CENTER_HORIZONTAL);
        pairView.setPadding(dp(a, 10), dp(a, 7), dp(a, 10), dp(a, 7));
        GradientDrawable cardBackground = new GradientDrawable();
        cardBackground.setColor(0xD6000000);
        cardBackground.setCornerRadius(dp(a, 8));
        pairView.setBackground(cardBackground);
        pairView.setElevation(dp(a, 6));
        pairView.setVisibility(View.GONE);''', 'add one coherent dark subtitle card')

    rep(overlay,
'''        sourceView = createTextView(a);
        LinearLayout.LayoutParams bottom = new LinearLayout.LayoutParams(''',
'''        sourceView = createTextView(a);
        sourceView.setTextColor(0xD9FFFFFF);
        LinearLayout.LayoutParams bottom = new LinearLayout.LayoutParams(''',
        'make English visually secondary')

    rep(overlay,
'''        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);''',
'''        FrameLayout.LayoutParams lp = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.WRAP_CONTENT, ViewGroup.LayoutParams.WRAP_CONTENT,
                Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);''',
        'make subtitle card hug its content')

    old_text_view = '''    private static TextView createTextView(Activity a) {
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
    }'''
    new_text_view = '''    private static TextView createTextView(Activity a) {
        TextView view = new TextView(a);
        view.setTextColor(Color.WHITE);
        view.setTypeface(Typeface.DEFAULT, Typeface.NORMAL);
        view.setGravity(Gravity.CENTER);
        view.setIncludeFontPadding(false);
        view.setSingleLine(false);
        view.setMaxLines(2);
        view.setHorizontallyScrolling(false);
        view.setEllipsize(null);
        view.setPadding(dp(a, 4), dp(a, 2), dp(a, 4), dp(a, 2));
        view.setBackground(null);
        view.setVisibility(View.GONE);
        return view;
    }'''
    rep(overlay, old_text_view, new_text_view, 'use clean two-line text inside shared card')

    rep(overlay,
'''        bg.setColor(0xE84A4A4A);
        bg.setStroke(dp(a, 1), 0xE6FFFFFF);
        bg.setCornerRadius(dp(a, 12));''',
'''        bg.setColor(0xB84A4A4A);
        bg.setCornerRadius(dp(a, 5));''',
        'simplify speaker identifier badge')

    rep(overlay,
'''            int maxWidth = Math.max(dp(a, 120), content.getWidth() - dp(a, 92));
            translatedView.setMaxWidth(maxWidth);
            sourceView.setMaxWidth(Math.max(dp(a, 120), content.getWidth() - dp(a, 56)));''',
'''            int maxWidth = Math.max(dp(a, 160), content.getWidth() - dp(a, 72));
            translatedView.setMaxWidth(maxWidth);
            sourceView.setMaxWidth(maxWidth);''',
        'use one shared subtitle width')

    print('v2.25 cheap speaker names + standards-oriented subtitle style complete')


if __name__ == '__main__':
    main()
