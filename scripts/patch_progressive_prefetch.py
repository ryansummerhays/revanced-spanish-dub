#!/usr/bin/env python3
"""Keep TTS synthesis buffered while long-video translation is still progressing.

Morphe normally starts TtsPrefetcher only after TranscriptFetcher returns. Translation itself is a
blocking multi-batch loop, so on a long video the first audible region can spend a long time doing
on-demand synthesis even though translated snapshots are already arriving. Feed each accepted
snapshot into the prefetcher without resetting the playhead.
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
        raise SystemExit("usage: patch_progressive_prefetch.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    vot = pkg / "VoiceOverTranslationPatch.java"
    prefetcher = pkg / "TtsPrefetcher.java"

    replace_once(
        vot,
        '''                                segments = SpanishStudyController.mergeTranslationUpdate(\n                                        segments, updated, resolveTargetLang());\n                                SpanishStudyController.onTranscriptUpdated(segments);''',
        '''                                segments = SpanishStudyController.mergeTranslationUpdate(\n                                        segments, updated, resolveTargetLang());\n                                SpanishStudyController.onTranscriptUpdated(segments);\n                                // Start synthesizing accepted Spanish immediately instead of waiting\n                                // for every later translation batch in a long video to finish.\n                                TtsPrefetcher.updateVideo(videoId, segments);''',
        "prefetch progressively translated snapshots",
    )

    replace_once(
        prefetcher,
        '''    static void updateVideo(String videoId, List<TranscriptSegment> segments) {\n        synchronized (lock) {\n            if (!videoId.equals(currentVideoId)) {\n                loadingLatch = new CountDownLatch(1);\n            }\n            currentVideoId = videoId;\n            currentSegments = Collections.unmodifiableList(segments);\n            currentVideoTimeMs = 0;\n            if (running) {''',
        '''    static void updateVideo(String videoId, List<TranscriptSegment> segments) {\n        synchronized (lock) {\n            final boolean videoChanged = !videoId.equals(currentVideoId);\n            if (videoChanged) {\n                loadingLatch = new CountDownLatch(1);\n                currentVideoTimeMs = 0;\n                currentBackoffMs = 0;\n            }\n            currentVideoId = videoId;\n            currentSegments = Collections.unmodifiableList(new ArrayList<>(segments));\n            // Progressive updates for the SAME video must preserve currentVideoTimeMs; resetting\n            // it to zero makes the prefetcher repeatedly synthesize the start instead of staying\n            // ahead of the actual playhead.\n            if (running) {''',
        "preserve prefetch playhead across progressive same-video snapshots",
    )

    replace_once(
        prefetcher,
        "import java.util.Collections;\n",
        "import java.util.ArrayList;\nimport java.util.Collections;\n",
        "TtsPrefetcher snapshot list import",
    )

    print("Progressive translation-to-TTS lookahead integration complete")


if __name__ == "__main__":
    main()
