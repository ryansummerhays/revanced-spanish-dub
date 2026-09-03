#!/usr/bin/env python3
"""Run audiovisual Gemini grounding as a non-blocking sidecar.

The first v2.6 implementation synchronously tried YouTube-video grounding before every text translation
batch. Even though it had a text-only fallback, a slow/unsupported video request could consume the
whole audible window before fallback returned, making Spanish appear completely dead. Basic Spanish
translation must never depend on the experimental multimodal path.
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
        raise SystemExit("usage: patch_video_grounding_delegate.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    gemini = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiTranslator.java"
    if not gemini.is_file():
        raise RuntimeError(f"Required source missing: {gemini}")

    replace_once(
        gemini,
        '''        if (segments == null || segments.isEmpty()) return new ArrayList<>();\n\n        PreparedTranscript prepared = prepared(videoId, targetLang);''',
        '''        if (segments == null || segments.isEmpty()) return new ArrayList<>();\n\n        // v2.6.1 reliability invariant: experimental audiovisual ASR/speaker grounding is SIDE DATA.\n        // It may improve corrected English and speaker labels later, but it can never delay the\n        // ordinary text-only translation that subtitles/TTS need right now. One bounded background\n        // sidecar is scheduled opportunistically and this method immediately continues below.\n        GeminiVideoGroundingSidecar.schedule(videoId, segments, targetLang);\n\n        PreparedTranscript prepared = prepared(videoId, targetLang);''',
        "make audiovisual grounding asynchronous and non-blocking",
    )

    print("Non-blocking audiovisual Gemini sidecar integration complete")


if __name__ == "__main__":
    main()
