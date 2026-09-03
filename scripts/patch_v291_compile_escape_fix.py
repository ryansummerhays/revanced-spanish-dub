#!/usr/bin/env python3
"""Correct the v2.9.1 generated Java URL-sanitizer regex before compilation."""
from pathlib import Path
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v291_compile_escape_fix.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    text = fetcher.read_text(encoding="utf-8")
    old = 'raw.replaceAll("https?://\\S+", "<url>")'
    new = 'raw.replaceAll("https?://[^ ]+", "<url>")'
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"v2.9.1 sanitizer compile fix: expected 1 anchor, found {count}")
    fetcher.write_text(text.replace(old, new, 1), encoding="utf-8")
    print("patched: v2.9.1 sanitizer compile escape")


if __name__ == "__main__":
    main()
