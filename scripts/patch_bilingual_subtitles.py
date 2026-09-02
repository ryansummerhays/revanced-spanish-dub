#!/usr/bin/env python3
"""Wire English source captions into the study overlay and suppress duplicate auto-CC."""
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
        raise SystemExit("usage: patch_bilingual_subtitles.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    auto = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/AutoCaptionsPatch.java"

    for path in (fetcher, auto):
        if not path.is_file():
            raise RuntimeError(f"Required source file not found: {path}")

    replace_once(
        fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "TranscriptFetcher study import",
    )
    replace_once(
        fetcher,
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n",
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n        SpanishStudyController.onSourceTranscriptFetched(segments);\n",
        "publish English source transcript",
    )

    replace_once(
        auto,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "AutoCaptions study import",
    )
    replace_once(
        auto,
        '''    public static boolean disableAutoCaptions(boolean original) {
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        '''    public static boolean disableAutoCaptions(boolean original) {
        // The study overlay can render the original English transcript itself. Keep YouTube's
        // automatically-enabled CC off to prevent a duplicate caption line; a manual CC tap
        // after the guard window still works normally.
        if (SpanishStudyController.suppressNativeCaptions()) return true;

        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        "suppress duplicate YouTube auto captions",
    )

    print("Bilingual subtitle integration complete")


if __name__ == "__main__":
    main()
