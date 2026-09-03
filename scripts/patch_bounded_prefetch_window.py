#!/usr/bin/env python3
"""Keep Edge TTS preparation bounded while prioritizing what is speaking now.

The prefetcher follows a moving window: up to three minutes ahead and forty-five seconds behind the
playhead. v2.6.3 diagnostics exposed an ordering bug in the upstream prefetcher: a segment that had
already started was classified as 'past', so every future segment could be synthesized before the
phrase the viewer was hearing right now. That forced on-demand TTS to compete with background
prefetch and caused intermittent silent stretches/skips.

v2.6.4 adds a priority-0 current-segment pass before future lookahead. Backoff is also capped when the
selected segment is currently on screen so one previous Edge failure cannot silence the active phrase
for many seconds. No persistent audio/video cache is added.
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
        "    private static final long PREFETCH_PAST_HORIZON_MS = 45_000L;\n"
        "    private static final int ACTIVE_SEGMENT_BACKOFF_CAP_MS = 800;\n",
        "add bounded moving TTS preparation window",
    )

    replace_once(
        prefetcher,
'''        // Priority 1: Future segments, closest first.
        for (int i = 0; i < segmentsSize; i++) {''',
'''        // Priority 0: the phrase currently under the playhead. Upstream treated a segment whose
        // start had already passed as "past", which meant all future TTS could outrank the exact
        // phrase the viewer needed now. That made on-demand synthesis contend with background work.
        for (int i = 0; i < segmentsSize; i++) {
            TranscriptSegment seg = segments.get(i);
            if (seg.startMs <= timeMs && timeMs < seg.endMs) {
                if (!TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)
                        && TtsCache.notCached(videoId, i, voice, lang, seg.text)) {
                    return new NextFetch(i, 0, seg);
                }
                break;
            }
        }

        // Priority 1: Future segments, closest first.
        for (int i = 0; i < segmentsSize; i++) {''',
        "prefetch the currently playing phrase before future phrases",
    )

    replace_once(
        prefetcher,
        '''            if (seg.startMs >= timeMs) {
                if (firstFutureIndex == segmentsSize) {''',
        '''            if (seg.startMs >= timeMs) {
                if (seg.startMs - timeMs > PREFETCH_FUTURE_HORIZON_MS) break;
                if (firstFutureIndex == segmentsSize) {''',
        "stop future synthesis beyond three-minute horizon",
    )

    replace_once(
        prefetcher,
        '''        for (int i = firstFutureIndex - 1; i >= 0; i--) {
            TranscriptSegment seg = segments.get(i);
            if (TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)) continue;''',
        '''        for (int i = firstFutureIndex - 1; i >= 0; i--) {
            TranscriptSegment seg = segments.get(i);
            if (timeMs - seg.endMs > PREFETCH_PAST_HORIZON_MS) break;
            if (TranscriptFetcher.isSpokenLanguageDifferent(lang, seg.lang)) continue;''',
        "bound past seek cache window",
    )

    replace_once(
        prefetcher,
'''                    if (currentBackoffMs > 0) {
                        delay = currentBackoffMs;
                    } else if (distanceMs <= DISTANCE_IMMEDIATE_MS) {''',
'''                    if (currentBackoffMs > 0) {
                        final boolean activeNow = next.seg.startMs <= timeMs && timeMs < next.seg.endMs;
                        delay = activeNow
                                ? Math.min(currentBackoffMs, ACTIVE_SEGMENT_BACKOFF_CAP_MS)
                                : currentBackoffMs;
                    } else if (distanceMs <= DISTANCE_IMMEDIATE_MS) {''',
        "cap TTS backoff for the currently audible phrase",
    )

    print("Current-first bounded TTS prefetch integration complete")


if __name__ == "__main__":
    main()
