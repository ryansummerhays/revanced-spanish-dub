package app.spanishstudy.vot;

import android.app.Activity;

import java.util.ArrayList;
import java.util.List;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;
import app.morphe.extension.youtube.settings.Settings;

/**
 * Passive bridge from stock Morphe VOT into the bilingual subtitle overlay.
 *
 * This class owns no translation, segmentation, TTS, playback rate, seek, cache, or prefetch
 * decisions. It only copies references to Morphe's published transcript snapshots for display.
 */
public final class SpanishStudyController {
    private static volatile int sourceCount;
    private static volatile int translatedCount;

    private SpanishStudyController() {}

    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        sourceCount = snapshot.size();
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setSourceSegments(snapshot));
        SpanishStudyDiagnostics.record("CAPTIONS", "stock source segments=" + snapshot.size());
    }

    public static void onTranscriptUpdated(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        translatedCount = snapshot.size();
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTranslatedSegments(snapshot));
        SpanishStudyDiagnostics.record("TRANSCRIPT", "stock translated snapshot segments=" + snapshot.size());
    }

    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        SpanishSubtitleOverlay.update(activity, timeMs);
    }

    public static void onVideoCleared() {
        sourceCount = 0;
        translatedCount = 0;
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);
        SpanishStudyDiagnostics.record("VIDEO", "cleared");
    }

    public static void onSessionDisabled() {
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);
        SpanishStudyDiagnostics.record("VOT", "session disabled");
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
        SpanishStudySheet.show(activity);
    }

    public static String buildDiagnostics() {
        StringBuilder report = new StringBuilder();
        report.append("Spanish Dub Study v2.27.0 diagnostics\n");
        report.append("coreArchitecture=morphe-v1.41.0-stock-vot\n");
        report.append("speechSegmentation=stock-morphe-mergeIntoSentences\n");
        report.append("translationPipeline=stock-morphe-unmodified\n");
        report.append("translationCustomRecovery=none\n");
        report.append("ttsArchitecture=stock-morphe-unmodified\n");
        report.append("subtitleLayer=passive-lossless-pagination-only\n");
        report.append("subtitleClock=stock-playback-window+active-spoken-index\n");
        report.append("subtitleBilingualCardSync=shared-count+shared-index\n");
        report.append("speakerBackend=disabled\n");
        report.append("speakerRequests=0\n");
        report.append("speakerVoiceRouting=disabled\n");
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
        report.append("--- events ---\n");
        report.append(SpanishStudyDiagnostics.dump());
        return report.toString();
    }
}
