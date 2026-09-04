#!/usr/bin/env python3
from pathlib import Path
import sys


def main():
    root = Path(sys.argv[1]).resolve()
    path = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"
    text = path.read_text(encoding="utf-8")
    old = '''                if ((isOpenRouter || isGemini) && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }'''
    new = '''                if (isOpenRouter && firstBatchAfterReposition) {
                    capFirstBatch(batches, batchDone, index);
                }'''
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"v2.14 first-batch compat expected 1 anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched: normalize historical OpenRouter/Gemini first-batch condition")

if __name__ == "__main__":
    main()
