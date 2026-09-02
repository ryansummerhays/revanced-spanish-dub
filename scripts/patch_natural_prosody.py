#!/usr/bin/env python3
"""Use conservative punctuation-aware SSML for Spanish Edge TTS.

This replaces the former playback-Visualizer expression path. No audio capture or RECORD_AUDIO
permission is involved: phrasing comes only from the already-grounded subtitle text.
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
        raise SystemExit("usage: patch_natural_prosody.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    tts = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TtsEngine.java"
    if not tts.is_file():
        raise RuntimeError(f"Required source missing: {tts}")

    replace_once(
        tts,
        '''                + "<voice name='" + voice + "'>" + escapeXml(text) + "</voice></speak>";''',
        '''                + "<voice name='" + voice + "'>"\n                + SpanishStudyController.buildNaturalSsml(text)\n                + "</voice></speak>";''',
        "use punctuation-aware grounded SSML fragment",
    )

    print("Natural punctuation-based Edge prosody integration complete")


if __name__ == "__main__":
    main()
