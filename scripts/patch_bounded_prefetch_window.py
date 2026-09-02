#!/usr/bin/env python3
"""Keep Edge TTS preparation useful without synthesizing an entire long video into memory.

The prefetcher follows a moving window: up to three minutes ahead and forty-five seconds behind the
playhead. This is enough to absorb network hiccups and seeks while preventing background synthesis
from filling the LRU with far-future phrases that may never be watched.
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
        raise SystemExit("usage: patch_bounded_prefetch_window.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    prefetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TtsPrefetcher.java"
    if not prefetcher.is_file():
        raise RuntimeError(f"Required source missing: {prefetcher}")

    replace_once(
        prefetcher,
        "    private static final int DISTANCE_PREFETCH_IGNORE = 10_000;\n",
        "    private static final int DISTANCE_PREFETCH_IGNORE = 10_000;\n"
        "    private static final long PREFETCH_FUTURE_HORIZON_MS = 180_000L;\n"
        "    private static final long PREFETCH_PAST_HORIZON_MS = 45_000L;\n",
        "add bounded moving TTS preparation window",
    )

    replace_once(
        prefetcher,
        '''            if (seg.startMs >= timeMs) {\n                if (firstFutureIndex == segmentsSize) {''',
        '''            if (seg.startMs >= timeMs) {\n                if (seg.startMs - timeMs > PREFETCH_FUTURE_HORIZON_MS) break;\n                if (firstFutureIndex == segmentsSize) {''',
        "stop future synthesis beyond three-minute horizon",
    )

    replace_once(
        prefetcher,
        '''        for (int i = firstFutureIndex - 1; i >= 0; i--) {\n            TranscriptSegment seg = segments.get(i);\n            if (TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)) continue;''',
        '''        for (int i = firstFutureIndex - 1; i >= 0; i--) {\n            TranscriptSegment seg = segments.get(i);\n            if (timeMs - seg.endMs > PREFETCH_PAST_HORIZON_MS) break;\n            if (TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)) continue;''',
        "bound past seek cache window",
    )

    print("Moving-window TTS prefetch integration complete")


if __name__ == "__main__":
    main()
