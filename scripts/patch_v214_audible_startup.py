#!/usr/bin/env python3
"""v2.14.0: audible-startup microbatches, stale-video guards, and local TTS failover."""
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
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v214_audible_startup.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    tts = pkg / "TtsEngine.java"
    prefetcher = pkg / "TtsPrefetcher.java"
    controller = study / "SpanishStudyController.java"

    # ---- Startup translation must become audible before background coverage -----------------
    rep(translator,
'''import app.morphe.extension.youtube.settings.Settings;
''',
'''import app.morphe.extension.youtube.settings.Settings;
import app.spanishstudy.vot.StartupTranslationPlanner;
''',
        "import startup translation planner")

    rep(translator,
'''                // Cap the first OpenRouter batch to a small budget; other services run unchanged.
                if (isOpenRouter && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;''',
'''                // Audible-startup rule: every provider gets a deliberately small first request.
                // Google can otherwise spend several seconds translating 60-100 phrases before
                // the first current phrase is available to TTS.
                if (firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;''',
        "use small first translation batch for Google too")

    old_cap = '''        int chars = 0;
        int splitAt = 0;
        for (int i = 0; i < batchSize; i++) {
            chars += batch.get(i).text.length() + 1;
            splitAt = i + 1;
            if (chars >= OPENROUTER_FIRST_BATCH_CHARS) break;
        }
        if (splitAt >= batchSize) return; // Whole batch already within budget.'''
    new_cap = '''        ArrayList<String> texts = new ArrayList<>(batchSize);
        for (TranscriptSegment segment : batch) texts.add(segment.text);
        int splitAt = StartupTranslationPlanner.initialSegmentCount(texts);
        if (splitAt <= 0 || splitAt >= batchSize) return; // Whole batch already within budget.'''
    rep(translator, old_cap, new_cap,
        "drive initial translation split from shared tested planner")

    # ---- Prime both speech backends when a session is enabled after the video already opened --
    rep(vot,
'''import android.speech.tts.TextToSpeech;
''',
'''import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
''',
        "offline fallback Voice import")

    rep(vot,
'''import app.spanishstudy.vot.SpanishStudyDiagnostics;
''',
'''import app.spanishstudy.vot.SpanishStudyDiagnostics;
import app.spanishstudy.vot.CaptionNamedSpeakerStore;
import app.spanishstudy.vot.EdgeFallbackPolicy;
import app.spanishstudy.vot.StartupSpeechPolicy;
''',
        "v2.14 policy imports")

    rep(vot,
'''    private static final TtsEngine ttsEngine = TtsEngine.INSTANCE;
''',
'''    private static final TtsEngine ttsEngine = TtsEngine.INSTANCE;
    private static int edgeConsecutiveFailures;
    private static long edgeFallbackUntilMs;
''',
        "Edge fallback circuit state")

    helpers = r'''
    private static void warmEdgeConnectionAsync() {
        if (Settings.VOT_USE_NATIVE_TTS.get()) return;
        Utils.runOnBackgroundThread(() -> {
            try {
                ttsEngine.warmConnection();
                noteEdgeSynthesisSuccess();
            } catch (Exception ex) {
                Logger.printDebug(() -> "Edge warm-up failed: " + ex);
            }
        });
    }

    private static void primeSpeechBackends() {
        ensureTts(); // local/offline safety floor; initialization is asynchronous and cheap.
        warmEdgeConnectionAsync();
    }

    static synchronized void noteEdgeSynthesisSuccess() {
        edgeConsecutiveFailures = 0;
        edgeFallbackUntilMs = 0L;
    }

    static synchronized void noteEdgeSynthesisFailure(String source) {
        edgeConsecutiveFailures++;
        if (EdgeFallbackPolicy.shouldOpen(edgeConsecutiveFailures)) {
            edgeFallbackUntilMs = EdgeFallbackPolicy.fallbackUntil(System.currentTimeMillis());
            SpanishStudyDiagnostics.record("TTS-FALLBACK", "offline window opened 60s after "
                    + edgeConsecutiveFailures + " Edge failures source=" + source);
        }
    }

    static synchronized boolean isEdgeFallbackActive() {
        return EdgeFallbackPolicy.isOpen(System.currentTimeMillis(), edgeFallbackUntilMs);
    }

    private static boolean selectOfflineSystemVoice(String lang, int speakerIndex) {
        ensureTts();
        if (tts == null || !ttsReady) return false;
        Set<Voice> voices = tts.getVoices();
        if (voices == null || voices.isEmpty()) return false;
        Locale target = Locale.forLanguageTag(lang);
        ArrayList<Voice> local = new ArrayList<>();
        for (Voice candidate : voices) {
            if (candidate == null || candidate.isNetworkConnectionRequired()) continue;
            Locale locale = candidate.getLocale();
            if (locale != null && locale.getLanguage().equalsIgnoreCase(target.getLanguage())) {
                local.add(candidate);
            }
        }
        if (local.isEmpty()) return false;
        local.sort((a, b) -> a.getName().compareToIgnoreCase(b.getName()));
        int index = speakerIndex < 0 ? 0 : Math.floorMod(speakerIndex, local.size());
        return tts.setVoice(local.get(index)) == TextToSpeech.SUCCESS;
    }

    private static boolean speakOfflineFallback(TranscriptSegment seg,
                                                 int index,
                                                 String lang,
                                                 float volume,
                                                 float rate,
                                                 String reason) {
        Utils.verifyOnMainThread();
        int speaker = SpanishStudyController.speakerIndex(seg);
        if (!selectOfflineSystemVoice(lang, speaker)) {
            SpanishStudyDiagnostics.record("TTS-FALLBACK", "no offline Spanish system voice available");
            return false;
        }
        Bundle params = new Bundle();
        params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, volume);
        tts.setSpeechRate(rate * VideoInformation.getPlaybackSpeed());
        final long id = ttsEngine.markBusy();
        final int result = tts.speak(seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);
        if (result != TextToSpeech.SUCCESS) {
            ttsEngine.clearBusy(id);
            SpanishStudyDiagnostics.record("TTS-FALLBACK", "offline system TTS rejected index=" + index);
            return false;
        }
        long estimatedMs = Math.max(1L, seg.text.length() * TtsEngine.ESTIMATED_MS_PER_CHAR);
        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, estimatedMs, rate);
        SpanishStudyDiagnostics.record("TTS-FALLBACK", "playing offline index=" + index + " reason=" + reason);
        return true;
    }

'''
    rep(vot,
'''    /**
     * Injection point.
     */
    public static void newVideoLoaded(String videoId) {''',
        helpers + '''    /**
     * Injection point.
     */
    public static void newVideoLoaded(String videoId) {''',
        "add Edge circuit and local fallback helpers")

    # Replace the duplicated new-video warm-up block with the shared primer.
    rep(vot,
'''        // Open the Edge socket in parallel so the first synthesis doesn't pay handshake cost.
        if (!Settings.VOT_USE_NATIVE_TTS.get()) {
            Utils.runOnBackgroundThread(() -> {
                try {
                    ttsEngine.warmConnection();
                } catch (Exception ex) {
                    Logger.printDebug(() -> "Edge warm-up failed: " + ex);
                }
            });
        }''',
'''        // Prime Edge plus an offline Android fallback while captions/translation are loading.
        primeSpeechBackends();''',
        "prime speech backends on new active video")

    rep(vot,
'''        SpanishStudyController.onSessionEnabled();
        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
'''        SpanishStudyController.onSessionEnabled();
        // newVideoLoaded may have happened while this session was disabled; warm speech here too.
        primeSpeechBackends();
        if (!currentVideoId.isEmpty() && segments.isEmpty() && !isLoading) {''',
        "prime speech when session is enabled late")

    # ---- Hard invalidate every asynchronous Edge playback when stop/video change occurs --------
    rep(tts,
'''        stopped = true;
        speaking = false;
''',
'''        stopped = true;
        speaking = false;
        // Every stop is also a generation boundary. In-flight synthesis from the old video/session
        // must fail the playbackId check even if it completes after a new video loads.
        playbackId++;
''',
        "invalidate in-flight Edge playback on stop")

    # A translated phrase with almost no time left should not monopolize the serialized Edge socket.
    rep(vot,
'''        final long playbackId = ttsEngine.markBusy();
        final String videoIdSnapshot = currentVideoId;
        Utils.runOnBackgroundThread(() -> {''',
'''        final long nowBeforeNetworkMs = VideoInformation.getVideoTime();
        if (!StartupSpeechPolicy.shouldStartNetwork(seg.endMs, nowBeforeNetworkMs)) {
            lastSpokenIndex = Math.max(lastSpokenIndex, index);
            SpanishStudyDiagnostics.record("TTS", "network-skip index=" + index
                    + " remaining=" + Math.max(0L, seg.endMs - nowBeforeNetworkMs) + "ms");
            SpanishStudyController.onDubPlaybackSkipped(seg, index);
            triggerNextSegmentCheck();
            return;
        }
        if (isEdgeFallbackActive() && speakOfflineFallback(seg, index, lang, volume, rate,
                "Edge circuit open")) return;

        final long playbackId = ttsEngine.markBusy();
        final String videoIdSnapshot = currentVideoId;
        Utils.runOnBackgroundThread(() -> {''',
        "skip doomed network synthesis and use active offline circuit")

    rep(vot,
'''            } catch (Exception ex) {
                logError(() -> "On-demand synthesis failed for segment " + index, ex);
                Utils.runOnMainThread(() -> handleEdgeAttemptFailure(
                        seg, index, playbackId, ex.getClass().getSimpleName()));
                return;
            }
            if (data.length > 0) {
                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);
            }
            final byte[] finalData = data;
            Utils.runOnMainThread(() -> {
                if (playbackId != ttsEngine.getPlaybackId()) return;
                if (finalData.length > 0) {
                    startPreparedEdgePlayback(seg, index, voice, lang, volume, finalData, playbackId,
                            explicitSeekForThisPlayback);
                } else {
                    handleEdgeAttemptFailure(seg, index, playbackId, "empty Edge TTS audio");
                }
            });''',
'''            } catch (Exception ex) {
                logError(() -> "On-demand synthesis failed for segment " + index, ex);
                Utils.runOnMainThread(() -> {
                    if (!videoIdSnapshot.equals(currentVideoId)) {
                        SpanishStudyDiagnostics.record("TTS", "stale-video failure discarded index=" + index);
                        return;
                    }
                    noteEdgeSynthesisFailure("on-demand");
                    if (!speakOfflineFallback(seg, index, lang, volume, rate, "Edge synthesis failed")) {
                        handleEdgeAttemptFailure(seg, index, playbackId, ex.getClass().getSimpleName());
                    }
                });
                return;
            }
            if (data.length > 0) {
                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);
            }
            final byte[] finalData = data;
            Utils.runOnMainThread(() -> {
                if (!videoIdSnapshot.equals(currentVideoId)) {
                    SpanishStudyDiagnostics.record("TTS", "stale-video audio discarded index=" + index);
                    return;
                }
                if (playbackId != ttsEngine.getPlaybackId()) return;
                if (finalData.length > 0) {
                    noteEdgeSynthesisSuccess();
                    startPreparedEdgePlayback(seg, index, voice, lang, volume, finalData, playbackId,
                            explicitSeekForThisPlayback);
                } else {
                    noteEdgeSynthesisFailure("empty-on-demand");
                    if (!speakOfflineFallback(seg, index, lang, volume, rate, "empty Edge audio")) {
                        handleEdgeAttemptFailure(seg, index, playbackId, "empty Edge TTS audio");
                    }
                }
            });''',
        "guard async Edge results by video and fail over locally")

    # ---- Prefetch must not mutate the new video's timing with an old video's finished request ---
    rep(prefetcher,
'''    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {''',
'''    private static boolean isCurrentVideo(String videoId) {
        synchronized (lock) { return videoId.equals(currentVideoId); }
    }

    private static boolean fetch(String videoId, TranscriptSegment seg, int index,
                                 int totalSegments, String voice, String lang) {''',
        "add prefetch video-generation guard")

    rep(prefetcher,
'''            if (data.length > 0) {
                TtsCache.put(videoId, index, voice, lang, seg.text, data);''',
'''            if (data.length > 0) {
                if (!isCurrentVideo(videoId)) {
                    SpanishStudyDiagnostics.record("TTS-PREFETCH", "stale-video audio discarded index=" + index);
                    return true;
                }
                VoiceOverTranslationPatch.noteEdgeSynthesisSuccess();
                TtsCache.put(videoId, index, voice, lang, seg.text, data);''',
        "discard stale prefetch completion before timing mutation")

    rep(prefetcher,
'''            markPrefetchFailure(index);
            return false;
        } catch (Exception ex) {
            markPrefetchFailure(index);
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
'''            markPrefetchFailure(index);
            VoiceOverTranslationPatch.noteEdgeSynthesisFailure("prefetch-empty");
            return false;
        } catch (Exception ex) {
            markPrefetchFailure(index);
            VoiceOverTranslationPatch.noteEdgeSynthesisFailure("prefetch-error");
            VoiceOverTranslationPatch.logError(() -> "Prefetch failed for segment " + index, ex);''',
        "feed prefetch failures into shared Edge circuit")

    # Avoid repeatedly hammering Edge during the short fallback window.
    rep(prefetcher,
'''            String voiceLang = VoiceOverTranslationPatch.resolveTargetLang();
            String voice = VoiceCatalog.resolve(voiceLang, Settings.VOT_TTS_VOICE_TYPE.get());''',
'''            String voiceLang = VoiceOverTranslationPatch.resolveTargetLang();
            if (VoiceOverTranslationPatch.isEdgeFallbackActive()) {
                if (waitOnLock(1_000L)) return;
                continue;
            }
            String voice = VoiceCatalog.resolve(voiceLang, Settings.VOT_TTS_VOICE_TYPE.get());''',
        "pause Edge prefetch while offline fallback circuit is open")

    # ---- Caption-provided names are safe identities; bare markers remain boundary-only --------
    rep(controller,
'''    public static int speakerIndex(TranscriptSegment segment){
        return SpeakerAssignmentStore.speakerIndex(segment);
    }''',
'''    public static int speakerIndex(TranscriptSegment segment){
        if (segment == null) return -1;
        int named = CaptionNamedSpeakerStore.speakerIndexAt(segment.startMs);
        return named >= 0 ? named : SpeakerAssignmentStore.speakerIndex(segment);
    }''',
        "use explicit caption names before acoustic speaker store")

    # ---- Diagnostics --------------------------------------------------------------------------
    rep(controller,
'''        report.append("Spanish Dub Study v2.13.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.14.0 diagnostics\\n");''',
        "label v2.14 diagnostics")

    rep(controller,
'''        report.append("captionSpeakerTurns=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("speakerBoundaryMode=caption-markers-hard-boundary\\n");
        report.append("speakerIdentityMode=pending-local-audio-clustering\\n");''',
'''        report.append("captionSpeakerMarkers=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("captionNamedSpeakers=").append(CaptionNamedSpeakerStore.namedSpeakerCount()).append('\\n');
        report.append("speakerBoundaryMode=caption-markers-provisional-hard-boundary\\n");
        report.append("speakerIdentityMode=caption-names-then-local-audio-clustering\\n");
        report.append("startupTranslationBatch=").append(StartupTranslationPlanner.MAX_INITIAL_SEGMENTS)
                .append(" segments/").append(StartupTranslationPlanner.MAX_INITIAL_CHARS).append(" chars\\n");''',
        "clarify provisional markers and startup microbatch diagnostics")

    print("v2.14.0 audible-startup/local-failover integration complete")


if __name__ == "__main__":
    main()
