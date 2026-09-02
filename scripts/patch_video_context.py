#!/usr/bin/env python3
"""Feed title/channel/description/keywords from the existing YouTube player response into Gemini.

No extra YouTube request is made: TranscriptFetcher already downloads the Innertube player JSON to
locate the caption track. We reuse videoDetails so Gemini can reason about niche names, jargon, game
items, technical terms and likely ASR mistakes using actual video subject context.
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
        '''        String response = Requester.parseString(conn);\n\n        // Reuse metadata from the player response that we already fetched for captions. This gives\n        // Gemini strong subject-matter context without another network request. Missing metadata is\n        // harmless; GeminiTranslator falls back to whole-transcript-only context.\n        try {\n            JSONObject root = new JSONObject(response);\n            JSONObject details = root.optJSONObject("videoDetails");\n            if (details != null) {\n                StringBuilder subjectDetails = new StringBuilder();\n                JSONArray keywords = details.optJSONArray("keywords");\n                if (keywords != null && keywords.length() > 0) {\n                    subjectDetails.append("Keywords/tags: ");\n                    int keywordLimit = Math.min(40, keywords.length());\n                    for (int i = 0; i < keywordLimit; i++) {\n                        if (i > 0) subjectDetails.append(", ");\n                        subjectDetails.append(keywords.optString(i, ""));\n                    }\n                    subjectDetails.append(". ");\n                }\n                subjectDetails.append(details.optString("shortDescription", ""));\n                GeminiTranslator.prepareVideoMetadata(\n                        videoId,\n                        details.optString("title", ""),\n                        details.optString("author", ""),\n                        subjectDetails.toString());\n            }\n        } catch (Exception metadataError) {\n            Logger.printDebug(() -> "Could not extract video metadata for Gemini context: "\n                    + metadataError.getClass().getSimpleName() + ": " + metadataError.getMessage());\n        }\n\n        return new String[]{findBestCaptionUrl(response), extractPoToken(response)};''',
        "publish title/channel/description/keywords to Gemini",
    )

    print("YouTube video-context integration complete")


if __name__ == "__main__":
    main()
