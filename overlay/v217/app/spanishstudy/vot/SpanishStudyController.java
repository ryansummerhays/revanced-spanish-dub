package app.spanishstudy.vot;

import android.app.Activity;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;
import app.morphe.extension.youtube.settings.Settings;

/**
 * Thin bridge from Morphe's native VOT lifecycle into the optional bilingual subtitle UI.
 * Translation, segmentation, batching, TTS synthesis, cache/prefetch and playback scheduling
 * remain owned by Morphe.
 */
public final class SpanishStudyController {
    private static volatile List<TranscriptSegment> sourceSegments = new ArrayList<>();
    private static List<TranscriptSegment> lastAcceptedTranslated = new ArrayList<>();
    private static long lastTranslatedFingerprint = Long.MIN_VALUE;
    private static int translatedSnapshotVersion;
    private static boolean cleared = true;

    private SpanishStudyController() {}

    public static void onNewVideo(String videoId) {
        sourceSegments = new ArrayList<>();
        synchronized (SpanishStudyController.class) {
            lastAcceptedTranslated = new ArrayList<>();
            lastTranslatedFingerprint = Long.MIN_VALUE;
            translatedSnapshotVersion = 0;
            cleared = false;
        }
        long epoch = SpanishStudyRuntimeTelemetry.beginEpoch();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " new-video id=" + videoId);
    }

    public static void onSessionEnabled() {
        long epoch = SpanishStudyRuntimeTelemetry.bumpEpoch();
        synchronized (SpanishStudyController.class) {
            cleared = false;
            lastTranslatedFingerprint = Long.MIN_VALUE;
        }
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " enabled");
    }

    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        sourceSegments = snapshot;
        synchronized (SpanishStudyController.class) {
            cleared = false;
        }
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setSourceSegments(snapshot));
        SpanishStudyDiagnostics.record("CAPTIONS", "epoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                + " source events=" + snapshot.size());
    }

    public static void onTranscriptUpdated(List<TranscriptSegment> segments) {
        final List<TranscriptSegment> snapshot = segments == null
                ? new ArrayList<>() : new ArrayList<>(segments);
        final int changed;
        final int version;
        synchronized (SpanishStudyController.class) {
            long fingerprint = fingerprint(snapshot);
            if (fingerprint == lastTranslatedFingerprint) {
                SpanishStudyRuntimeTelemetry.recordSnapshotSuppressed();
                return;
            }
            changed = changedCount(lastAcceptedTranslated, snapshot);
            lastAcceptedTranslated = snapshot;
            lastTranslatedFingerprint = fingerprint;
            translatedSnapshotVersion++;
            version = translatedSnapshotVersion;
        }
        SpanishStudyRuntimeTelemetry.recordSnapshotAccepted();
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTranslatedSegments(snapshot));
        SpanishStudyDiagnostics.record("TRANSCRIPT", "epoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                + " version=" + version + " events=" + snapshot.size() + " changed=" + changed);
    }

    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        SpanishSubtitleOverlay.update(activity, timeMs);
    }

    public static void onTtsWindow(int index, String text, long showAtMs, long hideAtMs,
                                   long speechDurationMs, float rate) {
        if (index < 0 || hideAtMs <= showAtMs) return;
        Utils.runOnMainThreadNowOrLater(() -> SpanishSubtitleOverlay.setTtsWindow(index, showAtMs, hideAtMs));

        List<TranscriptSegment> sources = sourceSegments;
        if (index >= 0 && index < sources.size()) {
            TranscriptSegment source = sources.get(index);
            long overrunMs = Math.max(0L, hideAtMs - source.endMs);
            SpanishStudyRuntimeTelemetry.recordSubtitleOverrun(overrunMs);
            if (overrunMs >= 500L) {
                SpanishStudyDiagnostics.record("SUBTITLE-TIMING", "epoch="
                        + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index
                        + " sourceEnd=" + source.endMs + " ttsEnd=" + hideAtMs
                        + " overrunMs=" + overrunMs + " speechMs=" + speechDurationMs
                        + " rate=" + String.format(java.util.Locale.US, "%.2f", rate));
            }
        }
    }

    /** Last-resort guard immediately before TTS. OpenRouter is also guarded before publication. */
    public static boolean allowTts(int index, String translatedText, String targetLang) {
        List<TranscriptSegment> sources = sourceSegments;
        if (index < 0 || index >= sources.size()) return true;
        String sourceText = sources.get(index).text;
        String reason = DubLanguageGuard.reason(sourceText, translatedText, targetLang);
        if (reason == null) return true;
        SpanishStudyRuntimeTelemetry.recordTtsEnglishGuardTrigger();
        SpanishStudyDiagnostics.record("TTS-LANGUAGE-GUARD", "epoch="
                + SpanishStudyRuntimeTelemetry.currentEpoch() + " index=" + index + " reason=" + reason);
        return false;
    }

    public static void recordTranslationGuardReject(int slot, String reason) {
        SpanishStudyRuntimeTelemetry.recordTranslationEnglishGuardReject();
        SpanishStudyDiagnostics.record("OPENROUTER-LANGUAGE-GUARD", "epoch="
                + SpanishStudyRuntimeTelemetry.currentEpoch() + " slot=" + slot + " reason=" + reason);
    }

    public static void onVideoCleared() {
        synchronized (SpanishStudyController.class) {
            if (cleared) return;
            cleared = true;
        }
        sourceSegments = new ArrayList<>();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);
        SpanishStudyDiagnostics.record("VIDEO", "epoch=" + SpanishStudyRuntimeTelemetry.currentEpoch() + " cleared");
    }

    public static void onSessionDisabled() {
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + SpanishStudyRuntimeTelemetry.currentEpoch() + " disabled");
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
        report.append("Spanish Dub Study v2.17.0 diagnostics\n");
        report.append("coreArchitecture=morphe-v1.41.0-native\n");
        report.append("segmentation=morphe-native-unchanged\n");
        report.append("translationBatching=morphe-native-1500char+350char-first+single-stream\n");
        report.append("ttsArchitecture=morphe-native-edge-cache-prefetch-window-adjustment\n");
        report.append("subtitleTiming=morphe-tts-effective-end+source-fallback\n");
        report.append("subtitleLinePolicy=up-to-4-lines-autosize\n");
        report.append("snapshotPublication=content-fingerprint-deduplicated\n");
        report.append("englishLeakGuard=openrouter-post-parse+pre-tts-source-aware\n");
        report.append("cardinalityRecovery=aligned-prefix+native-tail-requeue+same-batch-retry\n");
        report.append("translationOutputSanitizer=batch-enum+duration+timestamp-firewall\n");
        report.append("votRuntimeLifecycle=session-gated-provider-work+session-epoch\n");
        report.append("speakerBackend=not-installed\n");
        report.append("speakerVoiceRouting=disabled\n");
        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append('\n');
        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append('\n');
        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\n');
        report.append("translationActive=").append(VoiceOverTranslationPatch.isTranslationActive()).append('\n');
        report.append("translationProvider=").append(Settings.VOT_TRANSLATION_SERVICE.get()).append('\n');
        report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append('\n');
        report.append(OpenRouterTelemetry.diagnostics());
        report.append(SpanishStudyRuntimeTelemetry.diagnostics());
        report.append("--- events ---\n");
        report.append(SpanishStudyDiagnostics.dump());
        return report.toString();
    }

    private static long fingerprint(List<TranscriptSegment> segments) {
        long h = 1469598103934665603L;
        for (TranscriptSegment seg : segments) {
            h ^= seg.startMs; h *= 1099511628211L;
            h ^= seg.endMs; h *= 1099511628211L;
            h ^= Objects.hashCode(seg.text); h *= 1099511628211L;
            h ^= Objects.hashCode(seg.lang); h *= 1099511628211L;
        }
        h ^= segments.size();
        return h;
    }

    private static int changedCount(List<TranscriptSegment> before, List<TranscriptSegment> after) {
        int changed = Math.abs(before.size() - after.size());
        int limit = Math.min(before.size(), after.size());
        for (int i = 0; i < limit; i++) {
            TranscriptSegment a = before.get(i);
            TranscriptSegment b = after.get(i);
            if (a.startMs != b.startMs || a.endMs != b.endMs
                    || !Objects.equals(a.text, b.text) || !Objects.equals(a.lang, b.lang)) changed++;
        }
        return changed;
    }
}