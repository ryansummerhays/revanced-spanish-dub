#!/usr/bin/env python3
"""Prefer audiovisual Gemini grounding for each progressive batch, with text-only fallback."""
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
        raise SystemExit("usage: patch_video_grounding_delegate.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    gemini = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiTranslator.java"
    if not gemini.is_file():
        raise RuntimeError(f"Required source missing: {gemini}")

    replace_once(
        gemini,
        '''        if (segments == null || segments.isEmpty()) return new ArrayList<>();\n\n        PreparedTranscript prepared = prepared(videoId, targetLang);''',
        '''        if (segments == null || segments.isEmpty()) return new ArrayList<>();\n\n        // v2.6: First try Gemini's public-YouTube audiovisual path. It can listen to the\n        // actual voice at these immutable timestamps, correct unclear ASR words with real audio/\n        // video context, and assign conservative speaker labels. If the preview endpoint, model,\n        // video visibility, quota, or validation fails, return null and continue through the proven\n        // transcript-only Gemini path below.\n        List<String> audiovisual = GeminiVideoGrounding.translateBatch(videoId, segments, targetLang);\n        if (audiovisual != null && audiovisual.size() == segments.size()) return audiovisual;\n\n        PreparedTranscript prepared = prepared(videoId, targetLang);''',
        "prefer audiovisual grounding with safe text-only fallback",
    )

    print("Audiovisual Gemini progressive delegate integration complete")


if __name__ == "__main__":
    main()
