#!/usr/bin/env python3
"""Add an in-app diagnostic trail for caption/translation/TTS failures.

The user can copy a compact report from Spanish study settings and paste it into ChatGPT. No API keys,
full transcripts, microphone data, or room audio are included. The report focuses on state transitions,
counts, timestamps, batch windows and error classes.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    vot = votpkg / "VoiceOverTranslationPatch.java"
    translator = votpkg / "TranscriptTranslator.java"

    # ----- Controller events ------------------------------------------------------------------
    rep(controller,
'''    public static void onTranscriptUpdated(List<TranscriptSegment> segments){
        latest=segments==null?new ArrayList<>():new ArrayList<>(segments);
        SpanishSubtitleOverlay.setSegments(latest);
    }''',
'''    public static void onTranscriptUpdated(List<TranscriptSegment> segments){
        latest=segments==null?new ArrayList<>():new ArrayList<>(segments);
        SpanishStudyDiagnostics.record("TRANSCRIPT", "published events=" + latest.size());
        SpanishSubtitleOverlay.setSegments(latest);
    }''', "diagnose translated transcript publication")

    rep(controller,
'''    public static void onDubAudioReady(TranscriptSegment segment,int index,long durationMs){
        DubEventStateStore.markReady(segment,index,durationMs);
    }''',
'''    public static void onDubAudioReady(TranscriptSegment segment,int index,long durationMs){
        SpanishStudyDiagnostics.record("TTS", "ready index=" + index + " duration=" + durationMs + "ms");
        DubEventStateStore.markReady(segment,index,durationMs);
    }''', "diagnose TTS readiness")

    rep(controller,
'''    public static void onDubPlaybackStarted(TranscriptSegment segment,int index,long durationMs,float rate){
        DubEventStateStore.markPlaying(segment,index,durationMs,rate);
    }''',
'''    public static void onDubPlaybackStarted(TranscriptSegment segment,int index,long durationMs,float rate){
        SpanishStudyDiagnostics.record("TTS", "playing index=" + index + " duration=" + durationMs + "ms rate=" + rate);
        DubEventStateStore.markPlaying(segment,index,durationMs,rate);
    }''', "diagnose TTS playback start")

    rep(controller,
'''    public static int onDubPlaybackFailed(TranscriptSegment segment,int index){
        return DubEventStateStore.markFailure(segment,index);
    }''',
'''    public static int onDubPlaybackFailed(TranscriptSegment segment,int index){
        int failures=DubEventStateStore.markFailure(segment,index);
        SpanishStudyDiagnostics.record("TTS", "failed index=" + index + " count=" + failures);
        return failures;
    }''', "diagnose TTS failures")

    rep(controller,
'''    public static void onDubPlaybackSkipped(TranscriptSegment segment,int index){
        DubEventStateStore.markSkipped(segment,index);
    }''',
'''    public static void onDubPlaybackSkipped(TranscriptSegment segment,int index){
        SpanishStudyDiagnostics.record("TTS", "skipped index=" + index);
        DubEventStateStore.markSkipped(segment,index);
    }''', "diagnose TTS skips")

    rep(controller,
'''    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments){
        final List<TranscriptSegment> snapshot=segments==null?new ArrayList<>():new ArrayList<>(segments);''',
'''    public static void onSourceTranscriptFetched(List<TranscriptSegment> segments){
        final List<TranscriptSegment> snapshot=segments==null?new ArrayList<>():new ArrayList<>(segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "source fetched events=" + snapshot.size());''',
        "diagnose source caption fetch")

    rep(controller,
'''    public static void onVideoTimeChanged(long timeMs){
        Activity activity=Utils.getActivity();''',
'''    public static void onVideoTimeChanged(long timeMs){
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity=Utils.getActivity();''', "sample video clock")

    rep(controller,
'''    public static void onVideoCleared(){
        latest=new ArrayList<>();''',
'''    public static void onVideoCleared(){
        SpanishStudyDiagnostics.record("VIDEO", "overlay state cleared");
        latest=new ArrayList<>();''', "diagnose video clears")

    rep(controller,
'''    public static void onSessionDisabled(){SpanishSubtitleOverlay.hide();}''',
'''    public static void onSessionDisabled(){
        SpanishStudyDiagnostics.record("SESSION", "disabled");
        SpanishSubtitleOverlay.hide();
    }''', "diagnose session disable")

    # patch_speaker_ui has already inserted its APIs before this anchor.
    rep(controller,
'''    public static boolean isGeminiEnabled(Activity activity){''',
'''    public static String diagnosticsSummary(){
        return SpanishStudyDiagnostics.summary();
    }

    public static void clearDiagnostics(Activity activity){
        SpanishStudyDiagnostics.clear();
        if(activity!=null)Toast.makeText(activity,"Dub diagnostics cleared",Toast.LENGTH_SHORT).show();
    }

    public static void copyDiagnostics(Activity activity){
        if(activity==null)return;
        StringBuilder report=new StringBuilder();
        report.append("Spanish Dub Study v2.6.1 diagnostics\\n");
        report.append("video=").append(VoiceOverTranslationPatch.getCurrentVideoIdForStudy()).append('\\n');
        report.append("session=").append(VoiceOverTranslationPatch.isSessionEnabled()).append('\\n');
        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\\n');
        report.append("publishedSegments=").append(latest.size()).append('\\n');
        report.append("dubBuffer=").append(VoiceOverTranslationPatch.getDubBufferStatusForStudy()).append('\\n');
        report.append("geminiEnabled=").append(SpanishStudyPrefs.geminiEnabled(activity)).append('\\n');
        report.append("geminiModel=").append(SpanishStudyPrefs.geminiModel(activity)).append('\\n');
        report.append("videoGrounding=").append(SpanishStudyPrefs.videoGroundingEnabled(activity)).append('\\n');
        report.append("speakerRecognition=").append(SpanishStudyPrefs.speakerRecognitionEnabled(activity)).append('\\n');
        report.append("speakerVoices=").append(SpanishStudyPrefs.speakerVoicesEnabled(activity)).append('\\n');
        report.append("--- events ---\\n").append(SpanishStudyDiagnostics.dump());
        android.content.ClipboardManager clipboard=(android.content.ClipboardManager)
                activity.getSystemService(android.content.Context.CLIPBOARD_SERVICE);
        if(clipboard!=null){
            clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Spanish dub diagnostics",report.toString()));
            Toast.makeText(activity,"Dub diagnostics copied — paste them into ChatGPT",Toast.LENGTH_LONG).show();
        }
    }

    public static boolean isGeminiEnabled(Activity activity){''', "add diagnostic report APIs")

    # ----- Sheet controls ----------------------------------------------------------------------
    rep(sheet,
'''        content.addView(audioNote);

        content.addView(section(activity,"Vocabulary",secondary));''',
'''        content.addView(audioNote);

        content.addView(section(activity,"Diagnostics",secondary));
        LinearLayout copyDiagnostics=valueRow(activity,fg,"Copy dub diagnostics",
                SpanishStudyController.diagnosticsSummary());
        copyDiagnostics.setOnClickListener(v->SpanishStudyController.copyDiagnostics(activity));
        content.addView(copyDiagnostics);
        LinearLayout clearDiagnostics=valueRow(activity,fg,"Clear diagnostics","Clear");
        clearDiagnostics.setOnClickListener(v->SpanishStudyController.clearDiagnostics(activity));
        content.addView(clearDiagnostics);
        TextView diagnosticNote=new TextView(activity);
        diagnosticNote.setText("If Spanish fails, open this sheet after reproducing it, tap Copy dub diagnostics, and paste the report into ChatGPT. It contains pipeline state and errors, not your Gemini API key or microphone audio.");
        diagnosticNote.setTextColor(secondary);
        diagnosticNote.setTextSize(12);
        diagnosticNote.setPadding(0,Dim.dp4,0,Dim.dp8);
        content.addView(diagnosticNote);

        content.addView(section(activity,"Vocabulary",secondary));''', "add diagnostic UI")

    # ----- Core transcript lifecycle ------------------------------------------------------------
    rep(vot,
'''import app.spanishstudy.vot.SpanishStudyController;
''',
'''import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;
''', "import diagnostics into VoT")

    # patch_playhead_priority has already added the VideoInformation.getVideoTime seed.
    rep(vot,
'''        videoPositionHint = Math.max(0L, VideoInformation.getVideoTime());
        lastSpokenIndex = -1;''',
'''        try {
            long liveTime=VideoInformation.getVideoTime();
            if(liveTime>=0)videoPositionHint=liveTime;
        } catch(Throwable clockError) {
            SpanishStudyDiagnostics.record("VIDEO", "initial clock read failed: "
                    + clockError.getClass().getSimpleName());
        }
        videoPositionHint=Math.max(0L,videoPositionHint);
        SpanishStudyDiagnostics.record("VIDEO", "newVideoLoaded id=" + videoId
                + " hint=" + videoPositionHint + " player=" + PlayerType.getCurrent()
                + " enabled=" + Settings.VOT_ENABLED.get() + " session=" + sessionEnabled);
        lastSpokenIndex = -1;''', "safe initial clock seed with diagnostics")

    rep(vot,
'''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) return;
        TtsPrefetcher.updateVideo(videoId, segments);
        loadTranscript(videoId);''',
'''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) {
            SpanishStudyDiagnostics.record("VIDEO", "load skipped: VoT/session disabled");
            return;
        }
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) {
            SpanishStudyDiagnostics.record("VIDEO", "load deferred: INLINE_MINIMAL");
            return;
        }
        TtsPrefetcher.updateVideo(videoId, segments);
        SpanishStudyDiagnostics.record("CAPTIONS", "requesting transcript at hint=" + videoPositionHint);
        loadTranscript(videoId);''', "diagnose transcript load gate")

    rep(vot,
'''    private static void loadTranscript(String videoId) {
        Logger.printDebug(() -> "loadTranscript: " + videoId);
        Utils.verifyOnMainThread();
        if (isLoading) return;
        isLoading = true;''',
'''    private static void loadTranscript(String videoId) {
        Logger.printDebug(() -> "loadTranscript: " + videoId);
        Utils.verifyOnMainThread();
        if (isLoading) {
            SpanishStudyDiagnostics.record("CAPTIONS", "load ignored because another transcript is loading");
            return;
        }
        SpanishStudyDiagnostics.record("CAPTIONS", "load started video=" + videoId + " hint=" + videoPositionHint);
        isLoading = true;''', "diagnose transcript loader start")

    rep(vot,
'''            } catch (Exception ex) {
                logError(() -> "Transcript fetch failed", ex);''',
'''            } catch (Exception ex) {
                SpanishStudyDiagnostics.record("ERROR", "Transcript fetch failed: "
                        + ex.getClass().getSimpleName() + ": " + String.valueOf(ex.getMessage()));
                logError(() -> "Transcript fetch failed", ex);''', "capture transcript fetch exception")

    # ----- Progressive translation dispatch ----------------------------------------------------
    rep(translator,
'''import app.morphe.extension.youtube.settings.Settings;
import app.spanishstudy.vot.GeminiTranslator;
''',
'''import app.morphe.extension.youtube.settings.Settings;
import app.spanishstudy.vot.GeminiTranslator;
import app.spanishstudy.vot.SpanishStudyDiagnostics;
''', "import diagnostics into translator")

    rep(translator,
'''                List<TranscriptSegment> batch = batches.get(index);
                int offset = 0;''',
'''                List<TranscriptSegment> batch = batches.get(index);
                if(!batch.isEmpty()){
                    TranscriptSegment first=batch.get(0);
                    TranscriptSegment last=batch.get(batch.size()-1);
                    SpanishStudyDiagnostics.record("BATCH", "pick index=" + index
                            + " playhead=" + timeMs + " window=" + first.startMs + "-" + last.endMs
                            + " events=" + batch.size());
                }
                int offset = 0;''', "record selected translation batch")

    rep(translator,
'''                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,
                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));
                translatingBatchIndex = -1;''',
'''                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,
                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));
                SpanishStudyDiagnostics.record("BATCH", "returned index=" + index
                        + " outputs=" + (translated == null ? -1 : translated.size()));
                translatingBatchIndex = -1;''', "record translation batch completion")

    print("Runtime diagnostics integration complete")


if __name__ == "__main__":
    main()
