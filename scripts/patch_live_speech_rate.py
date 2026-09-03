#!/usr/bin/env python3
"""Make max-speech-rate changes live and non-destructive.

The older implementation stopped the active TTS, marked the change like an explicit video seek,
and restarted the dispatcher. That was far too invasive for a simple preference change and could
leave the current atomic event / subtitle timeline in a bad state. A speech-rate slider must never
clear, reload, or restart subtitles.

New behavior:
- slider movement is still debounced;
- lowering the max clamps an active Edge MediaPlayer in place when possible;
- raising the max does not suddenly accelerate an already-speaking phrase; it applies naturally to
  the next phrase;
- System TTS keeps its current utterance and uses the new ceiling on the next phrase;
- no stopTts(), explicit-seek flag, lastSpokenIndex reset, transcript reload, or subtitle mutation.
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
        raise SystemExit("usage: patch_live_speech_rate.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    sheet = pkg / "VotBottomSheet.java"
    for path in (vot, sheet):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    replace_once(
        sheet,
        '''        content.addView(makeSliderRow(context,\n                str("morphe_vot_max_speech_rate_title"),\n                Settings.VOT_MAX_SPEECH_RATE,\n                fg,\n                Settings.VOT_MAX_SPEECH_RATE::save));''',
        '''        content.addView(makeSliderRow(context,\n                str("morphe_vot_max_speech_rate_title"),\n                Settings.VOT_MAX_SPEECH_RATE,\n                fg,\n                value -> {\n                    Settings.VOT_MAX_SPEECH_RATE.save(value);\n                    VoiceOverTranslationPatch.updateMaxSpeechRate();\n                }));''',
        "max speech rate callback",
    )

    replace_once(
        vot,
        '''    /** Re-applies the ducking multiplier so a Settings change takes effect immediately. */\n    public static void updateOriginalAudioMultiplier() {''',
        '''    private static int maxSpeechRateChangeGeneration;\n\n    /**\n     * Applies a max-speech-rate change without disturbing the canonical subtitle/dub event.\n     *\n     * <p>This preference is only a CEILING. Lowering it may slow the currently-playing Edge MP3\n     * in place. Raising it does not force the current phrase faster, because doing so would create\n     * an audible jump; the new higher ceiling is used when the next phrase is scheduled. Android\n     * System TTS cannot safely retime an utterance already in progress, so it likewise adopts the\n     * new ceiling on the next phrase.\n     *\n     * <p>Critically, this method never stops TTS, never sets wasExplicitSeek, never resets\n     * lastSpokenIndex, and never changes the transcript/subtitle list. Moving a speed slider must\n     * not be capable of making Spanish subtitles or audio disappear.\n     */\n    public static void updateMaxSpeechRate() {\n        Utils.verifyOnMainThread();\n        final int generation = ++maxSpeechRateChangeGeneration;\n        Utils.runOnMainThreadDelayed(() -> {\n            if (generation != maxSpeechRateChangeGeneration) return;\n            if (!Settings.VOT_ENABLED.get() || !sessionEnabled) return;\n\n            final float newMaxRate = Math.max(1.0f,\n                    Settings.VOT_MAX_SPEECH_RATE.get() / 10.0f);\n\n            // Edge MediaPlayer supports live PlaybackParams changes. Only clamp downward: a\n            // higher max is permission for FUTURE fitting, not an instruction to speed up speech\n            // that is already halfway through a natural phrase.\n            if (ttsEngine.isSpeaking() && currentTtsBaseRate > newMaxRate) {\n                currentTtsBaseRate = newMaxRate;\n                lastAppliedPlaybackSpeed = VideoInformation.getPlaybackSpeed();\n                ttsEngine.setPlaybackRate(currentTtsBaseRate\n                        * Math.max(0.1f, lastAppliedPlaybackSpeed));\n                Logger.printDebug(() -> "Live max speech rate clamped active Edge dub to "\n                        + currentTtsBaseRate + "x");\n            }\n\n            // Prefetched Edge MP3 bytes are synthesized at natural speed; they do not encode the\n            // playback-rate ceiling. No cache invalidation or transcript reload is necessary. The\n            // next speak() call will calculateSpeechRate() using the freshly saved setting.\n        }, 250);\n    }\n\n    /** Re-applies the ducking multiplier so a Settings change takes effect immediately. */\n    public static void updateOriginalAudioMultiplier() {''',
        "non-destructive live max-rate update",
    )

    print("Live max-speech-rate integration complete (non-destructive)")


if __name__ == "__main__":
    main()
