#!/usr/bin/env python3
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def section(path: Path, start_marker: str, end_marker: str):
    text = path.read_text(encoding="utf-8")
    start_at = text.index(start_marker)
    start = text.rfind("\n", 0, start_at) + 1
    end = text.index(end_marker, start_at)
    return text, start, end, text[start:end]


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2190_speaker.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    prefs = study / "SpanishStudyPrefs.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    subtitles = study / "SpanishSubtitleOverlay.java"
    vot = pkg / "VoiceOverTranslationPatch.java"

    for path in (prefs, controller, sheet, subtitles, vot):
        if not path.is_file():
            raise RuntimeError(f"missing v2.19 lifecycle source: {path}")

    legacy = repo / "overlay/src/app/spanishstudy/vot"
    for name in ("SpeakerAssignmentStore.java", "GeminiSpeakerDiarizationSidecar.java"):
        shutil.copy2(legacy / name, study / name)
        print("copied:", name)
    speaker_store = study / "SpeakerAssignmentStore.java"
    sidecar = study / "GeminiSpeakerDiarizationSidecar.java"

    rep(prefs,
        '''    private static final String SUBTITLE_PAIR_BOTTOM = "bilingual_subtitle_bottom_dp";''',
        '''    private static final String SUBTITLE_PAIR_BOTTOM = "bilingual_subtitle_bottom_dp";
    private static final String SPEAKER_RECOGNITION = "speaker_recognition_enabled";
    private static final String SPEAKER_VOICES = "speaker_voices_enabled";
    private static final String SPEAKER_LABELS = "speaker_labels_enabled";
    private static final String SPEAKER_API_KEY = "gemini_api_key";''',
        "add speaker-only preferences")

    rep(prefs,
        '''    private static void putInt(Context context, String key, int value) {
        prefs(context).edit().putInt(key, value).apply();
    }
''',
        '''    private static void putInt(Context context, String key, int value) {
        prefs(context).edit().putInt(key, value).apply();
    }

    private static void putString(Context context, String key, String value) {
        prefs(context).edit().putString(key, value == null ? "" : value.trim()).apply();
    }
''',
        "add speaker key writer")

    rep(prefs,
        '''    static void setSubtitlePairBottom(Context context, int value) {
        putInt(context, SUBTITLE_PAIR_BOTTOM, Math.max(24, Math.min(240, value)));
    }
}''',
        '''    static void setSubtitlePairBottom(Context context, int value) {
        putInt(context, SUBTITLE_PAIR_BOTTOM, Math.max(24, Math.min(240, value)));
    }

    static boolean speakerRecognitionEnabled(Context context) {
        return prefs(context).getBoolean(SPEAKER_RECOGNITION, true);
    }

    static void setSpeakerRecognitionEnabled(Context context, boolean value) {
        putBoolean(context, SPEAKER_RECOGNITION, value);
    }

    static boolean speakerVoicesEnabled(Context context) {
        return prefs(context).getBoolean(SPEAKER_VOICES, true);
    }

    static void setSpeakerVoicesEnabled(Context context, boolean value) {
        putBoolean(context, SPEAKER_VOICES, value);
    }

    static boolean speakerLabelsEnabled(Context context) {
        return prefs(context).getBoolean(SPEAKER_LABELS, true);
    }

    static void setSpeakerLabelsEnabled(Context context, boolean value) {
        putBoolean(context, SPEAKER_LABELS, value);
    }

    static String speakerApiKey(Context context) {
        String value = prefs(context).getString(SPEAKER_API_KEY, "");
        return value == null ? "" : value.trim();
    }

    static void setSpeakerApiKey(Context context, String value) {
        putString(context, SPEAKER_API_KEY, value);
    }
}''',
        "add speaker preference APIs")

    rep(controller,
        '''        long epoch = SpanishStudyRuntimeTelemetry.beginEpoch();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);''',
        '''        long epoch = SpanishStudyRuntimeTelemetry.beginEpoch();
        SpeakerAssignmentStore.clear();
        GeminiSpeakerDiarizationSidecar.clear();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::clear);''',
        "reset speaker state on new video")

    rep(controller,
        '''        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " enabled");''',
        '''        GeminiSpeakerDiarizationSidecar.onSessionBoundary();
        SpanishStudyDiagnostics.record("SESSION", "epoch=" + epoch + " enabled");''',
        "invalidate speaker requests on session enable")

    rep(controller,
        '''    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity = Utils.getActivity();''',
        '''    public static void onVideoTimeChanged(long timeMs) {
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        GeminiSpeakerDiarizationSidecar.maybeSchedule(
                VoiceOverTranslationPatch.getCurrentVideoIdForStudy(), sourceSegments, timeMs);
        Activity activity = Utils.getActivity();''',
        "schedule speaker sidecar from Morphe playhead")

    rep(controller,
        '''        long epoch = SpanishStudyRuntimeTelemetry.bumpEpoch();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);''',
        '''        long epoch = SpanishStudyRuntimeTelemetry.bumpEpoch();
        GeminiSpeakerDiarizationSidecar.onSessionBoundary();
        Utils.runOnMainThreadNowOrLater(SpanishSubtitleOverlay::hide);''',
        "invalidate speaker requests on disable")

    rep(controller,
        '''    public static boolean suppressNativeCaptions() {''',
        '''    public static boolean isSpeakerRequestCurrent(long requestEpoch, String videoId) {
        return requestEpoch == SpanishStudyRuntimeTelemetry.currentEpoch()
                && VoiceOverTranslationPatch.isSessionEnabled()
                && videoId != null
                && videoId.equals(VoiceOverTranslationPatch.getCurrentVideoIdForStudy());
    }

    public static String speakerLabel(TranscriptSegment segment) {
        return SpeakerAssignmentStore.speakerLabel(segment);
    }

    public static int speakerIndex(TranscriptSegment segment) {
        return SpeakerAssignmentStore.speakerIndex(segment);
    }

    public static boolean speakerVoicesEnabled() {
        android.content.Context context = Utils.getContext();
        return context != null && SpanishStudyPrefs.speakerVoicesEnabled(context);
    }

    public static String speakerProfileStatus() {
        return GeminiSpeakerDiarizationSidecar.status();
    }

    public static void refreshSpeakerVoices() {
        VoiceOverTranslationPatch.refreshSpeakerPrefetchForStudy();
    }

    public static boolean suppressNativeCaptions() {''',
        "expose isolated speaker APIs")

    text, start, end, body = section(controller, "public static String buildDiagnostics()",
                                     "\n    private static long fingerprint")
    method_start = body.index("    public static String buildDiagnostics()")
    new_diag = '''    public static String buildDiagnostics() {
        StringBuilder report = new StringBuilder();
        report.append("Spanish Dub Study v2.19.0 diagnostics\\n");
        report.append("coreArchitecture=morphe-v1.41.0-native\\n");
        report.append("segmentation=morphe-native-unchanged\\n");
        report.append("translationBatching=morphe-native-1500char+350char-first+single-stream\\n");
        report.append("ttsArchitecture=morphe-native-edge-cache-prefetch-window-adjustment\\n");
        report.append("subtitleTiming=morphe-tts-effective-end+source-fallback\\n");
        report.append("subtitleLinePolicy=up-to-4-lines-autosize\\n");
        report.append("snapshotPublication=content-fingerprint-deduplicated\\n");
        report.append("englishLeakGuard=openrouter-post-parse+pre-tts-source-aware\\n");
        report.append("cardinalityRecovery=aligned-prefix+split-first+singleton-google+transport-retry-once\\n");
        report.append("translationOutputSanitizer=batch-enum+duration+timestamp-firewall\\n");
        report.append("votRuntimeLifecycle=session-epoch+deterministic-provider-rearm+stale-worker-drop\\n");
        report.append("ttsLateStartPolicy=source-end+500ms-fresh-start-deadline\\n");
        report.append("speakerBackend=gemini-3.7-flash-youtube-audio-sidecar\\n");
        report.append("speakerIdentity=anonymous-acoustic-profiles-A-H+hysteresis\\n");
        report.append("speakerVoiceRouting=stable-morphe-edge-voice-variant-per-confirmed-profile\\n");
        report.append("speakerMicrophoneAccess=none\\n");
        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append('\\n');
        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append('\\n');
        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\\n');
        report.append("translationActive=").append(VoiceOverTranslationPatch.isTranslationActive()).append('\\n');
        report.append("translationProvider=").append(Settings.VOT_TRANSLATION_SERVICE.get()).append('\\n');
        report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append('\\n');
        Activity activity = Utils.getActivity();
        report.append("speakerRecognitionEnabled=").append(activity != null
                && SpanishStudyPrefs.speakerRecognitionEnabled(activity)).append('\\n');
        report.append("speakerKeyConfigured=").append(activity != null
                && !SpanishStudyPrefs.speakerApiKey(activity).isEmpty()).append('\\n');
        report.append("speakerVoicesEnabled=").append(activity != null
                && SpanishStudyPrefs.speakerVoicesEnabled(activity)).append('\\n');
        report.append("speakerLabelsEnabled=").append(activity != null
                && SpanishStudyPrefs.speakerLabelsEnabled(activity)).append('\\n');
        report.append("speakerProfiles=").append(SpeakerAssignmentStore.profileSummary()).append('\\n');
        report.append(GeminiSpeakerDiarizationSidecar.diagnostics());
        report.append(OpenRouterTelemetry.diagnostics());
        report.append(SpanishStudyRuntimeTelemetry.diagnostics());
        report.append("--- events ---\\n");
        report.append(SpanishStudyDiagnostics.dump());
        return report.toString();
    }
'''
    body = body[:method_start] + new_diag
    controller.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched: v2.19 diagnostics")

    rep(vot,
        '''    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */''',
        '''    /** Re-scan loaded text when a confirmed speaker changes the requested TTS voice. */
    public static void refreshSpeakerPrefetchForStudy() {
        Utils.runOnMainThreadNowOrLater(TtsPrefetcher::triggerRescan);
    }

    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */''',
        "add speaker-voice prefetch refresh")

    rep(sidecar,
        '''        if (!SpanishStudyPrefs.speakerRecognitionEnabled(context)) return;
        if (!SpanishStudyPrefs.geminiEnabled(context)
                || SpanishStudyPrefs.geminiApiKey(context).trim().isEmpty()) return;''',
        '''        if (!SpanishStudyPrefs.speakerRecognitionEnabled(context)) return;
        if (SpanishStudyPrefs.speakerApiKey(context).trim().isEmpty()) return;''',
        "decouple speaker backend from old Gemini translation toggle")

    rep(sidecar,
        '''    private static boolean inFlight;''',
        '''    private static boolean inFlight;
    private static long requestGeneration;
    private static int requests;
    private static int succeeded;
    private static int failed;
    private static int staleDrops;
    private static int lastHttpStatus;
    private static long lastLatencyMs;
    private static String lastError = "none";''',
        "add speaker runtime telemetry")

    rep(sidecar,
        '''        consecutiveFailures = 0;
        inFlight = false;
    }''',
        '''        consecutiveFailures = 0;
        inFlight = false;
        requestGeneration++;
        requests = 0;
        succeeded = 0;
        failed = 0;
        staleDrops = 0;
        lastHttpStatus = 0;
        lastLatencyMs = 0L;
        lastError = "none";
    }

    static synchronized void onSessionBoundary() {
        requestGeneration++;
        inFlight = false;
        backoffUntilWallMs = 0L;
    }''',
        "invalidate speaker generation on lifecycle boundaries")

    rep(sidecar,
        '''        final long clipStartMs = Math.max(0L, playheadMs - WINDOW_BEHIND_MS);
        final long clipEndMs = Math.max(clipStartMs + 1_000L, playheadMs + WINDOW_AHEAD_MS);
        final List<TranscriptSegment> snapshot = new ArrayList<>(window);
        SpanishStudyDiagnostics.record("SPEAKER", "analyzing " + clipStartMs + "-" + clipEndMs
                + "ms events=" + snapshot.size() + " model=" + DIARIZATION_MODEL);

        Utils.runOnBackgroundThread(() -> {
            boolean success = false;''',
        '''        final long clipStartMs = Math.max(0L, playheadMs - WINDOW_BEHIND_MS);
        final long clipEndMs = Math.max(clipStartMs + 1_000L, playheadMs + WINDOW_AHEAD_MS);
        final List<TranscriptSegment> snapshot = new ArrayList<>(window);
        final long requestEpoch = SpanishStudyRuntimeTelemetry.currentEpoch();
        final long generation;
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            generation = requestGeneration;
            requests++;
        }
        SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                + " action=start window=" + clipStartMs + "-" + clipEndMs
                + " events=" + snapshot.size() + " model=" + DIARIZATION_MODEL);

        Utils.runOnBackgroundThread(() -> {
            boolean success = false;
            boolean stale = false;
            long requestStartedMs = System.currentTimeMillis();''',
        "tag speaker work with epoch and generation")

    rep(sidecar,
        '''                if (proposals != null && proposals.size() == snapshot.size()) {
                    SpeakerAssignmentStore.commitBatch(snapshot, proposals);
                    success = true;
                    SpanishStudyDiagnostics.record("SPEAKER", "window complete profiles="
                            + SpeakerAssignmentStore.profileSummary());
                } else {''',
        '''                if (proposals != null && proposals.size() == snapshot.size()) {
                    synchronized (GeminiSpeakerDiarizationSidecar.class) {
                        stale = generation != requestGeneration
                                || !SpanishStudyController.isSpeakerRequestCurrent(requestEpoch, videoId);
                    }
                    if (stale) {
                        synchronized (GeminiSpeakerDiarizationSidecar.class) {
                            staleDrops++;
                            lastLatencyMs = System.currentTimeMillis() - requestStartedMs;
                        }
                        SpanishStudyDiagnostics.record("SPEAKER-WORKER", "requestEpoch=" + requestEpoch
                                + " currentEpoch=" + SpanishStudyRuntimeTelemetry.currentEpoch()
                                + " action=stale-drop events=" + snapshot.size());
                    } else {
                        SpeakerAssignmentStore.commitBatch(snapshot, proposals);
                        SpanishStudyController.refreshSpeakerVoices();
                        synchronized (GeminiSpeakerDiarizationSidecar.class) {
                            succeeded++;
                            lastLatencyMs = System.currentTimeMillis() - requestStartedMs;
                            lastError = "none";
                        }
                        success = true;
                        SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                                + " action=success events=" + snapshot.size()
                                + " latencyMs=" + (System.currentTimeMillis() - requestStartedMs)
                                + " profiles=" + SpeakerAssignmentStore.profileSummary());
                    }
                } else {''',
        "commit only current speaker proposals")

    rep(sidecar,
        '''            } catch (Exception ex) {
                SpanishStudyDiagnostics.record("SPEAKER", "sidecar unavailable "
                        + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));
            } finally {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    inFlight = false;
                    if (success) {''',
        '''            } catch (Exception ex) {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    failed++;
                    lastLatencyMs = System.currentTimeMillis() - requestStartedMs;
                    lastError = ex.getClass().getSimpleName() + ": " + safe(ex.getMessage());
                }
                SpanishStudyDiagnostics.record("SPEAKER-WORKER", "epoch=" + requestEpoch
                        + " action=failed latencyMs=" + (System.currentTimeMillis() - requestStartedMs)
                        + " error=" + ex.getClass().getSimpleName() + ": " + safe(ex.getMessage()));
            } finally {
                synchronized (GeminiSpeakerDiarizationSidecar.class) {
                    inFlight = false;
                    if (stale) {
                        consecutiveFailures = 0;
                        backoffUntilWallMs = 0L;
                    } else if (success) {''',
        "record speaker failures and avoid stale-result backoff")

    rep(sidecar,
        '''    static synchronized String status() {
        String base = SpeakerAssignmentStore.profileSummary();''',
        '''    static synchronized String diagnostics() {
        return "speakerRequests=" + requests + '\\n'
                + "speakerSucceeded=" + succeeded + '\\n'
                + "speakerFailed=" + failed + '\\n'
                + "speakerStaleDrops=" + staleDrops + '\\n'
                + "speakerLastHttpStatus=" + lastHttpStatus + '\\n'
                + "speakerLastLatencyMs=" + lastLatencyMs + '\\n'
                + "speakerLastError=" + safe(lastError) + '\\n';
    }

    static synchronized String status() {
        String base = SpeakerAssignmentStore.profileSummary();''',
        "publish speaker backend diagnostics")

    rep(sidecar,
        '''        String apiKey = SpanishStudyPrefs.geminiApiKey(context).trim();''',
        '''        String apiKey = SpanishStudyPrefs.speakerApiKey(context).trim();''',
        "use speaker-only key accessor")

    rep(sidecar,
        '''        conn.setRequestProperty("x-goog-api-key", apiKey);
        conn.setRequestProperty("Api-Revision", "2026-05-20");
        conn.setDoOutput(true);''',
        '''        conn.setRequestProperty("x-goog-api-key", apiKey);
        conn.setDoOutput(true);''',
        "remove obsolete Interactions revision header")

    rep(sidecar,
        '''        int code = conn.getResponseCode();
        String response = readAll(code >= 200 && code < 300''',
        '''        int code = conn.getResponseCode();
        synchronized (GeminiSpeakerDiarizationSidecar.class) {
            lastHttpStatus = code;
        }
        String response = readAll(code >= 200 && code < 300''',
        "record speaker HTTP status")

    rep(speaker_store,
        '''        Map<String,Integer> committedThisBatch=new LinkedHashMap<>();''',
        '''        Map<String,Integer> committedThisBatch=new LinkedHashMap<>();
        int acceptedCount=0,inheritedCount=0,rejectedCount=0,switchCount=0;''',
        "add assignment evidence counters")

    rep(speaker_store,
        '''            if(candidate.isEmpty()||confidence<0.70f)continue;''',
        '''            if(candidate.isEmpty()||confidence<0.70f){rejectedCount++;continue;}''',
        "count low-confidence speaker reject")

    rep(speaker_store,
        '''            if(!accept){
                if(!previous.isEmpty())put(seg,previous,Math.min(confidence,0.74f));
                continue;
            }

            put(seg,candidate,confidence);
            lastAcceptedSpeaker=candidate;''',
        '''            if(!accept){
                if(!previous.isEmpty()){
                    put(seg,previous,Math.min(confidence,0.74f));
                    inheritedCount++;
                }else rejectedCount++;
                continue;
            }

            if(!previous.isEmpty()&&!previous.equals(candidate))switchCount++;
            acceptedCount++;
            put(seg,candidate,confidence);
            lastAcceptedSpeaker=candidate;''',
        "count accepted/inherited/switch decisions")

    rep(speaker_store,
        '''        if(!committedThisBatch.isEmpty()){
            StringBuilder msg=new StringBuilder("profiles ");''',
        '''        SpanishStudyDiagnostics.record("SPEAKER-ASSIGN","events="+n
                +" accepted="+acceptedCount+" inherited="+inheritedCount
                +" rejected="+rejectedCount+" switches="+switchCount
                +" profiles="+profileSummary());
        if(!committedThisBatch.isEmpty()){
            StringBuilder msg=new StringBuilder("profiles ");''',
        "log speaker assignment evidence summary")

    rep(sheet,
        '''import android.content.Context;
import android.graphics.Color;''',
        '''import android.content.Context;
import android.graphics.Color;
import android.text.InputType;''',
        "add speaker key input type")

    rep(sheet,
        '''import android.widget.LinearLayout;''',
        '''import android.widget.EditText;
import android.widget.LinearLayout;''',
        "add speaker key edit text")

    rep(sheet,
        '''        content.addView(section(activity, "Diagnostics", secondary));''',
        '''        content.addView(section(activity, "Speaker recognition", secondary));
        content.addView(switchRow(activity, fg, "Recognize different speakers",
                "Anonymous A/B/C acoustic profiles from the public YouTube audio; never uses the phone microphone",
                SpanishStudyPrefs.speakerRecognitionEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerRecognitionEnabled(activity, value)));
        content.addView(switchRow(activity, fg, "Different Spanish voice per speaker",
                "Confirmed profiles use stable alternate Morphe Spanish voices",
                SpanishStudyPrefs.speakerVoicesEnabled(activity),
                value -> {
                    SpanishStudyPrefs.setSpeakerVoicesEnabled(activity, value);
                    SpanishStudyController.refreshSpeakerVoices();
                }));
        content.addView(switchRow(activity, fg, "Show speaker labels",
                "Show A, B, C… beside bilingual subtitles when the acoustic profile is confident",
                SpanishStudyPrefs.speakerLabelsEnabled(activity),
                value -> SpanishStudyPrefs.setSpeakerLabelsEnabled(activity, value)));
        LinearLayout speakerKey = valueRow(activity, fg, "Speaker analysis API key",
                SpanishStudyPrefs.speakerApiKey(activity).isEmpty() ? "Not set" : "Configured");
        speakerKey.setOnClickListener(v -> showSpeakerKeyDialog(activity));
        content.addView(speakerKey);
        LinearLayout speakerStatus = valueRow(activity, fg, "Speaker profiles",
                SpanishStudyController.speakerProfileStatus());
        speakerStatus.setOnClickListener(v -> Toast.makeText(activity,
                SpanishStudyController.speakerProfileStatus(), Toast.LENGTH_SHORT).show());
        content.addView(speakerStatus);

        content.addView(section(activity, "Diagnostics", secondary));''',
        "add speaker controls and status UI")

    rep(sheet,
        '''    private static void showDiagnostics(Activity activity) {''',
        '''    private static void showSpeakerKeyDialog(Activity activity) {
        EditText key = new EditText(activity);
        key.setSingleLine(true);
        key.setHint("Gemini API key for speaker analysis");
        key.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        key.setText(SpanishStudyPrefs.speakerApiKey(activity));
        key.setPadding(Dim.dp16, Dim.dp8, Dim.dp16, Dim.dp8);
        new AlertDialog.Builder(activity)
                .setTitle("Speaker recognition")
                .setMessage("This key is used only by the background speaker-diarization sidecar. "
                        + "Your normal Morphe/OpenRouter translation provider is unchanged.")
                .setView(key)
                .setPositiveButton("Save", (dialog, which) -> {
                    SpanishStudyPrefs.setSpeakerApiKey(activity, key.getText().toString());
                    Toast.makeText(activity,
                            SpanishStudyPrefs.speakerApiKey(activity).isEmpty()
                                    ? "Speaker analysis key cleared" : "Speaker analysis key saved",
                            Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("Cancel", null)
                .show();
    }

    private static void showDiagnostics(Activity activity) {''',
        "add speaker key configuration dialog")

    rep(subtitles,
        '''        String sourceText = source == null || source.text == null ? "" : source.text.trim();
        String translatedText = translated == null || translated.text == null ? "" : translated.text.trim();

        if (SpanishStudyPrefs.showSubtitles(a)''',
        '''        String sourceText = source == null || source.text == null ? "" : source.text.trim();
        String translatedText = translated == null || translated.text == null ? "" : translated.text.trim();
        String speaker = SpanishStudyPrefs.speakerLabelsEnabled(a)
                ? SpanishStudyController.speakerLabel(source) : "";
        String speakerPrefix = speaker == null || speaker.isBlank() ? "" : speaker + " · ";

        if (SpanishStudyPrefs.showSubtitles(a)''',
        "resolve speaker label for active source cue")

    rep(subtitles,
        '''            if (!translatedText.contentEquals(translatedView.getText())) translatedView.setText(translatedText);''',
        '''            String shownTranslated = speakerPrefix + translatedText;
            if (!shownTranslated.contentEquals(translatedView.getText())) translatedView.setText(shownTranslated);''',
        "show speaker label on Spanish subtitle")

    rep(subtitles,
        '''            if (!sourceText.contentEquals(sourceView.getText())) sourceView.setText(sourceText);''',
        '''            String shownSource = (translatedView.getVisibility() == View.VISIBLE ? "" : speakerPrefix) + sourceText;
            if (!shownSource.contentEquals(sourceView.getText())) sourceView.setText(shownSource);''',
        "show speaker label on English-only subtitle")

    print("v2.19 speaker backend and observability integration complete")


if __name__ == "__main__":
    main()
