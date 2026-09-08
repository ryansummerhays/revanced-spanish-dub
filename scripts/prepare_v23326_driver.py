#!/usr/bin/env python3
"""Prepare the v2.33.26 patch driver for a compile-safe legacy-diarizer shutdown.

The generated Stage-E/F/G/J body is intentionally left in source for audit/history, but a volatile
runtime gate makes it unreachable in practice without Java's compile-time unreachable-code rules.
"""
from pathlib import Path
import re
import sys


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: prepare_v23326_driver.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    driver = repo / "scripts/patch_v23326_neural_absolute_timeline.py"

    pt = player.read_text(encoding="utf-8")
    field_anchor = "    private static final AtomicReference<AudioTrack> lastAudioTrackRef = new AtomicReference<>(null);\n"
    if pt.count(field_anchor) != 1:
        raise RuntimeError("could not locate lastAudioTrackRef field")
    pt = pt.replace(field_anchor,
            field_anchor + "    private static volatile boolean studyLegacySpeakerDiarizationEnabled = false;\n", 1)
    player.write_text(pt, encoding="utf-8")
    print("prepared: volatile legacy speaker gate")

    text = driver.read_text(encoding="utf-8")
    old = '''        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        return;
        /* legacy Stage-E/F/G/J retained below for source history but unreachable */
        /*
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    new = '''        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        if (!studyLegacySpeakerDiarizationEnabled) return;
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    if text.count(old) != 1:
        raise RuntimeError("could not locate v2.33.26 retirement injection")
    text = text.replace(old, new, 1)

    pattern = re.compile(
        r'''    # Close the comment just before the method's final catch\..*?'''
        r'''    rep\(player, legacy_end, legacy_end_new, "close retired legacy PCM diarization source block"\)\n''',
        re.S,
    )
    text, n = pattern.subn("", text, count=1)
    if n != 1:
        raise RuntimeError("could not remove obsolete block-comment close patch")
    driver.write_text(text, encoding="utf-8")
    print("prepared: compile-safe v2.33.26 patch driver")


if __name__ == "__main__":
    main()
