#!/usr/bin/env python3
"""v2.14.0: Edge/native fail-forward, bounded Edge failures, conservative marker confidence, faster Google startup."""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count} in {path}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def rep_n(path: Path, old: str, new: str, expected: int, label: str):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != expected:
        raise RuntimeError(f"{label}: expected {expected} anchors, found {count} in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")
    print("patched:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v214_tts_failover_marker_confidence.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    votpkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = votpkg / "VoiceOverTranslationPatch.java"
    prefetcher = votpkg / "TtsPrefetcher.java"
    translator = votpkg / "TranscriptTranslator.java"
    fetcher = votpkg / "TranscriptFetcher.java"
    controller = study / "SpanishStudyController.java"

    # ---- Native Android TTS is the reliability floor underneath Edge -------------------------
    rep(vot,
'''import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
'''import app.spanishstudy.vot.EdgeReliabilityPolicy;
import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        "import Edge reliability policy")

    # Warm native TTS whether the session was already persisted on or was just enabled. Its async
    # initialization then overlaps caption fetch/Google translation instead of delaying fallback.
    rep(vot,
'''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) return;
        TtsPrefetcher.updateVideo(videoId, segments);''',
'''        if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;
        if (PlayerType.getCurrent() == PlayerType.INLINE_MINIMAL) return;
        ensureTts(); // warm the local/native reliability floor in parallel with transcript work
        TtsPrefetcher.updateVideo(videoId, segments);''',
        "warm native TTS for persisted active sessions")

    rep(vot,
'''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        SpanishStudyController.onSessionEnabled();''',
'''        sessionEnabled = true;
        Settings.VOT_SESSION_ENABLED.save(true);
        SpanishStudyController.onSessionEnabled();
        ensureTts(); // do not wait for the first Edge miss to initialize Android TTS''',
        "warm native TTS when session is enabled")

    native_helper = r'''
    /**
     * Fail one active phrase forward to an installed OFFLINE Android Spanish voice. Edge remains
     * preferred whenever its MP3 was prepared in advance; this path exists so a cold/broken Edge
     * socket cannot make an otherwise translated video completely silent.
     */
    private static boolean speakNativeReliabilityFallback(TranscriptSegment seg,
                                                           int index,
                                                           float volume,
                                                           String reason) {
        Utils.verifyOnMainThread();
        ensureTts();
        if (!ttsReady || tts == null) return false;

        final long nowVideoMs = VideoInformation.getVideoTime();
        if (nowVideoMs < seg.startMs || nowVideoMs >= seg.endMs) return false;

        final Locale targetLocale = Locale.forLanguageTag(resolveTargetLang());
        android.speech.tts.Voice best = null;
        try {
            java.util.Set<android.speech.tts.Voice> voices = tts.getVoices();
            if (voices != null) {
                for (android.speech.tts.Voice candidate : voices) {
                    if (candidate == null || candidate.isNetworkConnectionRequired()) continue;
                    Locale locale = candidate.getLocale();
                    if (locale == null || !targetLocale.getLanguage().equals(locale.getLanguage())) continue;
                    if (best == null) best = candidate;
                    if (!targetLocale.getCountry().isEmpty()
                            && targetLocale.getCountry().equalsIgnoreCase(locale.getCountry())) {
                        best = candidate;
                        break;
                    }
                }
            }
        } catch (Exception ex) {
            SpanishStudyDiagnostics.record("TTS", "native-fallback voice enumeration failed "
                    + ex.getClass().getSimpleName());
        }
        if (best == null) {
            SpanishStudyDiagnostics.record("TTS", "native-fallback unavailable index=" + index
                    + " reason=no-offline-spanish-voice");
            return false;
        }

        try {
            if (tts.setVoice(best) != TextToSpeech.SUCCESS) return false;
        } catch (Exception ex) {
            return false;
        }

        final long availableMs = Math.max(1L, seg.endMs - nowVideoMs);
        final long estimatedSpeechMs = Math.max(1L,
                (long) seg.text.length() * TtsEngine.ESTIMATED_MS_PER_CHAR);
        final float rate = calculateSpeechRate(estimatedSpeechMs, availableMs);
        final float videoSpeed = VideoInformation.getPlaybackSpeed();

        PlayerVolumePatch.setDuckMultiplier(Settings.VOT_ORIGINAL_AUDIO_VOLUME.get() / 100.0f);
        tts.setSpeechRate(rate * videoSpeed);
        Bundle params = new Bundle();
        params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, volume);
        final long id = ttsEngine.markBusy();
        final int result = tts.speak(seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);
        if (result != TextToSpeech.SUCCESS) {
            ttsEngine.clearBusy(id);
            SpanishStudyDiagnostics.record("TTS", "native-fallback rejected index=" + index);
            return false;
        }

        lastSpokenIndex = index;
        ttsEndVideoTimeMs = nowVideoMs + (long) (estimatedSpeechMs / Math.max(0.1f, rate));
        currentTtsBaseRate = rate;
        lastAppliedPlaybackSpeed = videoSpeed;
        SpanishStudyController.onDubPlaybackStarted(seg, index, estimatedSpeechMs, rate);
        SpanishStudyDiagnostics.record("TTS", "native-fallback index=" + index
                + " reason=" + reason + " voice=" + best.getName() + " rate=" + rate);
        return true;
    }

'''
    rep(vot,
'''    private static void speak(TranscriptSegment seg, int index) {''',
        native_helper + '''    private static void speak(TranscriptSegment seg, int index) {''',
        "add offline native phrase fallback helper")

    # If an active phrase has no prefetched Edge MP3, do not start a fresh network synthesis on its
    # deadline. Use native immediately when ready; Edge background prefetch continues for later slots.
    rep(vot,
'''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);
        if (cached != null) {
            final long playbackId = ttsEngine.markBusy();
            startPreparedEdgePlayback(seg, index, voice, lang, volume, cached, playbackId,
                    explicitSeekForThisPlayback);
            return;
        }

        // Synthesize at natural speed so the result can be cached and reused at any rate;''',
'''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);
        if (cached != null) {
            final long playbackId = ttsEngine.markBusy();
            startPreparedEdgePlayback(seg, index, voice, lang, volume, cached, playbackId,
                    explicitSeekForThisPlayback);
            return;
        }

        final long activeNowMs = VideoInformation.getVideoTime();
        if (EdgeReliabilityPolicy.useNativeForActiveCacheMiss(
                false, ttsReady, activeNowMs, seg.startMs, seg.endMs)
                && speakNativeReliabilityFallback(seg, index, volume, "edge-cache-miss")) {
            return;
        }

        // Synthesize at natural speed so the result can be cached and reused at any rate;''',
        "fail active uncached Edge phrase forward to native TTS")

    # If an Edge attempt was already in flight and fails while the phrase remains active, fail forward
    # on the first failure instead of burning the entire source slot on repeated network retries.
    rep(vot,
'''        ttsEngine.clearBusy(playbackId);
        final int failures = SpanishStudyController.onDubPlaybackFailed(seg, index);''',
'''        ttsEngine.clearBusy(playbackId);
        if (speakNativeReliabilityFallback(seg, index,
                Settings.VOT_TRANSLATION_VOLUME.get() / 100.0f,
                "edge-failure-" + reason)) {
            return;
        }
        final int failures = SpanishStudyController.onDubPlaybackFailed(seg, index);''',
        "fail active Edge synthesis failure forward to native TTS")

    # ---- Stop retrying poisoned Edge prefetch slots forever ----------------------------------
    rep(prefetcher,
'''import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
'''import app.spanishstudy.vot.EdgeReliabilityPolicy;
import app.spanishstudy.vot.SpanishStudyController;
import app.spanishstudy.vot.SpanishStudyDiagnostics;''',
        "import prefetch suppression policy")

    rep(prefetcher,
'''    private static final Map<Integer, Long> failedUntilByIndex = new HashMap<>();''',
'''    private static final Map<Integer, Long> failedUntilByIndex = new HashMap<>();
    @GuardedBy("lock")
    private static final Map<Integer, Integer> failedAttemptsByIndex = new HashMap<>();''',
        "track repeated Edge prefetch failures per slot")

    rep_n(prefetcher,
'''                failedUntilByIndex.clear();''',
'''                failedUntilByIndex.clear();
                failedAttemptsByIndex.clear();''',
        1, "clear failure counters on video change")

    # clear() has different indentation than the videoChanged block.
    rep(prefetcher,
'''            failedUntilByIndex.clear();
            lock.notifyAll();''',
'''            failedUntilByIndex.clear();
            failedAttemptsByIndex.clear();
            lock.notifyAll();''',
        "clear failure counters on explicit reset")

    rep(prefetcher,
'''    private static boolean isPrefetchCoolingDown(int index) {
        synchronized (lock) {
            Long until = failedUntilByIndex.get(index);
            if (until == null) return false;
            if (until <= System.currentTimeMillis()) {
                failedUntilByIndex.remove(index);
                return false;
            }
            return true;
        }
    }

    private static void markPrefetchFailure(int index) {
        synchronized (lock) {
            failedUntilByIndex.put(index, System.currentTimeMillis() + FAILED_SEGMENT_COOLDOWN_MS);
        }
        SpanishStudyDiagnostics.record("TTS-PREFETCH", "cooldown index=" + index + " 25s");
    }

    private static void clearPrefetchFailure(int index) {
        synchronized (lock) { failedUntilByIndex.remove(index); }
    }''',
'''    private static boolean isPrefetchSuppressed(int index) {
        synchronized (lock) {
            Integer failures = failedAttemptsByIndex.get(index);
            return failures != null && EdgeReliabilityPolicy.suppressEdgePrefetch(failures);
        }
    }

    private static boolean isPrefetchCoolingDown(int index) {
        synchronized (lock) {
            Integer failures = failedAttemptsByIndex.get(index);
            if (failures != null && EdgeReliabilityPolicy.suppressEdgePrefetch(failures)) return true;
            Long until = failedUntilByIndex.get(index);
            if (until == null) return false;
            if (until <= System.currentTimeMillis()) {
                failedUntilByIndex.remove(index);
                return false;
            }
            return true;
        }
    }

    private static void markPrefetchFailure(int index) {
        final int failures;
        final boolean suppressed;
        synchronized (lock) {
            failures = failedAttemptsByIndex.getOrDefault(index, 0) + 1;
            failedAttemptsByIndex.put(index, failures);
            suppressed = EdgeReliabilityPolicy.suppressEdgePrefetch(failures);
            if (suppressed) failedUntilByIndex.remove(index);
            else failedUntilByIndex.put(index, System.currentTimeMillis() + FAILED_SEGMENT_COOLDOWN_MS);
        }
        SpanishStudyDiagnostics.record("TTS-PREFETCH", suppressed
                ? "suppressed index=" + index + " failures=" + failures
                : "cooldown index=" + index + " 25s failures=" + failures);
    }

    private static void clearPrefetchFailure(int index) {
        synchronized (lock) {
            failedUntilByIndex.remove(index);
            failedAttemptsByIndex.remove(index);
        }
    }''',
        "bound repeated Edge prefetch failures")

    rep(prefetcher,
'''                    if (success) {
                        currentBackoffMs = Math.max(0, currentBackoffMs - 500);
                    } else {
                        if (currentBackoffMs == 0) currentBackoffMs = BACKOFF_MIN_MS;
                        else currentBackoffMs = (int) Math.min(BACKOFF_MAX_MS, currentBackoffMs * BACKOFF_FACTOR);
                    }''',
'''                    if (success) {
                        currentBackoffMs = Math.max(0, currentBackoffMs - 500);
                    } else if (isPrefetchSuppressed(next.index)) {
                        // One poisoned phrase must not slow every later phrase after it is exhausted.
                        currentBackoffMs = 0;
                    } else {
                        if (currentBackoffMs == 0) currentBackoffMs = BACKOFF_MIN_MS;
                        else currentBackoffMs = (int) Math.min(BACKOFF_MAX_MS, currentBackoffMs * BACKOFF_FACTOR);
                    }''',
        "do not propagate exhausted-slot backoff to later phrases")

    # ---- Faster Google time-to-first-translation ---------------------------------------------
    rep(translator,
'''    private static final int GOOGLE_MAX_BATCH_CHARS = TextTranslator.MAXIMUM_BATCH_CHARACTERS;
    // Smaller batches for OpenRouter so the first batch completes faster and TTS starts sooner.''',
'''    private static final int GOOGLE_MAX_BATCH_CHARS = TextTranslator.MAXIMUM_BATCH_CHARACTERS;
    // The first Google request is intentionally smaller so subtitles/native fallback become usable
    // quickly; later batches retain the normal large character budget for throughput.
    private static final int GOOGLE_FIRST_BATCH_CHARS = 900;
    // Smaller batches for OpenRouter so the first batch completes faster and TTS starts sooner.''',
        "add small first Google translation budget")

    rep(translator,
'''                // Cap the first OpenRouter batch to a small budget; other services run unchanged.
                if (isOpenRouter && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }
                firstBatchAfterReposition = false;''',
'''                // First audible slice is deliberately small for Google as well as OpenRouter.
                if (firstBatchAfterReposition && !isMyMemory) {
                    capFirstBatch(batches, batchDone, index,
                            isOpenRouter ? OPENROUTER_FIRST_BATCH_CHARS : GOOGLE_FIRST_BATCH_CHARS);
                }
                firstBatchAfterReposition = false;''',
        "cap first Google batch near playhead")

    rep(translator,
'''    private static void capFirstBatch(List<List<TranscriptSegment>> batches,
                                      List<Boolean> batchDone, int index) {''',
'''    private static void capFirstBatch(List<List<TranscriptSegment>> batches,
                                      List<Boolean> batchDone, int index, int firstBatchChars) {''',
        "parameterize first-batch character cap")

    rep(translator,
'''            if (chars >= OPENROUTER_FIRST_BATCH_CHARS) break;''',
'''            if (chars >= firstBatchChars) break;''',
        "use provider-specific first-batch cap")

    # ---- Diagnostics reflect marker confidence + fail-forward policy -------------------------
    rep(fetcher,
'''                + planned.size() + " floor=" + SpeechUnitPlanner.MIN_UNIT_MS + "ms"
                + " speakerTurns=" + CaptionSpeakerTurnStore.count());''',
'''                + planned.size() + " floor=" + SpeechUnitPlanner.MIN_UNIT_MS + "ms"
                + " cueMarkers=" + CaptionSpeakerTurnStore.markerCount()
                + " speakerTurns=" + CaptionSpeakerTurnStore.count());''',
        "separate raw cue markers from high-confidence speaker turns")

    rep(controller,
'''        report.append("Spanish Dub Study v2.13.0 diagnostics\\n");''',
'''        report.append("Spanish Dub Study v2.14.0 diagnostics\\n");''',
        "label v2.14 diagnostics")

    rep(controller,
'''        report.append("captionSpeakerTurns=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("speakerBoundaryMode=caption-markers-hard-boundary\\n");''',
'''        report.append("captionCueMarkers=").append(CaptionSpeakerTurnStore.markerCount()).append('\\n');
        report.append("captionSpeakerTurns=").append(CaptionSpeakerTurnStore.count()).append('\\n');
        report.append("speakerBoundaryMode=explicit-labelled-caption-turns-only\\n");''',
        "diagnose conservative speaker-marker confidence")

    rep(controller,
'''        report.append("analysisMode=local-lightweight-only\\n");''',
'''        report.append("analysisMode=local-lightweight-only\\n");
        report.append("ttsFailover=edge-prefetched-native-offline-active-miss\\n");
        report.append("edgePrefetchFailureLimit=").append(EdgeReliabilityPolicy.PREFETCH_FAILURES_BEFORE_SUPPRESS).append('\\n');''',
        "diagnose TTS reliability policy")

    # Controller now references EdgeReliabilityPolicy in diagnostics.
    rep(controller,
'''import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;''',
'''import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;
import app.spanishstudy.vot.EdgeReliabilityPolicy;''',
        "import reliability policy into diagnostics controller")

    print("v2.14.0 TTS fail-forward/marker-confidence integration complete")


if __name__ == "__main__":
    main()
