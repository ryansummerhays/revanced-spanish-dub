#!/usr/bin/env python3
"""Hard-link Edge dub playback to the real YouTube transport.

VideoState callbacks are useful but can arrive late or be missed on some YouTube builds. This adds a
second, independent watchdog inside TtsEngine: while Spanish is active it samples the digital video
position (not audio) and pauses the MediaPlayer whenever YouTube is paused, errored, or stalled. When
video time advances again, the exact same MP3 resumes from the same position.
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
        raise SystemExit("usage: patch_transport_sync.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    tts = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TtsEngine.java"
    if not tts.is_file():
        raise RuntimeError(f"Required source missing: {tts}")

    replace_once(
        tts,
        "import android.media.audiofx.LoudnessEnhancer;\n",
        "import android.media.audiofx.LoudnessEnhancer;\nimport android.os.SystemClock;\n",
        "transport watchdog SystemClock import",
    )
    replace_once(
        tts,
        "import app.morphe.extension.youtube.patches.VideoInformation;\n",
        "import app.morphe.extension.youtube.patches.VideoInformation;\nimport app.morphe.extension.youtube.shared.VideoState;\n",
        "transport watchdog VideoState import",
    )

    replace_once(
        tts,
        '''    /** Tracks the active synthesis/playback session to prevent overlapping segments. */\n    private long playbackId;''',
        '''    /** Tracks the active synthesis/playback session to prevent overlapping segments. */\n    private long playbackId;\n\n    // Redundant transport synchronization. We intentionally use VIDEO TIME only: no microphone,\n    // Visualizer, speaker output, or room audio participates in pause/buffer detection.\n    private static final long TRANSPORT_WATCHDOG_TICK_MS = 90L;\n    private static final long TRANSPORT_STALL_PAUSE_MS = 420L;\n    private static final long TRANSPORT_ADVANCE_EPSILON_MS = 12L;\n    private boolean transportPaused;\n    private boolean transportWatchdogScheduled;\n    private long transportLastVideoMs = -1L;\n    private long transportLastAdvanceElapsedMs;''',
        "add transport watchdog state",
    )

    replace_once(
        tts,
        '''        Utils.runOnBackgroundThread(() -> {\n            try {\n                // playMp3 blocks until completion or error.''',
        '''        transportPaused = false;\n        transportLastVideoMs = VideoInformation.getVideoTime();\n        transportLastAdvanceElapsedMs = SystemClock.elapsedRealtime();\n        scheduleTransportWatchdog();\n\n        Utils.runOnBackgroundThread(() -> {\n            try {\n                // playMp3 blocks until completion or error.''',
        "start transport watchdog for every Edge playback",
    )

    replace_once(
        tts,
        '''    /**\n     * Pauses the active MediaPlayer without releasing it so playback can resume from the\n     * same MP3 position. Audio focus and engine state are intentionally left untouched\n     * so resume() avoids the audio-ducking ramp delay that would clip the first frames.\n     */\n    void pause() {\n        Utils.verifyOnMainThread();\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.pause();\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer pause failed", ex);\n        }\n    }\n\n    /** Resumes a previously paused MediaPlayer. No-op if there is no active player. */\n    void resume() {\n        Utils.verifyOnMainThread();\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.start();\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer resume failed", ex);\n        }\n    }''',
        '''    /**\n     * Pauses the active Edge MP3 in place. Idempotent so state callbacks and the independent\n     * transport watchdog may both request the same pause safely.\n     */\n    void pause() {\n        Utils.verifyOnMainThread();\n        if (transportPaused) return;\n        transportPaused = true;\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.pause();\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer pause failed", ex);\n        }\n    }\n\n    /** Resume the same MP3 position after YouTube itself is moving again. */\n    void resume() {\n        Utils.verifyOnMainThread();\n        if (!transportPaused) return;\n        transportPaused = false;\n        if (currentPlayer == null) return;\n        try {\n            currentPlayer.start();\n        } catch (Exception ex) {\n            VoiceOverTranslationPatch.logError(() -> "MediaPlayer resume failed", ex);\n        }\n    }''',
        "make Edge pause/resume idempotent",
    )

    helpers = r'''
    private void scheduleTransportWatchdog() {
        Utils.verifyOnMainThread();
        if (transportWatchdogScheduled || stopped || !speaking) return;
        transportWatchdogScheduled = true;
        Utils.runOnMainThreadDelayed(this::transportWatchdogTick, TRANSPORT_WATCHDOG_TICK_MS);
    }

    /**
     * Reconciles Spanish playback against the real source-video clock. This catches PAUSED callbacks
     * that arrive late and buffering/stalls where VideoState can remain PLAYING even though the
     * source clock has stopped. The source transport always wins.
     */
    private void transportWatchdogTick() {
        Utils.verifyOnMainThread();
        transportWatchdogScheduled = false;
        if (stopped || !speaking) return;

        final long nowElapsed = SystemClock.elapsedRealtime();
        final long videoMs = VideoInformation.getVideoTime();
        final VideoState state = VideoState.getCurrent();
        final boolean explicitlyNotPlaying = state != null && state != VideoState.PLAYING;

        if (transportLastVideoMs < 0L
                || Math.abs(videoMs - transportLastVideoMs) >= TRANSPORT_ADVANCE_EPSILON_MS) {
            transportLastVideoMs = videoMs;
            transportLastAdvanceElapsedMs = nowElapsed;
            if (!explicitlyNotPlaying && transportPaused) resume();
        } else {
            final boolean stalled = nowElapsed - transportLastAdvanceElapsedMs >= TRANSPORT_STALL_PAUSE_MS;
            if ((explicitlyNotPlaying || stalled) && !transportPaused) pause();
        }

        scheduleTransportWatchdog();
    }

'''
    replace_once(
        tts,
        "    /** Updates the active playback volume. No-op if there is no active player. */\n",
        helpers + "    /** Updates the active playback volume. No-op if there is no active player. */\n",
        "add source-clock transport watchdog",
    )

    replace_once(
        tts,
        '''        stopped = true;\n        speaking = false;''',
        '''        stopped = true;\n        speaking = false;\n        transportPaused = false;''',
        "reset transport state when TTS stops",
    )

    print("Hard YouTube transport synchronization integration complete")


if __name__ == "__main__":
    main()
