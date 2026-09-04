#!/usr/bin/env python3
"""v2.15.0: TTS provenance, scheduler diagnostics, and study UI cleanup."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def insert_after(path: Path, anchor: str, addition: str, label: str) -> None:
    rep(path, anchor, anchor + addition, label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v215d_tts_ui.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    for p in (vot, controller, sheet):
        if not p.is_file():
            raise RuntimeError(f"missing required source: {p}")

    # ------------------------------------------------------------------------------------------
    # TTS/scheduler provenance and completion visibility.
    # ------------------------------------------------------------------------------------------
    rep(controller,
        '''    public static void onDubAudioReady(TranscriptSegment segment,int index,long durationMs){
        SpanishStudyDiagnostics.record("TTS", "ready index=" + index + " duration=" + durationMs + "ms");''',
        '''    public static void onDubAudioReady(TranscriptSegment segment,int index,long durationMs){
        SpanishStudyDiagnostics.record("TTS", "ready index=" + index + " duration=" + durationMs + "ms");
        SpanishStudyDiagnostics.record("TTS-SOURCE", "ready index=" + index + " "
                + TranslationProvenanceLog.describe(index,segment==null?null:segment.text));''',
        "attach translation provenance to synthesized audio")
    rep(controller,
        '''    public static void onDubPlaybackStarted(TranscriptSegment segment,int index,long durationMs,float rate){
        SpanishStudyDiagnostics.record("TTS", "playing index=" + index + " duration=" + durationMs + "ms rate=" + rate);''',
        '''    public static void onDubPlaybackStarted(TranscriptSegment segment,int index,long durationMs,float rate){
        SpanishStudyDiagnostics.record("TTS", "playing index=" + index + " duration=" + durationMs + "ms rate=" + rate);
        SpanishStudyDiagnostics.record("TTS-SOURCE", "playing index=" + index + " "
                + TranslationProvenanceLog.describe(index,segment==null?null:segment.text));''',
        "attach provenance to playback start")
    rep(controller,
        '''    public static void onDubPlaybackDone(TranscriptSegment segment,int index){
        DubEventStateStore.markDone(segment,index);
    }''',
        '''    public static void onDubPlaybackDone(TranscriptSegment segment,int index){
        SpanishStudyDiagnostics.record("TTS", "done index=" + index);
        DubEventStateStore.markDone(segment,index);
    }''',
        "diagnose TTS completion")

    insert_after(controller,
        '''        TranscriptCorrectionStore.clear();
''',
        '''        TranslationProvenanceLog.clear();
''',
        "clear translation provenance per video")

    # One diagnostic line per blocked candidate rather than flooding every video-time tick.
    rep(vot,
        '''    private static volatile int pendingSpeechIndex = -1;''',
        '''    private static volatile int pendingSpeechIndex = -1;
    private static volatile int lastBlockedSpeechIndex = -1;''',
        "track scheduler block diagnostic")
    old_dispatch = '''                        if (app.spanishstudy.vot.SpeechDispatchPolicy.mayDispatch(
                                i, lastSpokenIndex, pendingSpeechIndex,
                                ttsEngine.isSpeaking(), wasExplicitSeek)) {
                            final int candidateIndex = i;
                            pendingSpeechIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        }'''
    new_dispatch = '''                        if (app.spanishstudy.vot.SpeechDispatchPolicy.mayDispatch(
                                i, lastSpokenIndex, pendingSpeechIndex,
                                ttsEngine.isSpeaking(), wasExplicitSeek)) {
                            final int candidateIndex = i;
                            lastBlockedSpeechIndex = -1;
                            pendingSpeechIndex = i;
                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex
                                    + " videoTime: " + timeMs + " "
                                    + SpanishStudyController.dubDiagnostic(seg));
                            speak(seg, i);
                        } else if (lastBlockedSpeechIndex != i) {
                            lastBlockedSpeechIndex = i;
                            SpanishStudyDiagnostics.record("SCHEDULER", "blocked index=" + i
                                    + " lastSpoken=" + lastSpokenIndex + " pending=" + pendingSpeechIndex
                                    + " speaking=" + ttsEngine.isSpeaking() + " explicitSeek=" + wasExplicitSeek);
                        }'''
    rep(vot, old_dispatch, new_dispatch, "explain scheduler stalls without log flooding")
    rep(vot,
        '''        pendingSpeechIndex = -1;
        isTestSpeaking = false;''',
        '''        pendingSpeechIndex = -1;
        lastBlockedSpeechIndex = -1;
        isTestSpeaking = false;''',
        "clear scheduler block marker on stop/seek/video change")

    # ------------------------------------------------------------------------------------------
    # Diagnostics/UI truthfulness and cleanup.
    # ------------------------------------------------------------------------------------------
    insert_after(controller,
                 "import app.morphe.extension.youtube.patches.voiceovertranslation.VoiceOverTranslationPatch;\n",
                 "import app.morphe.extension.youtube.settings.Settings;\n",
                 "import normal Morphe provider setting for study UI")

    insert_after(controller,
        '''    public static String dubBufferStatus(){
        return VoiceOverTranslationPatch.getDubBufferStatusForStudy();
    }
''',
        '''
    public static String translationProviderStatus(){
        String provider=Settings.VOT_TRANSLATION_SERVICE.get();
        if("openrouter".equals(provider)){
            String model=Settings.VOT_OPENROUTER_MODEL.get().trim();
            return model.isEmpty()?"OpenRouter":"OpenRouter · "+model;
        }
        if("mymemory".equals(provider))return "MyMemory";
        return "Google";
    }
''',
        "expose normal Morphe provider in study UI")

    rep(controller,
        '''        report.append("loading=").append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\\n');''',
        '''        report.append("startupReady=").append(!latest.isEmpty()).append('\\n');
        report.append("backgroundTranslationActive=")
                .append(VoiceOverTranslationPatch.isTranscriptLoading()).append('\\n');''',
        "separate startup readiness from background translation")

    text = controller.read_text(encoding="utf-8")
    text = text.replace("Spanish Dub Study v2.14.1 diagnostics", "Spanish Dub Study v2.15.0 diagnostics")
    text = text.replace("providerRuntimeTelemetry=v2.14.1", "providerRuntimeTelemetry=v2.15.0")
    old_batch_diag = '''        report.append("startupTranslationBatch=").append(StartupTranslationPlanner.MAX_INITIAL_SEGMENTS)
                .append(" segments/").append(StartupTranslationPlanner.MAX_INITIAL_CHARS).append(" chars\\n");'''
    if old_batch_diag not in text:
        raise RuntimeError("startupTranslationBatch diagnostics anchor missing")
    new_batch_diag = '''        report.append("realtimeTranslationBatch=")
                .append(RealtimeTranslationPlanner.MAX_BATCH_SEGMENTS).append(" segments/")
                .append(RealtimeTranslationPlanner.MAX_BATCH_CHARS).append(" chars\\n");
        report.append("openRouterParallelism=")
                .append(RealtimeTranslationPlanner.OPENROUTER_PARALLEL_REQUESTS).append('\\n');
        report.append("translationContext=video-metadata+whole-video-terms+nearby-raw-cues\\n");
        report.append("rawCaptionCues=").append(VideoTranslationContext.rawCueCount()).append('\\n');
        report.append("sourceRepair=local-boundary-repair+implicit-ai-asr-repair\\n");
        report.append("translationProvenanceEntries=").append(TranslationProvenanceLog.size()).append('\\n');'''
    text = text.replace(old_batch_diag, new_batch_diag, 1)
    controller.write_text(text, encoding="utf-8")
    print("patched: v2.15 diagnostic header/context/realtime policy")

    # v2.10 relabeled the old Gemini credential row to "Advanced analysis (future)" and disabled
    # its click action. Replace that final post-chain shape with the provider that actually controls
    # translation now.
    rep(sheet,
        '''        LinearLayout geminiRow=valueRow(activity,fg,"Advanced analysis (future)",
                SpanishStudyPrefs.geminiApiKey(activity).trim().isEmpty()
                        ? "Not configured"
                        : SpanishStudyPrefs.geminiModel(activity));
        geminiRow.setOnClickListener(v->Toast.makeText(activity,"Cloud analysis is disabled in this stable build",Toast.LENGTH_SHORT).show());
        content.addView(geminiRow);''',
        '''        LinearLayout providerRow=valueRow(activity,fg,"Translation provider",
                SpanishStudyController.translationProviderStatus());
        providerRow.setOnClickListener(v->Toast.makeText(activity,
                "Change provider/model in Morphe's normal Voice-over translation settings.",
                Toast.LENGTH_LONG).show());
        content.addView(providerRow);
        TextView translationNote=new TextView(activity);
        translationNote.setText("AI providers get compact context from this video's metadata and nearby raw English captions. No separate full-video AI analysis runs before playback.");
        translationNote.setTextColor(secondary);
        translationNote.setTextSize(12);
        translationNote.setPadding(0,Dim.dp4,0,Dim.dp8);
        content.addView(translationNote);''',
        "show authoritative Morphe translation provider")

    text = sheet.read_text(encoding="utf-8")
    replacements = {
        "Paired bilingual layout: Spanish on top and the exact matching English source below. Both switch on one shared source-video event. Short sentences stay whole; longer speech prefers real punctuation and source timing pauses. If no trustworthy pause exists, the phrase stays together rather than being chopped at an arbitrary width.":
            "Spanish stays above the matching English source. Phrase boundaries follow source timing, punctuation, and conservative local repair.",
        "Spanish playback is hard-linked to the YouTube transport: pause/buffering pauses the Edge voice in place, resume continues the same MP3, and seeking cancels stale speech and re-targets the source phrase. Natural phrasing uses punctuation and TTS word timing only—no microphone, playback Visualizer, speaker recording, or room-audio measurement. Dub audio stays in a small bounded in-memory cache only; full videos are not saved to storage.":
            "Dub playback follows YouTube pause, resume, speed, and seek. Nearby speech is cached only in memory; full videos are not saved.",
        "Original-audio volume and max speech rate remain in Morphe's normal voice-over settings. The dub buffer prepares nearby phrases ahead of the playhead, but memory use is bounded and disappears when the app process ends.":
            "Original-audio volume and preferred/max speech rate remain in Morphe's normal Voice-over translation settings.",
        "If Spanish fails, open this sheet after reproducing it, tap Copy dub diagnostics, and paste the report into ChatGPT. It contains pipeline state and errors, not your Gemini API key or microphone audio.":
            "After reproducing a problem, copy diagnostics and paste them into ChatGPT. Keys and microphone audio are never included."
    }
    for old, new in replacements.items():
        if old not in text:
            raise RuntimeError("UI cleanup text anchor missing: " + old[:40])
        text = text.replace(old, new, 1)
    sheet.write_text(text, encoding="utf-8")
    print("patched: concise Spanish study UI copy")
    print("v2.15d TTS/scheduler/UI integration complete")


if __name__ == "__main__":
    main()
