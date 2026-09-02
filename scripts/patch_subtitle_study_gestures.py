#!/usr/bin/env python3
"""Make the bilingual subtitle itself a lightweight study control."""
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
        raise SystemExit("usage: patch_subtitle_study_gestures.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    overlay = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishSubtitleOverlay.java"
    if not overlay.is_file():
        raise RuntimeError(f"Required source missing: {overlay}")

    replace_once(
        overlay,
        '''        spanishView = createTextView(a);\n        englishView = createTextView(a);\n''',
        '''        spanishView = createTextView(a);\n        englishView = createTextView(a);\n\n        // Study gestures stay source-timeline based: tapping seeks the VIDEO back to this phrase,\n        // so picture, original audio, subtitles and Spanish dub all replay together.\n        spanishView.setOnClickListener(v -> SpanishStudyController.replayCurrentPhrase());\n        spanishView.setOnLongClickListener(v -> SpanishStudyController.replayPreviousPhrase());\n''',
        "add tap/long-press Spanish subtitle replay",
    )

    print("Subtitle study gesture integration complete")


if __name__ == "__main__":
    main()
