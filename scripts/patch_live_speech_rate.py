#!/usr/bin/env python3
"""Make max-speech-rate changes restart the active dub cleanly on the immutable video timeline."""
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
        '''    private static int maxSpeechRateChangeGeneration;\n\n    /**\n     * Recomputes the currently audible dub after max speech rate changes. The source subtitle/TTS\n     * timestamps remain immutable; only the audio playback rate is recalculated. Slider movement\n     * is debounced so dragging across several values causes one clean restart after the user\n     * settles on a value instead of repeatedly tearing down the active utterance.\n     */\n    public static void updateMaxSpeechRate() {\n        Utils.verifyOnMainThread();\n        final int generation = ++maxSpeechRateChangeGeneration;\n        Utils.runOnMainThreadDelayed(() -> {\n            if (generation != maxSpeechRateChangeGeneration) return;\n            if (!Settings.VOT_ENABLED.get() || !sessionEnabled || segments.isEmpty()) return;\n            if (lastSpokenIndex >= 0 || ttsEngine.isSpeaking() || (tts != null && tts.isSpeaking())) {\n                wasExplicitSeek = true;\n                stopTtsPreservingMultiplier();\n                lastSpokenIndex = -1;\n                triggerNextSegmentCheck();\n            }\n        }, 250);\n    }\n\n    /** Re-applies the ducking multiplier so a Settings change takes effect immediately. */\n    public static void updateOriginalAudioMultiplier() {''',
        "debounced restart after max-rate change",
    )

    print("Live max-speech-rate resync integration complete")


if __name__ == "__main__":
    main()
