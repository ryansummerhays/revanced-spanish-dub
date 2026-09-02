#!/usr/bin/env python3
"""Patch Morphe VoT into an AutoDub-style immutable timeline.

Applied after apply_overlay.py. Gemini translates the complete transcript before playback,
seeking never reprioritizes translation, and TTS/subtitles stay pinned to source timestamps.
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
        raise SystemExit("usage: patch_autodub_timeline.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    translator = pkg / "TranscriptTranslator.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    prefetcher = pkg / "TtsPrefetcher.java"

    for path in (translator, vot, prefetcher):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    # Gemini bypasses Morphe's progressive play-head batch dispatcher entirely. The source
    # transcript has already been fetched in full when translate() is called.
    replace_once(
        translator,
        '''        if (segments.isEmpty()) return segments;\n        Utils.verifyOffMainThread();\n\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        if (segments.isEmpty()) return segments;\n        Utils.verifyOffMainThread();\n\n        if (GeminiTranslator.isEnabled()) {\n            try {\n                // AutoDub-style: finish one canonical translation before playback consumes it.\n                // Seeking therefore never changes what gets translated or how segments are indexed.\n                return GeminiTranslator.translateWholeTranscript(videoId, segments, targetLang);\n            } catch (Exception ex) {\n                Logger.printException(() -> "Whole-transcript Gemini translation failed", ex);\n                return segments;\n            }\n        }\n\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        "whole-transcript Gemini fast path",
    )

    # The older injected delegate is unreachable for Gemini now but would still compile. Remove it
    # so the normal batch path remains exclusively Google/MyMemory/OpenRouter.
    replace_once(
        translator,
        '''        if (GeminiTranslator.isEnabled()) {\n            return GeminiTranslator.translateBatch(videoId, segments, targetLang);\n        }\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        "remove per-batch Gemini delegate",
    )

    # Seeking should only retarget playback. Do not cancel or mutate translation state.
    replace_once(
        vot,
        '''                // Re-target translation at the new position so a seek into an untranslated region\n                // is translated next instead of waiting for the sequential dispatch to reach it.\n                TranscriptTranslator.onSeek(timeMs);''',
        '''                // Translation is immutable in the AutoDub-style path. Seeking only retargets\n                // playback and TTS prefetch; it never cancels or reprioritizes translation.\n                TtsPrefetcher.triggerRescan();''',
        "seek retargets playback only",
    )

    # Dispatch by immutable source timestamps, never by mutable TTS playback windows.
    replace_once(
        vot,
        '''            final long segPlaybackStartMs = seg.playbackStartMs;\n            if (timeMs >= segPlaybackStartMs) {\n                if (timeMs < seg.playbackEndMs) {''',
        '''            final long segPlaybackStartMs = seg.startMs;\n            if (timeMs >= segPlaybackStartMs) {\n                if (timeMs < seg.endMs) {''',
        "dispatch from immutable source timestamps",
    )

    # Speech fitting uses the immutable slot. On seek, map source progress proportionally into the
    # synthesized clip instead of assuming source milliseconds equal TTS milliseconds.
    replace_once(
        vot,
        '''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.playbackStartMs);\n        final long availableMs = seg.playbackEndMs - speakFromMs;''',
        '''        final long speakFromMs = Math.max(lastVideoTimeMs, seg.startMs);\n        final long availableMs = seg.endMs - speakFromMs;''',
        "fit speech to immutable source slot",
    )

    replace_once(
        vot,
        '''        if (wasExplicitSeek) {\n            final long timeIntoSegment = lastVideoTimeMs - seg.playbackStartMs;\n            if (timeIntoSegment > SEEK_INTO_THRESHOLD_MS) {\n                // Approximate audio position assuming natural speed. The TTS clip is usually\n                // shorter than the video segment, so clamp to its length to avoid seeking past\n                // the end.\n                startTimeMs = Math.min(timeIntoSegment, speechDurationMs);\n            }''',
        '''        if (wasExplicitSeek) {\n            final long timeIntoSegment = lastVideoTimeMs - seg.startMs;\n            if (timeIntoSegment > SEEK_INTO_THRESHOLD_MS) {\n                final long sourceSpanMs = Math.max(1L, seg.endMs - seg.startMs);\n                final double sourceProgress = Math.max(0.0, Math.min(1.0,\n                        timeIntoSegment / (double) sourceSpanMs));\n                // Map video progress into the generated clip. This stays stable even when the\n                // Spanish utterance is shorter/longer than the source English slot.\n                startTimeMs = Math.min(Math.max(0L, speechDurationMs - 1L),\n                        Math.round(sourceProgress * speechDurationMs));\n            }''',
        "proportional TTS seek within segment",
    )

    # Do not let background synthesis rewrite segment boundaries. Audio duration is still measured
    # and cached, but the canonical video timeline is never modified.
    replace_once(
        prefetcher,
        '''                seg.durationMs = TtsEngine.mp3DurationMs(data.length);\n                engine.adjustPlaybackTimes(currentSegments, index,\n                        VoiceOverTranslationPatch.getLastSpokenIndex(),\n                        videoId, voice, lang);''',
        '''                seg.durationMs = TtsEngine.mp3DurationMs(data.length);\n                // AutoDub-style invariant: generated audio may adapt its playback rate, but it\n                // never moves the video's canonical segment timestamps.''',
        "disable mutable playback-window reshaping",
    )

    print("AutoDub-style immutable timeline integration complete")


if __name__ == "__main__":
    main()
