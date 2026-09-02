#!/usr/bin/env python3
"""Feed title/channel/description from YouTube's existing Innertube response into Gemini.

No extra YouTube request is made: TranscriptFetcher already downloads the player JSON to locate the
caption track. We reuse videoDetails from that same response so Gemini can reason about niche names,
jargon, game items, technical terms and likely ASR mistakes using actual video subject context.
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
        raise SystemExit("usage: patch_video_context.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    if not fetcher.is_file():
        raise RuntimeError(f"Required source missing: {fetcher}")

    replace_once(
        fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.GeminiTranslator;\n",
        "TranscriptFetcher Gemini video-context import",
    )

    replace_once(
        fetcher,
        '''        String response = Requester.parseString(conn);\n        return new String[]{findBestCaptionUrl(response), extractPoToken(response)};''',
        '''        String response = Requester.parseString(conn);\n\n        // Reuse metadata from the player response that we already fetched for captions. This gives\n        // Gemini strong subject-matter context without another network request. Missing metadata is\n        // harmless; GeminiTranslator falls back to whole-transcript-only context.\n        try {\n            JSONObject root = new JSONObject(response);\n            JSONObject details = root.optJSONObject("videoDetails");\n            if (details != null) {\n                GeminiTranslator.prepareVideoMetadata(\n                        videoId,\n                        details.optString("title", ""),\n                        details.optString("author", ""),\n                        details.optString("shortDescription", ""));\n            }\n        } catch (Exception metadataError) {\n            Logger.printDebug(() -> "Could not extract video metadata for Gemini context", metadataError);\n        }\n\n        return new String[]{findBestCaptionUrl(response), extractPoToken(response)};''',
        "publish title/channel/description to Gemini",
    )

    print("YouTube video-context integration complete")


if __name__ == "__main__":
    main()
