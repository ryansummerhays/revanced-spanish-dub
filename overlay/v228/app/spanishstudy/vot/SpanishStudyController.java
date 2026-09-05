package app.spanishstudy.vot;

import android.app.Activity;

import java.util.ArrayList;
import java.util.List;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;
import app.morphe.extension.youtube.settings.Settings;

/** Passive bridge from stock Morphe VOT into subtitles, diagnostics, and local speaker probing. */
public final class SpanishStudyController {
    private static volatile int sourceCount;
    private static volatile int translatedCount;
    private static volatile boolean prefsApplied;
    private static List<TranscriptSegment> lastTranslated = new ArrayList<>();

    private SpanishStudyController() {}

    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        sourceCount = snapshot.size();
        LocalSpeakerDiarizer.setSourceSegments(snapshot);
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setSourceSegments(snapshot));
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                "published source segments=" + snapshot.size());
        if (SpanishStudyDiagnostics.includeText()) {
            for (int i = 0; i < snapshot.size(); i++) {
                TranscriptSegment s = snapshot.get(i);
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                        "source[" + i + "] " + s.startMs + "-" + s.endMs
                                + " chars=" + (s.text == null ? 0 : s.text.length())
                                + " text=" + SpanishStudyDiagnostics.text(s.text));
            }
        }
    }

    public static void onTranscriptUpdated(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        translatedCount = snapshot.size();
        int changed = 0;
        int translated = 0;
        synchronized (SpanishStudyController.class) {
            int n = Math.min(snapshot.size(), lastTranslated.size());
            for (int i = 0; i < snapshot.size(); i++) {
                TranscriptSegment now = snapshot.get(i);
                if (now.lang != null && now.lang.toLowerCase().startsWith("es")) translated++;
                if (i >= n || !sameText(now, lastTranslated.get(i))) {
                    changed++;
                    if (SpanishStudyDiagnostics.includeText()) {
                        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                                "snapshot changed index=" + i + " lang=" + now.lang
                                        + " text=" + SpanishStudyDiagnostics.text(now.text));
                    }
                }
            }
            lastTranslated = snapshot;
        }
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTranslatedSegments(snapshot));
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "published snapshot segments=" + snapshot.size() + " translatedLangSegments="
                        + translated + " changed=" + changed);
    }

    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        LocalSpeakerDiarizer.updatePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        if (activity != null && !prefsApplied) {
            prefsApplied = true;
            SpanishStudyPrefs.applyDiagnosticConfig(activity);
            LocalSpeakerDiarizer.setEnabled(activity, SpanishStudyPrefs.speakerExperiment(activity));
        }
        SpanishSubtitleOverlay.update(activity, timeMs);
    }

    public static void onVideoCleared() {
        sourceCount = 0;
        translatedCount = 0;
        synchronized (SpanishStudyController.class) { lastTranslated = new ArrayList<>(); }
        LocalSpeakerDiarizer.resetForVideo();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE, "video state cleared");
    }

    public static void onSessionDisabled() {
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE, "VOT session disabled");
    }

    public static boolean suppressNativeCaptions() {
        Activity activity = Utils.getActivity();
        return activity != null
                && VoiceOverTranslationPatch.isSessionEnabled()
                && (SpanishStudyPrefs.showSubtitles(activity)
                    || SpanishStudyPrefs.showEnglishSubtitles(activity));
    }

    public static void showTools(Activity activity) {
        if (activity == null || activity.isFinishing()) return;
        SpanishStudyPrefs.applyDiagnosticConfig(activity);
        LocalSpeakerDiarizer.setEnabled(activity, SpanishStudyPrefs.speakerExperiment(activity));
        SpanishStudySheet.show(activity);
    }

    public static String buildDiagnostics() {
        Activity activity = Utils.getActivity();
        if (activity != null) SpanishStudyPrefs.applyDiagnosticConfig(activity);

        StringBuilder report = new StringBuilder();
        report.append("Spanish Dub Study v2.28.0 diagnostics\n");
        report.append("coreArchitecture=morphe-v1.41.0-stock-vot+read-only-diagnostic-hooks\n");
        report.append("speechSegmentation=stock-morphe-mergeIntoSentences\n");
        report.append("translationPipeline=stock-morphe-openrouter-mistral\n");
        report.append("translationCustomRecovery=none\n");
        report.append("ttsArchitecture=stock-morphe+diagnostic-hooks-only\n");
        report.append("subtitleLayer=passive-lossless-pagination\n");
        report.append("subtitleClock=stock-playback-window+active-spoken-index\n");
        report.append("subtitleBilingualCardSync=shared-count+shared-index\n");
        report.append("diagnosticArchitecture=component-selectable-3000-line-ring\n");
        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append('\n');
        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append('\n');
        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoadingForStudy()).append('\n');
        report.append("translationActive=").append(VoiceOverTranslationPatch.isTranslationActive()).append('\n');
        report.append("translationProvider=").append(Settings.VOT_TRANSLATION_SERVICE.get()).append('\n');
        report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append('\n');
        report.append("sourceSegments=").append(sourceCount).append('\n');
        report.append("translatedSegments=").append(translatedCount).append('\n');
        report.append("activeSpokenIndex=").append(VoiceOverTranslationPatch.getActiveSpokenIndexForStudy()).append('\n');
        report.append("activeTtsEndVideoMs=").append(VoiceOverTranslationPatch.getTtsEndVideoTimeMsForStudy()).append('\n');
        report.append(LocalSpeakerDiarizer.diagnostics());
        report.append("--- events ---\n");
        report.append(SpanishStudyDiagnostics.dump());
        return report.toString();
    }

    private static boolean sameText(TranscriptSegment a, TranscriptSegment b) {
        if (a == null || b == null) return a == b;
        String at = a.text == null ? "" : a.text;
        String bt = b.text == null ? "" : b.text;
        String al = a.lang == null ? "" : a.lang;
        String bl = b.lang == null ? "" : b.lang;
        return at.equals(bt) && al.equals(bl);
    }
}
