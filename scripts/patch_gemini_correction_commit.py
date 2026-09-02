#!/usr/bin/env python3
"""Do not display a Gemini ASR correction until its paired translation survives validation.

Context-aware correction is useful for niche jargon, but correctedSource is still model output. Keep it
provisional until the exact source echo and Spanish line pass deterministic checks; if the independent
back-translation later rejects that Spanish, roll the English correction back as well.
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
        raise SystemExit("usage: patch_gemini_correction_commit.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    gemini = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/GeminiTranslator.java"
    if not gemini.is_file():
        raise RuntimeError(f"Required source missing: {gemini}")

    replace_once(
        gemini,
        '''            // Display correction is side data only; the store independently rejects broad rewrites.\n            TranscriptCorrectionStore.put(canonicalSegment.startMs, canonicalSegment.endMs,\n                    canonicalSegment.text, correctedSource);\n            String acceptedSource = TranscriptCorrectionStore.get(\n                    canonicalSegment.startMs, canonicalSegment.endMs, canonicalSegment.text);\n            intendedSourceById.put(id, acceptedSource);\n\n            try {\n                TranslationAlignmentGuard.validate(\n                        canonicalSegment.text,\n                        sourceEcho,\n                        translation,\n                        neighboringSourceTexts(segments, id));\n                translationsById.put(id, translation);\n            } catch (IllegalArgumentException badLine) {''',
        '''            // correctedSource remains provisional until the exact source echo and Spanish\n            // proposal both pass deterministic validation. A model cannot change the displayed\n            // English caption merely by returning a plausible-looking correction.\n            intendedSourceById.put(id, canonicalSegment.text);\n            try {\n                TranslationAlignmentGuard.validate(\n                        canonicalSegment.text,\n                        sourceEcho,\n                        translation,\n                        neighboringSourceTexts(segments, id));\n                TranscriptCorrectionStore.put(canonicalSegment.startMs, canonicalSegment.endMs,\n                        canonicalSegment.text, correctedSource);\n                String acceptedSource = TranscriptCorrectionStore.get(\n                        canonicalSegment.startMs, canonicalSegment.endMs, canonicalSegment.text);\n                intendedSourceById.put(id, acceptedSource);\n                translationsById.put(id, translation);\n            } catch (IllegalArgumentException badLine) {''',
        "defer ASR correction until deterministic translation validation",
    )

    replace_once(
        gemini,
        '''                            Logger.printDebug(() -> "Gemini translation failed independent grounding check: "\n                                    + rejectedId);\n                            translationsById.put(id, null);''',
        '''                            Logger.printDebug(() -> "Gemini translation failed independent grounding check: "\n                                    + rejectedId);\n                            translationsById.put(id, null);\n                            TranscriptSegment rejectedSource = segments.get(id);\n                            TranscriptCorrectionStore.remove(\n                                    rejectedSource.startMs, rejectedSource.endMs);\n                            intendedSourceById.put(id, rejectedSource.text);''',
        "roll back ASR correction when independent grounding fails",
    )

    print("Grounded Gemini correction commit integration complete")


if __name__ == "__main__":
    main()
