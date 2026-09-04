#!/usr/bin/env python3
from pathlib import Path
import sys


def rep(path, old, new, label):
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected 1 anchor, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched:", label)


def main():
    root = Path(sys.argv[1]).resolve()
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    rep(vot, "    static synchronized void noteEdgeSynthesisSuccess() {",
             "    public static synchronized void noteEdgeSynthesisSuccess() {", "public Edge success hook")
    rep(vot, "    static synchronized void noteEdgeSynthesisFailure(String source) {",
             "    public static synchronized void noteEdgeSynthesisFailure(String source) {", "public Edge failure hook")
    rep(vot, "    static synchronized boolean isEdgeFallbackActive() {",
             "    public static synchronized boolean isEdgeFallbackActive() {", "public Edge circuit query")

if __name__ == "__main__":
    main()
