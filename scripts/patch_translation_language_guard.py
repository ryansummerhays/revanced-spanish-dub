#!/usr/bin/env python3
"""Prevent untranslated English text from being tagged/spoken as Spanish.

A translation provider can occasionally return the original English text. Morphe's generic
applyBatch() normally labels every returned string with the target language anyway, which causes
English to be sent through a Spanish TTS voice. This patch validates each Spanish result against its
exact English source before it is allowed to replace the source segment.

If a result is unsafe, v2.3.1 performs one line-preserving Google rescue translation immediately on
the translation worker thread. Only if that rescue is also unsafe do we leave the original segment
in place. This makes brief Spanish/audio dropouts much less likely without ever intentionally
speaking English through the Spanish voice.
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
        raise SystemExit("usage: patch_translation_language_guard.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    if not translator.is_file():
        raise RuntimeError(f"Required source missing: {translator}")

    replace_once(
        translator,
        "import app.spanishstudy.vot.GeminiTranslator;\n",
        "import app.spanishstudy.vot.GeminiTranslator;\nimport app.spanishstudy.vot.TranslationAlignmentGuard;\n",
        "translation language guard import",
    )

    replace_once(
        translator,
        '''        for (int j = 0; j < limit; j++) {\n            TranscriptSegment orig = batch.get(j);\n            target.set(offset + j, new TranscriptSegment(\n                    orig.startMs, orig.endMs, translated.get(j), lang));\n        }''',
        '''        for (int j = 0; j < limit; j++) {\n            TranscriptSegment orig = batch.get(j);\n            String translatedText = translated.get(j);\n            if (lang != null && lang.toLowerCase(Locale.ROOT).startsWith("es")\n                    && !TranslationAlignmentGuard.isSafeSpanishTranslation(orig.text, translatedText)) {\n                final int rejectedIndex = offset + j;\n                Logger.printDebug(() -> "Rejected English/untranslated text from Spanish slot; attempting rescue: "\n                        + rejectedIndex);\n\n                // A whole Gemini batch may have fallen back cleanly except for one stubborn line,\n                // or a generic provider may briefly return the source unchanged. Retry only this\n                // exact immutable source event with Morphe's line-preserving Google translator.\n                // This code already runs off the main thread inside TranscriptTranslator.translate().\n                String rescuedText = null;\n                try {\n                    List<String> rescue = TextTranslator.translate(\n                            Collections.singletonList(orig.text), lang);\n                    if (rescue != null && !rescue.isEmpty()) {\n                        String candidate = rescue.get(0);\n                        if (TranslationAlignmentGuard.isSafeSpanishTranslation(orig.text, candidate)) {\n                            rescuedText = candidate;\n                        }\n                    }\n                } catch (Exception rescueError) {\n                    Logger.printDebug(() -> "Spanish rescue translation failed for slot: "\n                            + rejectedIndex, rescueError);\n                }\n\n                if (rescuedText == null || rescuedText.isBlank()) {\n                    Logger.printDebug(() -> "Spanish slot remains untranslated after rescue: "\n                            + rejectedIndex);\n                    // Leave the original language in place. VoiceOverTranslationPatch refuses to\n                    // speak it with a Spanish voice, and the bilingual overlay hides that slot.\n                    continue;\n                }\n                translatedText = rescuedText;\n            }\n            target.set(offset + j, new TranscriptSegment(\n                    orig.startMs, orig.endMs, translatedText, lang));\n        }''',
        "reject or rescue English text before Spanish tagging/TTS",
    )

    print("Spanish translation language safety/rescue guard complete")


if __name__ == "__main__":
    main()
