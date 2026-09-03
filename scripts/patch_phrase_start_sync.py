#!/usr/bin/env python3
"""Fix the v2.5 phrase-start regression without expanding persistent caching.

Two independent v2.5 behaviors could make Spanish appear only partway through a subtitle slot:
1. measured-duration fitting could trim the BEGINNING of a phrase when the remaining source slot was
   too short at the configured maximum speech rate;
2. the new transport watchdog could gate each freshly prepared MP3 on a stale VideoState value even
   while the source video clock was actually advancing.

The source timeline remains authoritative, but ordinary playback now always starts Edge audio at
byte/time zero. Only a real user seek is allowed to seek into an MP3. If a phrase is still too long at
maximum speech rate, the existing hard source deadline may cut its tail rather than deleting its first
words. Transport pause state is latched by pause() (including while synthesis is still in flight), while
actual video-clock movement is allowed to overrule a stale non-PLAYING VideoState.
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
        raise SystemExit("usage: patch_phrase_start_sync.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    tts = pkg / "TtsEngine.java"
    for path in (vot, tts):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    # Never compensate for normal synthesis/network lateness by deleting the beginning of a phrase.
    # startTimeMs may be non-zero only when explicitSeek is true from the block immediately above.
    replace_once(
        vot,
        '''        // Normal network/synthesis lateness should not throw away words if speeding up can still fit\n        // the complete phrase. Only when even max speech rate cannot fit do we trim the minimum audio\n        // needed from the beginning so this one event cannot push every later event behind.\n        final float maxRate = Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f;\n        final long playableAudioAtMax = Math.max(1L, (long) (availableMs * maxRate));\n        final long remainingBeforeTrim = Math.max(1L, actualDurationMs - startTimeMs);\n        if (remainingBeforeTrim > playableAudioAtMax) {\n            long requiredTrim = remainingBeforeTrim - playableAudioAtMax;\n            startTimeMs = Math.min(actualDurationMs - 1L, startTimeMs + requiredTrim);\n        }\n\n        final long remainingSpeechMs = Math.max(1L, actualDurationMs - startTimeMs);''',
        '''        // Phrase-start invariant: ordinary sequential playback NEVER trims or seeks past\n        // the first Spanish word merely to make a late/long synthesis fit. Only the explicit-seek\n        // block above may make startTimeMs non-zero. calculateSpeechRate() will use the configured\n        // maximum rate when necessary, and the immutable source deadline remains the final guard\n        // against cumulative drift. If anything must be sacrificed, lose the tail at the source\n        // boundary rather than making every subtitle begin with missing Spanish words.\n        final long remainingSpeechMs = Math.max(1L, actualDurationMs - startTimeMs);''',
        "never trim the beginning of an ordinary Spanish phrase",
    )

    # Do not reinterpret a possibly stale VideoState as a fresh pause at the beginning of EVERY MP3.
    # pause() already latches transportPaused even when currentPlayer is null, which is what protects
    # the real pause-during-synthesis race.
    replace_once(
        tts,
        '''        final VideoState sourceStateAtStart = VideoState.getCurrent();\n        transportPaused = sourceStateAtStart != null && sourceStateAtStart != VideoState.PLAYING;\n        transportLastVideoMs = VideoInformation.getVideoTime();\n        transportLastAdvanceElapsedMs = SystemClock.elapsedRealtime();\n        scheduleTransportWatchdog();''',
        '''        // Preserve an actual latched pause, but do not manufacture one from a stale\n        // VideoState snapshot each time a new phrase begins. The normal state observer calls\n        // pause(), and pause() remembers that state even while Edge synthesis is still in flight.\n        transportLastVideoMs = VideoInformation.getVideoTime();\n        transportLastAdvanceElapsedMs = SystemClock.elapsedRealtime();\n        scheduleTransportWatchdog();''',
        "preserve latched pause without stale per-phrase VideoState gating",
    )

    # The real advancing source clock is stronger evidence than a lagging VideoState enum.
    replace_once(
        tts,
        '''            transportLastVideoMs = videoMs;\n            transportLastAdvanceElapsedMs = nowElapsed;\n            if (!explicitlyNotPlaying && transportPaused) resume();''',
        '''            transportLastVideoMs = videoMs;\n            transportLastAdvanceElapsedMs = nowElapsed;\n            if (transportPaused) resume();''',
        "let advancing video time resume audio despite stale VideoState",
    )

    # When an MP3 becomes ready, use the pause latch itself. Querying VideoState again here was the
    # second stale-state gate that could hold every phrase until after its subtitle had already begun.
    replace_once(
        tts,
        '''                final VideoState sourceStateNow = VideoState.getCurrent();\n                if (!transportPaused\n                        && (sourceStateNow == null || sourceStateNow == VideoState.PLAYING)) {\n                    mp.start();\n                } else {\n                    transportPaused = true;\n                    Logger.printDebug(() -> "Edge MP3 prepared while source transport is paused; waiting to resume");\n                }''',
        '''                if (!transportPaused) {\n                    mp.start();\n                } else {\n                    Logger.printDebug(() -> "Edge MP3 prepared during a latched source pause; waiting to resume");\n                }''',
        "start prepared phrase immediately unless a real pause was latched",
    )

    print("Spanish phrase-start synchronization regression fix complete")


if __name__ == "__main__":
    main()
