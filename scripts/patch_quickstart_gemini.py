#!/usr/bin/env python3
"""Keep whole-transcript Gemini context while allowing the first dubbed block to start quickly.

Applied after patch_autodub_timeline.py. The immutable source timeline remains unchanged; only the
translation delivery strategy changes from all-at-once blocking to progressive publication.
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
        raise SystemExit("usage: patch_quickstart_gemini.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    if not translator.is_file():
        raise RuntimeError(f"Required source missing: {translator}")

    # v2.2 blocked until every Gemini output block finished. Prepare the complete source transcript
    # as context, then let Morphe's existing progressive dispatcher publish the first tiny batch as
    # soon as it returns. Every batch still sees the entire source transcript through GeminiTranslator.
    replace_once(
        translator,
        '''        if (GeminiTranslator.isEnabled()) {\n            try {\n                // AutoDub-style: finish one canonical translation before playback consumes it.\n                // Seeking therefore never changes what gets translated or how segments are indexed.\n                return GeminiTranslator.translateWholeTranscript(videoId, segments, targetLang);\n            } catch (Exception ex) {\n                Logger.printException(() -> "Whole-transcript Gemini translation failed", ex);\n                return segments;\n            }\n        }\n\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        '''        if (GeminiTranslator.isEnabled()) {\n            // Full-video context is captured once before batching. The first translated block can\n            // then be published immediately instead of waiting for the whole video to finish.\n            GeminiTranslator.prepareTranscript(videoId, segments, targetLang);\n        }\n\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();''',
        "prepare full Gemini context without blocking playback",
    )

    # The first Gemini batch is still capped by Morphe's existing 350-character fast-start rule.
    # Keep later batches modest as well: with one-line semantic clauses, a 4k batch can contain well
    # over 100 subtitle events, which makes an LLM positional shift much more likely. 1.2k normally
    # holds a few dozen events while preserving progressive background throughput.
    replace_once(
        translator,
        "    private static final int GEMINI_MAX_BATCH_CHARS = 900;\n",
        "    private static final int GEMINI_MAX_BATCH_CHARS = 1_200;\n",
        "alignment-safe Gemini background batches",
    )

    # patch_autodub_timeline.py removed the per-batch Gemini delegate because v2.2 was blocking on
    # translateWholeTranscript(). Restore it now that translateBatch() uses the prepared full context.
    replace_once(
        translator,
        '''        String service = Settings.VOT_TRANSLATION_SERVICE.get();\n        if (service.equals(TRANSLATION_SERVICE_MY_MEMORY)) {''',
        '''        if (GeminiTranslator.isEnabled()) {\n            return GeminiTranslator.translateBatch(videoId, segments, targetLang);\n        }\n        String service = Settings.VOT_TRANSLATION_SERVICE.get();\n        if (service.equals(TRANSLATION_SERVICE_MY_MEMORY)) {''',
        "restore progressive Gemini batch delegate",
    )

    print("Quick-start full-context Gemini integration complete")


if __name__ == "__main__":
    main()
