package app.spanishstudy.vot;

import android.app.Activity;

import java.util.ArrayList;
import java.util.List;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;
import app.morphe.extension.youtube.settings.Settings;

/**
 * Thin bridge from Morphe's native VOT lifecycle into the optional bilingual subtitle UI.
 * It deliberately does not own translation, segmentation, batching, TTS, or playback scheduling.
 */
public final class SpanishStudyController {
    private SpanishStudyController() {}

    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setSourceSegments(snapshot));
        SpanishStudyDiagnostics.record("CAPTIONS", "source events=" + snapshot.size());
    }

    public static void onTranscriptUpdated(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTranslatedSegments(snapshot));
        SpanishStudyDiagnostics.record("TRANSCRIPT", "translated snapshot events=" + snapshot.size());
    }

    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        SpanishSubtitleOverlay.update(activity, timeMs);
    }

    public static void onVideoCleared() {
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
        report.append("Spanish Dub Study v2.16.0 diagnostics\n");
        report.append("coreArchitecture=morphe-v1.41.0-native\n");
        report.append("segmentation=morphe-native-unchanged\n");
        report.append("translationBatching=morphe-native-1500char+350char-first+single-stream\n");
        report.append("ttsArchitecture=morphe-native-edge-cache-prefetch-window-adjustment\n");
        report.append("translationOutputSanitizer=batch-enum+duration+timestamp-firewall\n");
        report.append("votRuntimeLifecycle=session-gated-provider-work\n");
        report.append("speakerBackend=not-installed\n");
        report.append("speakerVoiceRouting=disabled\n");
        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append('\n');
        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append('\n');
        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\n');
        report.append("translationActive=").append(VoiceOverTranslationPatch.isTranslationActive()).append('\n');
        report.append("translationProvider=").append(Settings.VOT_TRANSLATION_SERVICE.get()).append('\n');
        report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append('\n');
        report.append(OpenRouterTelemetry.diagnostics());
        report.append("--- events ---\n");
        report.append(SpanishStudyDiagnostics.dump());
        return report.toString();
    }
}
