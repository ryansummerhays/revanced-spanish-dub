#!/usr/bin/env python3
"""Make translated subtitle/TTS slots atomic and make Edge playback fit measured audio, not estimates.

Applied late in the patch chain after immutable timing and source-expression patches. The goals are:
- never rewrite an already accepted Spanish slot while it is being shown/spoken;
- never mark a slot spoken before audio actually starts;
- retry transient synthesis failures instead of silently losing Spanish;
- once Edge audio exists, measure its real MP3 duration and fit that exact duration to the current
  remaining source slot (late synthesis can no longer create cumulative drift);
- keep a healthier adaptive TTS lookahead on long videos.
"""
from __future__ import annotations

import sys
from pathlib import Path


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly 1 anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"patched: {label}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_atomic_dub_events.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    prefetcher = pkg / "TtsPrefetcher.java"
    for path in (vot, prefetcher):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    # Progressive publication may replace source placeholders, but the first accepted target-language
    # text for a slot becomes immutable. Crucially, do not stop an already speaking event just because
    # a background list publication arrived.
    replace_once(
        vot,
        '''                                // If the segment we last started speaking had its text replaced\n                                // by a freshly-arrived translation, stop and let videoTimeChanged\n                                // re-speak it with the translated text on the next tick.\n                                if (lastSpokenIndex >= 0\n                                        && lastSpokenIndex < segments.size()\n                                        && lastSpokenIndex < updated.size() && !segments.get(lastSpokenIndex).text\n                                        .equals(updated.get(lastSpokenIndex).text)) {\n                                    stopTts();\n                                }\n                                segments = updated;\n                                SpanishStudyController.onTranscriptUpdated(updated);''',
        '''                                // Atomic dub events: source placeholders may become Spanish,\n                                // but an accepted Spanish slot is frozen and cannot be rewritten\n                                // underneath subtitles/TTS by a later progressive publication.\n                                segments = SpanishStudyController.mergeTranslationUpdate(\n                                        segments, updated, resolveTargetLang());\n                                SpanishStudyController.onTranscriptUpdated(segments);''',
        "freeze accepted translated slots across progressive updates",
    )

    # A synthesis request is only an attempt, not proof that speech began. Mark lastSpokenIndex later,
    # immediately before successful playback starts.
    replace_once(
        vot,
        '''                        if (!ttsEngine.isSpeaking() || wasExplicitSeek) {\n                            lastSpokenIndex = i;\n                            Logger.printDebug(() -> "Found segment: " + lastSpokenIndex\n                                    + " videoTime: " + timeMs);\n                            speak(seg, i);\n                        }''',
        '''                        if (!ttsEngine.isSpeaking() || wasExplicitSeek) {\n                            final int candidateIndex = i;\n                            Logger.printDebug(() -> "Preparing segment: " + candidateIndex\n                                    + " videoTime: " + timeMs + " "\n                                    + SpanishStudyController.dubDiagnostic(seg));\n                            speak(seg, i);\n                        }''',
        "do not mark segment spoken before playback starts",
    )

    # Keep whether the current attempt follows an explicit seek available to the measured-audio path.
    replace_once(
        vot,
        '''        // Calculate if we should seek into the audio (e.g. after a short seek within segment).\n        long startTimeMs = 0;\n        if (wasExplicitSeek) {''',
        '''        // Calculate if we should seek into the audio (e.g. after a short seek within segment).\n        final boolean explicitSeekForThisPlayback = wasExplicitSeek;\n        long startTimeMs = 0;\n        if (wasExplicitSeek) {''',
        "remember explicit-seek intent through asynchronous synthesis",
    )

    helpers = r'''
    private static final int MAX_TTS_RETRIES = 2;
    private static final long TTS_RETRY_BASE_DELAY_MS = 220L;

    /**
     * Start a prepared Edge MP3 using its measured duration and the video position at the instant
     * playback actually begins. This removes the old failure mode where a character-count estimate
     * chose a rate before synthesis, then a differently-sized real MP3 drifted past the source slot.
     */
    private static void startPreparedEdgePlayback(TranscriptSegment seg,
                                                  int index,
                                                  String voice,
                                                  String lang,
                                                  float volume,
                                                  byte[] data,
                                                  long playbackId,
                                                  boolean explicitSeek) {
        Utils.verifyOnMainThread();
        if (data == null || data.length == 0 || playbackId != ttsEngine.getPlaybackId()) return;

        final long actualDurationMs = Math.max(1L, TtsEngine.mp3DurationMs(data.length));
        SpanishStudyController.onDubAudioReady(seg, index, actualDurationMs);

        final long nowVideoMs = VideoInformation.getVideoTime();
        final long availableMs = seg.endMs - nowVideoMs;
        if (availableMs <= 45L) {
            ttsEngine.clearBusy(playbackId);
            lastSpokenIndex = Math.max(lastSpokenIndex, index);
            SpanishStudyController.onDubPlaybackSkipped(seg, index);
            triggerNextSegmentCheck();
            return;
        }

        long startTimeMs = 0L;
        final long sourceSpanMs = Math.max(1L, seg.endMs - seg.startMs);
        final long timeIntoSourceMs = Math.max(0L, nowVideoMs - seg.startMs);

        if (explicitSeek && timeIntoSourceMs > SEEK_INTO_THRESHOLD_MS) {
            double sourceProgress = Math.max(0.0, Math.min(1.0,
                    timeIntoSourceMs / (double) sourceSpanMs));
            startTimeMs = Math.min(actualDurationMs - 1L,
                    Math.round(sourceProgress * actualDurationMs));
        }

        // Normal network/synthesis lateness should not throw away words if speeding up can still fit
        // the complete phrase. Only when even max speech rate cannot fit do we trim the minimum audio
        // needed from the beginning so this one event cannot push every later event behind.
        final float maxRate = Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f;
        final long playableAudioAtMax = Math.max(1L, (long) (availableMs * maxRate));
        final long remainingBeforeTrim = Math.max(1L, actualDurationMs - startTimeMs);
        if (remainingBeforeTrim > playableAudioAtMax) {
            long requiredTrim = remainingBeforeTrim - playableAudioAtMax;
            startTimeMs = Math.min(actualDurationMs - 1L, startTimeMs + requiredTrim);
        }

        final long remainingSpeechMs = Math.max(1L, actualDurationMs - startTimeMs);
        final float rate = calculateSpeechRate(remainingSpeechMs, availableMs);
        final float playbackRate = rate * VideoInformation.getPlaybackSpeed();

        ttsEndVideoTimeMs = nowVideoMs + (long) (remainingSpeechMs / Math.max(0.1f, rate));
        currentTtsBaseRate = rate;
        lastAppliedPlaybackSpeed = VideoInformation.getPlaybackSpeed();
        lastSpokenIndex = index;
        SpanishStudyController.onDubPlaybackStarted(seg, index, actualDurationMs, rate);
        Logger.printDebug(() -> "Starting measured dub event: "
                + SpanishStudyController.dubDiagnostic(seg));

        final long seekMs = startTimeMs;
        ttsEngine.play(data, volume, playbackRate, seekMs, playbackId, () -> {
            SpanishStudyController.onDubPlaybackDone(seg, index);
            triggerNextSegmentCheck();
        });
    }

    private static void handleEdgeAttemptFailure(TranscriptSegment seg,
                                                 int index,
                                                 long playbackId,
                                                 String reason) {
        Utils.verifyOnMainThread();
        ttsEngine.clearBusy(playbackId);
        final int failures = SpanishStudyController.onDubPlaybackFailed(seg, index);
        Logger.printDebug(() -> "Dub event synthesis/playback attempt failed: index=" + index
                + " attempt=" + failures + " reason=" + reason);
        if (failures > MAX_TTS_RETRIES) {
            // Fail forward rather than permanently wedging the playback engine on one bad network
            // request. We never speak source English through the Spanish voice.
            lastSpokenIndex = Math.max(lastSpokenIndex, index);
            SpanishStudyController.onDubPlaybackSkipped(seg, index);
            triggerNextSegmentCheck();
            return;
        }
        Utils.runOnMainThreadDelayed(VoiceOverTranslationPatch::triggerNextSegmentCheck,
                TTS_RETRY_BASE_DELAY_MS * failures);
    }

'''
    replace_once(
        vot,
        "    private static void speak(TranscriptSegment seg, int index) {\n",
        helpers + "    private static void speak(TranscriptSegment seg, int index) {\n",
        "add atomic measured-audio playback helpers",
    )

    # System TTS cannot expose a synthesized MP3 duration, but at least do not claim success if the
    # Android engine rejected the speak request.
    replace_once(
        vot,
        '''            final long id = ttsEngine.markBusy();\n            // System TTS doesn't support seekTo, so it will always play from the start.\n            tts.speak(seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);\n            return;''',
        '''            final long id = ttsEngine.markBusy();\n            // System TTS doesn't support seekTo, so it will always play from the start.\n            final int speakResult = tts.speak(\n                    seg.text, TextToSpeech.QUEUE_FLUSH, params, VOT_ID_PREFIX + id);\n            if (speakResult == TextToSpeech.SUCCESS) {\n                lastSpokenIndex = index;\n                SpanishStudyController.onDubPlaybackStarted(\n                        seg, index, speechDurationMs, rate);\n            } else {\n                handleEdgeAttemptFailure(seg, index, id, "Android System TTS rejected request");\n            }\n            return;''',
        "mark System TTS spoken only after accepted request",
    )

    # Cached Edge audio already has an exact duration. Route it through the same measured start logic.
    replace_once(
        vot,
        '''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);\n        if (cached != null) {\n            final long playbackId = ttsEngine.markBusy();\n            ttsEngine.play(cached, volume, playbackRate, startTimeMs, playbackId,\n                    VoiceOverTranslationPatch::triggerNextSegmentCheck);\n            return;\n        }''',
        '''        byte[] cached = TtsCache.get(currentVideoId, index, voice, lang, seg.text);\n        if (cached != null) {\n            final long playbackId = ttsEngine.markBusy();\n            startPreparedEdgePlayback(seg, index, voice, lang, volume, cached, playbackId,\n                    explicitSeekForThisPlayback);\n            return;\n        }''',
        "fit cached Edge audio from measured duration at actual playback time",
    )

    # On-demand synthesis used to retain the pre-synthesis character-count rate. Recompute after the
    # MP3 exists and clear the busy flag on failure so the same slot can actually retry.
    replace_once(
        vot,
        '''        final long playbackId = ttsEngine.markBusy();\n        final String videoIdSnapshot = currentVideoId;\n        final long startTimeMsSnapshot = startTimeMs;\n        Utils.runOnBackgroundThread(() -> {\n            byte[] data;\n            try {\n                data = ttsEngine.prefetch(seg.text, voice, lang);\n            } catch (Exception ex) {\n                logError(() -> "On-demand synthesis failed for segment " + index, ex);\n                Utils.runOnMainThread(VoiceOverTranslationPatch::triggerNextSegmentCheck);\n                return;\n            }\n            if (data.length > 0) {\n                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);\n            }\n            final byte[] finalData = data;\n            Utils.runOnMainThread(() -> {\n                if (finalData.length > 0 && playbackId == ttsEngine.getPlaybackId()) {\n                    // Re-read playback speed in case it changed during synthesis.\n                    final float playbackRateNow = rate * VideoInformation.getPlaybackSpeed();\n                    ttsEngine.play(finalData, volume, playbackRateNow, startTimeMsSnapshot, playbackId,\n                            VoiceOverTranslationPatch::triggerNextSegmentCheck);\n                } else {\n                    triggerNextSegmentCheck();\n                }\n            });\n        });''',
        '''        final long playbackId = ttsEngine.markBusy();\n        final String videoIdSnapshot = currentVideoId;\n        Utils.runOnBackgroundThread(() -> {\n            byte[] data;\n            try {\n                data = ttsEngine.prefetch(seg.text, voice, lang);\n            } catch (Exception ex) {\n                logError(() -> "On-demand synthesis failed for segment " + index, ex);\n                Utils.runOnMainThread(() -> handleEdgeAttemptFailure(\n                        seg, index, playbackId, ex.getClass().getSimpleName()));\n                return;\n            }\n            if (data.length > 0) {\n                TtsCache.put(videoIdSnapshot, index, voice, lang, seg.text, data);\n            }\n            final byte[] finalData = data;\n            Utils.runOnMainThread(() -> {\n                if (playbackId != ttsEngine.getPlaybackId()) return;\n                if (finalData.length > 0) {\n                    startPreparedEdgePlayback(seg, index, voice, lang, volume, finalData, playbackId,\n                            explicitSeekForThisPlayback);\n                } else {\n                    handleEdgeAttemptFailure(seg, index, playbackId, "empty Edge TTS audio");\n                }\n            });\n        });''',
        "recompute exact playback fit after on-demand synthesis and retry failures",
    )

    # Adaptive prefetch: long videos should maintain a useful buffer instead of falling behind after
    # one transient server error. Keep it serial (the Edge socket is serialized) but look farther
    # ahead and cap global backoff so a single failure cannot create a minute of silent source audio.
    replace_once(
        prefetcher,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "TtsPrefetcher dub-state import",
    )
    replacements = [
        ("    private static final int DISTANCE_IMMEDIATE_MS = 30_000;\n",
         "    private static final int DISTANCE_IMMEDIATE_MS = 45_000;\n",
         "extend immediate TTS lookahead"),
        ("    private static final int DISTANCE_NEAR_MS      = 60_000;\n",
         "    private static final int DISTANCE_NEAR_MS      = 120_000;\n",
         "extend near TTS lookahead"),
        ("    private static final int DELAY_IMMEDIATE_MS  = 200;\n",
         "    private static final int DELAY_IMMEDIATE_MS  = 120;\n",
         "faster immediate prefetch cadence"),
        ("    private static final int DELAY_NEAR_MS       = 1_000;\n",
         "    private static final int DELAY_NEAR_MS       = 450;\n",
         "faster near prefetch cadence"),
        ("    private static final int DELAY_BACKGROUND_MS = 4_000;\n",
         "    private static final int DELAY_BACKGROUND_MS = 2_000;\n",
         "faster background prefetch cadence"),
        ("    private static final int BACKOFF_MAX_MS      = 60_000; // Cap at 1 minute.\n",
         "    private static final int BACKOFF_MAX_MS      = 15_000; // Never lose a full minute of dubbing.\n",
         "cap long-video TTS backoff"),
    ]
    for old, new, label in replacements:
        replace_once(prefetcher, old, new, label)

    replace_once(
        prefetcher,
        '''                seg.durationMs = TtsEngine.mp3DurationMs(data.length);\n                // AutoDub-style invariant: generated audio may adapt its playback rate, but it\n                // never moves the video's canonical segment timestamps.''',
        '''                seg.durationMs = TtsEngine.mp3DurationMs(data.length);\n                SpanishStudyController.onDubAudioReady(seg, index, seg.durationMs);\n                // AutoDub-style invariant: generated audio may adapt its playback rate, but it\n                // never moves the video's canonical segment timestamps.''',
        "publish measured prefetched audio readiness",
    )

    print("Atomic dub-event, measured-duration playback, retry, and adaptive prefetch integration complete")


if __name__ == "__main__":
    main()
