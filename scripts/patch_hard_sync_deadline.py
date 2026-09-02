#!/usr/bin/env python3
"""Prevent slow Spanish TTS from accumulating lag behind the source speaker.

A translated clause may require a faster rate than the user's configured max. Morphe normally lets
that audio finish, which can make every later clause start increasingly late. This patch treats each
immutable English/source clause end as a hard synchronization deadline: if the old dub is still
speaking after that boundary, stop it and resume from the current source position in the new clause.
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
        raise SystemExit("usage: patch_hard_sync_deadline.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    if not vot.is_file():
        raise RuntimeError(f"Required source missing: {vot}")

    replace_once(
        vot,
        "        for (int i = 0, size = segments.size(); i < size; i++) {\n",
        "        // Never let a slow translated utterance push every later clause behind the video.\n"
        "        enforceSourceDeadline(timeMs);\n\n"
        "        for (int i = 0, size = segments.size(); i < size; i++) {\n",
        "enforce source deadline before dispatch",
    )

    deadline_method = r'''
    /**
     * Hard-sync policy used by professional-style timed dubbing: the source timeline wins.
     *
     * If the previous translated utterance cannot finish inside its immutable English/source slot
     * even at the configured maximum speech rate, do not allow its overrun to accumulate into the
     * rest of the video. Cut the stale utterance at the source boundary and let the normal dispatcher
     * start the clause that corresponds to the current video position. wasExplicitSeek makes a late
     * entry map proportionally into that clause instead of replaying it from its first word.
     */
    private static void enforceSourceDeadline(long timeMs) {
        if (lastSpokenIndex < 0 || lastSpokenIndex >= segments.size()) return;
        TranscriptSegment active = segments.get(lastSpokenIndex);
        if (timeMs < active.endMs) return;

        final boolean systemSpeaking = tts != null && tts.isSpeaking();
        if (!ttsEngine.isSpeaking() && !systemSpeaking) return;

        Logger.printDebug(() -> "Hard-sync cutoff at source boundary. segment="
                + lastSpokenIndex + " time=" + timeMs + " end=" + active.endMs);
        stopTtsPreservingMultiplier();
        wasExplicitSeek = true;
        lastSpokenIndex = -1;
    }

'''
    replace_once(
        vot,
        "    private static void triggerNextSegmentCheck() {\n",
        deadline_method + "    private static void triggerNextSegmentCheck() {\n",
        "add hard source deadline helper",
    )

    print("Hard source-timeline dub synchronization complete")


if __name__ == "__main__":
    main()
