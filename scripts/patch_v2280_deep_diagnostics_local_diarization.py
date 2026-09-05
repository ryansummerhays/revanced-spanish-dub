#!/usr/bin/env python3
"""v2.28: stock Morphe VOT behavior + read-only deep diagnostics + local speaker capture probe."""
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


def rep_section(path: Path, start_marker: str, end_marker: str,
                old: str, new: str, label: str, count: int = 1) -> None:
    text, start, end, body = section(path, start_marker, end_marker)
    found = body.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} section anchor(s), found {found}")
    body = body.replace(old, new, count)
    path.write_text(text[:start] + body + text[end:], encoding="utf-8")
    print("patched:", label)


def copy_sources(root: Path, repo: Path) -> None:
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    target.mkdir(parents=True, exist_ok=True)
    sources = {
        "SpanishStudyPrefs.java": repo / "overlay/v228/app/spanishstudy/vot/SpanishStudyPrefs.java",
        "SpanishStudyDiagnostics.java": repo / "overlay/v228/app/spanishstudy/vot/SpanishStudyDiagnostics.java",
        "LocalSpeakerDiarizer.java": repo / "overlay/v228/app/spanishstudy/vot/LocalSpeakerDiarizer.java",
        "SpanishStudyController.java": repo / "overlay/v228/app/spanishstudy/vot/SpanishStudyController.java",
        "SpanishSubtitleOverlay.java": repo / "overlay/v228/app/spanishstudy/vot/SpanishSubtitleOverlay.java",
        "SpanishStudySheet.java": repo / "overlay/v228/app/spanishstudy/vot/SpanishStudySheet.java",
        "SubtitlePagePolicy.java": repo / "overlay/v224/app/spanishstudy/vot/SubtitlePagePolicy.java",
        "BilingualCardPolicy.java": repo / "overlay/v223/app/spanishstudy/vot/BilingualCardPolicy.java",
        "SubtitleLinePolicy.java": repo / "overlay/v225/app/spanishstudy/vot/SubtitleLinePolicy.java",
    }
    for name, src in sources.items():
        if not src.is_file():
            raise RuntimeError(f"missing source: {src}")
        shutil.copy2(src, target / name)
        print("copied:", name)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2280_deep_diagnostics_local_diarization.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    copy_sources(root, repo)

    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    fetcher = pkg / "TranscriptFetcher.java"
    translator = pkg / "TranscriptTranslator.java"
    engine = pkg / "TtsEngine.java"
    prefetch = pkg / "TtsPrefetcher.java"
    cache = pkg / "TtsCache.java"
    bottom_sheet = pkg / "VotBottomSheet.java"
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    auto = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/AutoCaptionsPatch.java"

    for path in (vot, fetcher, translator, engine, prefetch, cache, bottom_sheet, player_volume, auto):
        if not path.is_file():
            raise RuntimeError(f"missing Morphe source: {path}")

    # ------------------------------------------------------------------
    # Passive subtitle lifecycle + detailed VOT/TTS decision tracing.
    # ------------------------------------------------------------------
    rep(vot,
        "import app.morphe.extension.youtube.shared.VideoState;\n",
        "import app.morphe.extension.youtube.shared.VideoState;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "VOT study imports")

    rep(vot,
        "    public static void newVideoLoaded(String videoId) {\n",
        "    public static void newVideoLoaded(String videoId) {\n"
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE,\n"
        "                \"newVideoLoaded id=\" + videoId + \" player=\" + PlayerType.getCurrent()\n"
        "                        + \" state=\" + VideoState.getCurrent() + \" session=\" + sessionEnabled);\n",
        "log newVideoLoaded")

    rep(vot,
        '''                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();''',
        '''                    currentVideoId = "";
                    segments = new ArrayList<>();
                    TtsPrefetcher.clear();
                    SpanishStudyController.onVideoCleared();''',
        "clear study overlay when player closes")

    rep(vot,
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        httpErrorDialogShownThisVideo = false;''',
        '''        currentVideoId = videoId;
        segments = new ArrayList<>();
        SpanishStudyController.onVideoCleared();
        httpErrorDialogShownThisVideo = false;''',
        "clear study state on new video")

    rep(vot,
        '''        videoPositionHint = timeMs;
        // Video state can be null until the overlay is activated the first time.''',
        '''        videoPositionHint = timeMs;
        SpanishStudyController.onVideoTimeChanged(timeMs);
        // Video state can be null until the overlay is activated the first time.''',
        "drive subtitle/speaker observers")

    rep(vot,
        '''                Logger.printDebug(() -> "videoTimeChanged jump detected: " + timeSinceLastUpdate + "ms");
                wasExplicitSeek = true;''',
        '''                Logger.printDebug(() -> "videoTimeChanged jump detected: " + timeSinceLastUpdate + "ms");
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE,
                        "seek/jump prev=" + prevVideoTimeMs + " now=" + timeMs
                                + " delta=" + timeSinceLastUpdate + " threshold=" + jumpThreshold);
                wasExplicitSeek = true;''',
        "log VOT seek jump")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Lazily creates the System TTS instance",
        '''        final String loadService = Settings.VOT_TRANSLATION_SERVICE.get();

        Utils.runOnBackgroundThread(() -> {''',
        '''        final String loadService = Settings.VOT_TRANSLATION_SERVICE.get();
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE,
                "loadTranscript start video=" + videoId + " target=" + loadLang
                        + " service=" + loadService);

        Utils.runOnBackgroundThread(() -> {''',
        "log transcript worker start")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Lazily creates the System TTS instance",
        '''                                segments = updated;''',
        '''                                segments = updated;
                                SpanishStudyController.onTranscriptUpdated(updated);''',
        "observe progressive transcript snapshots")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Lazily creates the System TTS instance",
        '''                        if (segments.isEmpty()) segments = fetched;
                        TtsPrefetcher.updateVideo(videoId, segments);''',
        '''                        if (segments.isEmpty()) segments = fetched;
                        SpanishStudyController.onTranscriptUpdated(segments);
                        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE,
                                "loadTranscript publish video=" + videoId + " segments=" + segments.size());
                        TtsPrefetcher.updateVideo(videoId, segments);''',
        "observe final transcript snapshot")

    rep_section(vot, "private static void loadTranscript(String videoId)",
                "\n    /** Lazily creates the System TTS instance",
        '''            } catch (Exception ex) {
                logError(() -> "Transcript fetch failed", ex);''',
        '''            } catch (Exception ex) {
                SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.LIFECYCLE,
                        "Transcript fetch failed video=" + videoId, ex);
                logError(() -> "Transcript fetch failed", ex);''',
        "log transcript worker exception")

    rep(vot,
        '''        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();
        lastSpokenIndex = -1;''',
        '''        Settings.VOT_SESSION_ENABLED.save(false);
        stopTts();
        SpanishStudyController.onSessionDisabled();
        lastSpokenIndex = -1;''',
        "observe session disabled")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''        currentTtsBaseRate = rate;
        lastAppliedPlaybackSpeed = VideoInformation.getPlaybackSpeed();''',
        '''        currentTtsBaseRate = rate;
        lastAppliedPlaybackSpeed = VideoInformation.getPlaybackSpeed();
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "speak index=" + index + " voice=" + voice + " lang=" + lang
                        + " videoMs=" + lastVideoTimeMs + " source=" + seg.startMs + "-" + seg.endMs
                        + " playback=" + seg.playbackStartMs + "-" + seg.playbackEndMs
                        + " speakFrom=" + speakFromMs + " availableMs=" + availableMs
                        + " speechMs=" + speechDurationMs + " remainingMs=" + remainingSpeechMs
                        + " seekIntoMs=" + startTimeMs + " rate=" + rate
                        + " videoSpeed=" + VideoInformation.getPlaybackSpeed()
                        + " predictedEnd=" + ttsEndVideoTimeMs
                        + " text=" + SpanishStudyDiagnostics.text(seg.text));''',
        "log stock speak decision")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);
        if (cached != null) {''',
        '''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "speak cache index=" + index + " hit=" + (cached != null)
                        + " bytes=" + (cached == null ? 0 : cached.length));
        if (cached != null) {''',
        "log speak cache outcome")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''        Utils.runOnBackgroundThread(() -> {
            byte[] data;
            try {
                data = ttsEngine.prefetch(seg.text, voice, lang);''',
        '''        Utils.runOnBackgroundThread(() -> {
            byte[] data;
            final long diagSynthesisStart = System.currentTimeMillis();
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                    "on-demand synthesis start index=" + index + " voice=" + voice);
            try {
                data = ttsEngine.prefetch(seg.text, voice, lang);''',
        "log on-demand synthesis start")

    rep_section(vot, "private static void speak(TranscriptSegment seg, int index)",
                "\n    private static void triggerNextSegmentCheck()",
        '''            if (data.length > 0) {
                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);
            }''',
        '''            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                    "on-demand synthesis done index=" + index + " bytes=" + data.length
                            + " latencyMs=" + (System.currentTimeMillis() - diagSynthesisStart));
            if (data.length > 0) {
                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);
            }''',
        "log on-demand synthesis completion")

    rep(vot,
        '''    public static void onVideoSeeked() {
        Logger.printDebug(() -> "onVideoSeeked");''',
        '''    public static void onVideoSeeked() {
        Logger.printDebug(() -> "onVideoSeeked");
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.LIFECYCLE,
                "onVideoSeeked lastVideoMs=" + lastVideoTimeMs + " activeIndex=" + lastSpokenIndex);''',
        "log programmatic seek")

    study_getters = r'''
    /** Read-only study hook: current video id. */
    public static String getCurrentVideoIdForStudy() { return currentVideoId; }

    /** Read-only study hook: whether stock transcript loading is active. */
    public static boolean isTranscriptLoadingForStudy() { return isLoading; }

    /** Read-only study hook: active spoken index, or -1. */
    public static int getActiveSpokenIndexForStudy() {
        Utils.verifyOnMainThread();
        boolean active = ttsEngine.isSpeaking() || (tts != null && tts.isSpeaking());
        return active ? lastSpokenIndex : -1;
    }

    /** Read-only copy of Morphe's predicted TTS completion timestamp. */
    public static long getTtsEndVideoTimeMsForStudy() {
        Utils.verifyOnMainThread();
        return ttsEndVideoTimeMs;
    }

'''
    rep(vot,
        "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        study_getters + "    /** Lazily creates the System TTS instance and wires its completion listener. Idempotent. */\n",
        "add read-only study getters")

    # ------------------------------------------------------------------
    # Caption fetch/merge diagnostics.
    # ------------------------------------------------------------------
    rep(fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "TranscriptFetcher study imports")

    rep(fetcher,
        '''    static List<TranscriptSegment> fetch(String videoId, Consumer<List<TranscriptSegment>> onUpdate,
                                         BooleanSupplier cancelled) {
        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);''',
        '''    static List<TranscriptSegment> fetch(String videoId, Consumer<List<TranscriptSegment>> onUpdate,
                                         BooleanSupplier cancelled) {
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                "caption fetch start video=" + videoId);
        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);
        SpanishStudyController.onSourceTranscriptFetched(segments);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                "caption fetch result video=" + videoId + " sourceLang=" + lastSourceLang
                        + " mergedSegments=" + segments.size());''',
        "publish/log stock source segments")

    rep(fetcher,
        '''        return mergeIntoSentences(lines);
    }''',
        '''        List<TranscriptSegment> merged = mergeIntoSentences(lines);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                "parseJson3 lang=" + sourceLang + " rawSpeechLines=" + lines.size()
                        + " mergedSentences=" + merged.size() + " punctuated=" + detectPunctuation(lines));
        if (SpanishStudyDiagnostics.includeText()) {
            for (int i = 0; i < lines.size(); i++) {
                TranscriptSegment s = lines.get(i);
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.CAPTIONS,
                        "raw[" + i + "] " + s.startMs + "-" + s.endMs
                                + " text=" + SpanishStudyDiagnostics.text(s.text));
            }
        }
        return merged;
    }''',
        "log raw-to-sentence merge")

    # ------------------------------------------------------------------
    # Stock TranscriptTranslator observability. No recovery/provider behavior changed.
    # ------------------------------------------------------------------
    rep(translator,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "Translator diagnostic import")

    rep(translator,
        '''    static void requestAbort() {
        abortTranslation = true;''',
        '''    static void requestAbort() {
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "requestAbort activeConnection=" + (activeConnection != null)
                        + " translatingBatch=" + translatingBatchIndex);
        abortTranslation = true;''',
        "log translation abort")

    rep(translator,
        '''        reprioritize = true;
        conn.disconnect();''',
        '''        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "seek cut targetBatch=" + target + " currentBatch=" + translatingBatchIndex
                        + " playhead=" + pendingSeekTimeMs);
        reprioritize = true;
        conn.disconnect();''',
        "log translation seek cut")

    rep(translator,
        '''        List<List<TranscriptSegment>> batches =
                new ArrayList<>(splitByCharBudget(segments, maxBatchChars));
        reportNextTranslationError = true;''',
        '''        List<List<TranscriptSegment>> batches =
                new ArrayList<>(splitByCharBudget(segments, maxBatchChars));
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "translate session video=" + videoId + " service=" + service
                        + " target=" + targetLang + " segments=" + segments.size()
                        + " maxBatchChars=" + maxBatchChars + " initialBatches=" + batches.size());
        reportNextTranslationError = true;''',
        "log translation session")

    rep(translator,
        '''                translatingBatchIndex = index;
                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,
                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));
                translatingBatchIndex = -1;''',
        '''                int diagChars = 0;
                for (TranscriptSegment diagSeg : batch) diagChars += diagSeg.text.length() + 1;
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                        "dispatch batch=" + index + " offset=" + offset + " size=" + batch.size()
                                + " chars=" + diagChars + " playhead=" + timeMs
                                + " totalBatches=" + batches.size());
                final long diagBatchStart = System.currentTimeMillis();
                translatingBatchIndex = index;
                final List<String> translated = translateBatchSafe(videoId, batch, targetLang,
                        streamCallback(onUpdate, mainHandler, working, batch, offset, targetLang));
                translatingBatchIndex = -1;
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                        "batch result=" + index + " expected=" + batch.size()
                                + " got=" + (translated == null ? -1 : translated.size())
                                + " latencyMs=" + (System.currentTimeMillis() - diagBatchStart)
                                + " reprioritize=" + reprioritize + " abort=" + abortTranslation);''',
        "log batch dispatch/result")

    rep(translator,
        '''                if (translated != null && translated.size() < batch.size()) {
                    List<TranscriptSegment> tail = new ArrayList<>(batch.subList(translated.size(), batch.size()));''',
        '''                if (translated != null && translated.size() < batch.size()) {
                    SpanishStudyDiagnostics.recordAlways(SpanishStudyDiagnostics.TRANSLATION,
                            "cardinality mismatch batch=" + index + " expected=" + batch.size()
                                    + " got=" + translated.size() + " requeue=" + (batch.size() - translated.size()));
                    List<TranscriptSegment> tail = new ArrayList<>(batch.subList(translated.size(), batch.size()));''',
        "log stock cardinality requeue")

    rep(translator,
        '''        } catch (Exception ex) {
            if (abortTranslation || reprioritize) {''',
        '''        } catch (Exception ex) {
            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.TRANSLATION,
                    "translateBatchSafe failure target=" + targetLang
                            + " batchSize=" + batch.size() + " abort=" + abortTranslation
                            + " reprioritize=" + reprioritize, ex);
            if (abortTranslation || reprioritize) {''',
        "log translation failures")

    rep(translator,
        '''        String model = Settings.VOT_OPENROUTER_MODEL.get();
        final long start = System.currentTimeMillis();''',
        '''        String model = Settings.VOT_OPENROUTER_MODEL.get();
        final long start = System.currentTimeMillis();
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "OpenRouter request start model=" + model + " video=" + videoId
                        + " target=" + targetLang + " segments=" + segments.size());''',
        "log OpenRouter start")

    rep(translator,
        '''        byte[] bodyBytes = body.toString().getBytes(StandardCharsets.UTF_8);

        HttpURLConnection conn = Requester.openConnection(''',
        '''        byte[] bodyBytes = body.toString().getBytes(StandardCharsets.UTF_8);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "OpenRouter request bodyBytes=" + bodyBytes.length + " maxTokens=" + (segments.size() * 30)
                        + " model=" + model);

        HttpURLConnection conn = Requester.openConnection(''',
        "log OpenRouter request size")

    rep(translator,
        '''            final int code = conn.getResponseCode();
            if (code != 200) {''',
        '''            final int code = conn.getResponseCode();
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                    "OpenRouter response http=" + code + " headersMs=" + (System.currentTimeMillis() - start));
            if (code != 200) {''',
        "log OpenRouter HTTP response")

    rep(translator,
        '''        final int matchedFirst = matched[0];
        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang''',
        '''        final int matchedFirst = matched[0];
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TRANSLATION,
                "OpenRouter stream complete expected=" + segmentSize + " matched=" + matchedFirst
                        + " rawChars=" + rawOutput.length()
                        + " totalLatencyMs=" + (System.currentTimeMillis() - start));
        Logger.printDebug(() -> "OpenRouter translation complete: " + targetLang''',
        "log OpenRouter stream completion")

    # ------------------------------------------------------------------
    # TTS engine/cache/prefetch telemetry. Read-only observations around stock calls.
    # ------------------------------------------------------------------
    rep(engine,
        "import app.morphe.extension.youtube.patches.VideoInformation;\n",
        "import app.morphe.extension.youtube.patches.VideoInformation;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "TtsEngine diagnostic import")

    rep(engine,
        '''    byte[] prefetch(String text, String voice, String lang) throws Exception {
        return synthesizeEdge(text, voice, lang);
    }''',
        '''    byte[] prefetch(String text, String voice, String lang) throws Exception {
        final long diagStart = System.currentTimeMillis();
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "Edge synth start voice=" + voice + " lang=" + lang + " chars=" + text.length()
                        + " text=" + SpanishStudyDiagnostics.text(text));
        byte[] result = synthesizeEdge(text, voice, lang);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "Edge synth done voice=" + voice + " bytes=" + result.length
                        + " durationMs=" + mp3DurationMs(result.length)
                        + " latencyMs=" + (System.currentTimeMillis() - diagStart));
        return result;
    }''',
        "log Edge synthesis")

    rep(engine,
        '''    void play(byte[] mp3, float volume, float rate, long startTimeMs, long id, @Nullable Runnable onDone) {
        Utils.verifyOnMainThread();''',
        '''    void play(byte[] mp3, float volume, float rate, long startTimeMs, long id, @Nullable Runnable onDone) {
        Utils.verifyOnMainThread();
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "play request id=" + id + " bytes=" + (mp3 == null ? 0 : mp3.length)
                        + " volume=" + volume + " rate=" + rate + " seekMs=" + startTimeMs);''',
        "log TTS play request")

    rep(engine,
        '''                if (startTimeMs > 0) {
                    mp.seekTo((int) startTimeMs);
                }
                mp.start();''',
        '''                if (startTimeMs > 0) {
                    mp.seekTo((int) startTimeMs);
                }
                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                        "MediaPlayer actual start id=" + id + " bytes=" + mp3.length
                                + " rate=" + rate + " seekMs=" + startTimeMs);
                mp.start();''',
        "log actual Edge audio start")

    rep(prefetch,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "TtsPrefetcher diagnostic import")

    rep(prefetch,
        '''    static void updateVideo(String videoId, List<TranscriptSegment> segments) {
        synchronized (lock) {''',
        '''    static void updateVideo(String videoId, List<TranscriptSegment> segments) {
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "prefetch updateVideo id=" + videoId + " segments=" + (segments == null ? -1 : segments.size()));
        synchronized (lock) {''',
        "log prefetch video update")

    rep(prefetch,
        '''    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {
        try {
            final long start = System.currentTimeMillis();''',
        '''    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {
        try {
            final long start = System.currentTimeMillis();
            SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                    "prefetch start index=" + index + "/" + totalSegments + " voice=" + voice
                            + " distanceMs=" + (seg.startMs - currentVideoTimeMs));''',
        "log prefetch start")

    rep(prefetch,
        '''                Logger.printDebug(() -> "prefetched TTS: " + videoId
                        + " segment: " + index + "/" + totalSegments + " fetchTime: "''',
        '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                        "prefetch success index=" + index + " bytes=" + data.length
                                + " durationMs=" + seg.durationMs
                                + " fetchMs=" + (System.currentTimeMillis() - start)
                                + " playback=" + seg.playbackStartMs + "-" + seg.playbackEndMs);
                Logger.printDebug(() -> "prefetched TTS: " + videoId
                        + " segment: " + index + "/" + totalSegments + " fetchTime: "''',
        "log prefetch success")

    rep(prefetch,
        '''        } catch (Exception ex) {
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
        '''        } catch (Exception ex) {
            SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.TTS,
                    "prefetch failed index=" + index + " voice=" + voice, ex);
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
        "log prefetch error")

    rep(cache,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\n"
        "import app.spanishstudy.vot.SpanishStudyDiagnostics;\n",
        "TtsCache diagnostic import")

    rep(cache,
        '''    static synchronized byte[] get(String videoId, int segmentIndex, String voice, String lang, String text) {
        if (TTS_ENGINE_SYSTEM.equals(voice)) return null;
        return cache.get(key(videoId, segmentIndex, voice, lang, text));
    }''',
        '''    static synchronized byte[] get(String videoId, int segmentIndex, String voice, String lang, String text) {
        if (TTS_ENGINE_SYSTEM.equals(voice)) return null;
        byte[] data = cache.get(key(videoId, segmentIndex, voice, lang, text));
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "cache get index=" + segmentIndex + " hit=" + (data != null)
                        + " bytes=" + (data == null ? 0 : data.length));
        return data;
    }''',
        "log TTS cache reads")

    rep(cache,
        '''        if (TTS_ENGINE_SYSTEM.equals(voice)) return;
        cache.put(key(videoId, segmentIndex, voice, lang, text), data);''',
        '''        if (TTS_ENGINE_SYSTEM.equals(voice)) return;
        cache.put(key(videoId, segmentIndex, voice, lang, text), data);
        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.TTS,
                "cache put index=" + segmentIndex + " bytes=" + (data == null ? 0 : data.length));''',
        "log TTS cache writes")

    # ------------------------------------------------------------------
    # Local source-audio capture: reuse Morphe's existing AudioTrack wrapper reference.
    # ------------------------------------------------------------------
    rep(player_volume,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\n"
        "import app.spanishstudy.vot.LocalSpeakerDiarizer;\n",
        "PlayerVolume local diarizer import")

    rep(player_volume,
        '''        lastAudioTrackRef.set(track);
        applyMultiplier();''',
        '''        lastAudioTrackRef.set(track);
        try {
            LocalSpeakerDiarizer.onAudioTrack(track);
        } catch (Throwable ignored) {
            // Speaker diagnostics must never interfere with YouTube audio.
        }
        applyMultiplier();''',
        "observe YouTube AudioTrack for local diarization")

    # ------------------------------------------------------------------
    # UI integration and native-caption suppression (same behavior as v2.27).
    # ------------------------------------------------------------------
    rep(bottom_sheet,
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\n",
        "import app.morphe.extension.youtube.shared.PipDismissHelper;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "VOT bottom sheet study import")

    rep(bottom_sheet,
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();''',
        '''        translationRow.setOnClickListener(v -> showTranslationServicePicker(context, mainRef[0]));
        refreshTranslation.run();

        LinearLayout studyRow = makeValueRow(context, fg, "Spanish study");
        ((TextView) studyRow.getTag()).setText("Subtitles · local speakers · deep diagnostics");
        studyRow.setOnClickListener(v -> {
            if (mainRef[0] != null) mainRef[0].dismiss();
            SpanishStudyController.showTools(Utils.getActivity());
        });''',
        "create study settings row")

    rep(bottom_sheet,
        '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(makeDivider(context, fg));''',
        '''        content.addView(translationRow);
        content.addView(engineRow);
        content.addView(studyRow);
        content.addView(makeDivider(context, fg));''',
        "add study settings row")

    rep(auto,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\n"
        "import app.spanishstudy.vot.SpanishStudyController;\n",
        "AutoCaptions study import")

    rep(auto,
        '''    public static boolean disableAutoCaptions(boolean original) {
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        '''    public static boolean disableAutoCaptions(boolean original) {
        if (SpanishStudyController.suppressNativeCaptions()) return true;
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        "avoid duplicate native captions")

    print("v2.28 deep diagnostics + local diarization integration complete")


if __name__ == "__main__":
    main()
