#!/usr/bin/env python3
"""Keep very long videos from starving the first Spanish subtitle/TTS batch.

The contextual Gemini path snapshots the entire immutable transcript, which is correct, but v2.5.1
also built the recurring-term index by scanning every semantic clause before the progressive translator
could dispatch its first tiny batch. On a 50-90 minute video the clause count can become very large.

This patch keeps the full transcript for immutable ID/timing alignment and local context, while limiting
startup-only whole-video term mining to an evenly distributed sample. Immediate context around every
translated batch still comes from the complete transcript, so niche names/jargon near the spoken line
are not lost. Startup work therefore becomes effectively constant with video length.
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
        raise SystemExit("usage: patch_long_video_startup.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    gemini = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiTranslator.java"
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    for path in (gemini, translator):
        if not path.is_file():
            raise RuntimeError(f"Required source missing: {path}")

    replace_once(
        gemini,
        "    private static final int MAX_RECURRING_TERMS = 120;\n",
        "    private static final int MAX_RECURRING_TERMS = 120;\n"
        "    private static final int MAX_GLOBAL_CONTEXT_SAMPLE_SEGMENTS = 600;\n",
        "bound long-video terminology sampling",
    )

    replace_once(
        gemini,
        '''    /** Capture the immutable source list and a compact whole-video subject index before batching. */\n    public static synchronized void prepareTranscript(String videoId,\n                                                      List<TranscriptSegment> segments,\n                                                      String targetLang) {\n        if (videoId == null || segments == null || segments.isEmpty()) return;\n        List<TranscriptSegment> snapshot = new ArrayList<>(segments);\n        PREPARED.put(cacheKey(videoId, targetLang),\n                new PreparedTranscript(snapshot, buildGlobalContext(videoId, snapshot)));\n    }''',
        '''    /**\n     * Capture the complete immutable source list, but make whole-video terminology preparation\n     * independent of video length. The complete snapshot is still used for every local context\n     * window and exact source-ID lookup. Only the recurring-term index is sampled.\n     */\n    public static void prepareTranscript(String videoId,\n                                         List<TranscriptSegment> segments,\n                                         String targetLang) {\n        if (videoId == null || segments == null || segments.isEmpty()) return;\n        final List<TranscriptSegment> snapshot = new ArrayList<>(segments);\n        final List<TranscriptSegment> contextSample = sampleForGlobalContext(snapshot);\n        final String context = buildGlobalContext(videoId, contextSample);\n        synchronized (GeminiTranslator.class) {\n            PREPARED.put(cacheKey(videoId, targetLang),\n                    new PreparedTranscript(snapshot, context));\n        }\n        Logger.printDebug(() -> "Gemini prepared transcript: total=" + snapshot.size()\n                + " contextSample=" + contextSample.size());\n    }\n\n    private static List<TranscriptSegment> sampleForGlobalContext(List<TranscriptSegment> segments) {\n        final int size = segments.size();\n        if (size <= MAX_GLOBAL_CONTEXT_SAMPLE_SEGMENTS) return segments;\n\n        // Even sampling preserves evidence from the beginning, middle and end instead of only\n        // scanning an arbitrary prefix of a long stream/VOD. The immediate +/- local context for\n        // each batch still uses the complete transcript.\n        final ArrayList<TranscriptSegment> sample =\n                new ArrayList<>(MAX_GLOBAL_CONTEXT_SAMPLE_SEGMENTS);\n        final int slots = MAX_GLOBAL_CONTEXT_SAMPLE_SEGMENTS;\n        for (int i = 0; i < slots; i++) {\n            final int index = (int) Math.round(i * (size - 1.0) / (slots - 1.0));\n            sample.add(segments.get(index));\n        }\n        return sample;\n    }''',
        "constant-time long-video Gemini preparation",
    )

    # Make the urgent first Gemini batch smaller than the background batches. 350 chars can still be
    # many one-line semantic clauses after our splitter; ~220 chars generally gets the first few
    # spoken phrases through Gemini + grounding and into TTS sooner. This constant is shared with
    # OpenRouter and remains a reasonable fast-start size there as well.
    replace_once(
        translator,
        "    private static final int OPENROUTER_FIRST_BATCH_CHARS = 350;\n",
        "    private static final int OPENROUTER_FIRST_BATCH_CHARS = 220;\n",
        "faster first audible translation batch",
    )

    print("Long-video progressive translation startup integration complete")


if __name__ == "__main__":
    main()
