#!/usr/bin/env python3
"""Make source/TTS segmentation follow natural speech pauses instead of width cutoffs.

Applied after apply_overlay.py and before patch_bilingual_subtitles.py. The baseline Morphe merger is
excellent at joining raw caption rows into sentences, but our earlier latency tuning reduced the hard
character caps so aggressively that it could flush in the middle of a thought. This patch restores
longer safety caps and adds punctuation+caption-gap cues for comma/semicolon/colon/dash pauses.
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
        raise SystemExit("usage: patch_natural_speech_boundaries.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    if not fetcher.is_file():
        raise RuntimeError(f"Required source missing: {fetcher}")

    # apply_overlay.py lowers these to 180/120 for quick re-sync. That made width itself act like a
    # speech boundary. Keep length only as an emergency fuse; punctuation and acoustic-caption gaps
    # should normally decide where an utterance ends.
    replace_once(
        fetcher,
        "    private static final int MAX_SENTENCE_CHARS = 180;\n",
        "    private static final int MAX_SENTENCE_CHARS = 360;\n",
        "restore long punctuated sentence safety cap",
    )
    replace_once(
        fetcher,
        "    private static final int MAX_UNPUNCTUATED_CHARS = 120;\n",
        "    private static final int MAX_UNPUNCTUATED_CHARS = 220;\n",
        "restore long unpunctuated safety cap",
    )

    replace_once(
        fetcher,
        '''                    flush = endsSentence(text)\n                            || text.length() >= MAX_SENTENCE_CHARS\n                            || (gap > MAX_SENTENCE_GAP_MS && text.length() > 80);''',
        '''                    flush = endsSentence(text)\n                            || endsNaturalPhrasePause(text, gap)\n                            || text.length() >= MAX_SENTENCE_CHARS\n                            || (gap > MAX_SENTENCE_GAP_MS && text.length() > 80);''',
        "use punctuation plus real caption gap as a natural phrase cue",
    )

    helper = r'''
    /**
     * Mid-sentence punctuation is only promoted to an utterance boundary when the source captions
     * also expose a small timing gap there. This is a useful proxy for prosody: comma/semicolon/
     * colon/dash plus a real pause is much more likely to be a place a human speaker would breathe
     * than an arbitrary character count. Terminal punctuation is handled by endsSentence().
     */
    private static boolean endsNaturalPhrasePause(CharSequence text, long gapMs) {
        if (text.length() == 0 || gapMs < 90) return false;
        int i = text.length() - 1;
        while (i >= 0 && Character.isWhitespace(text.charAt(i))) i--;
        if (i < 0) return false;
        final char c = text.charAt(i);
        if (c == ';' || c == ':' || c == '—' || c == '–') return gapMs >= 90;
        if (c == ',') return gapMs >= 130;
        return false;
    }

'''
    replace_once(
        fetcher,
        "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        helper + "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        "add natural prosodic pause helper",
    )

    print("Natural speech-boundary segmentation complete")


if __name__ == "__main__":
    main()
