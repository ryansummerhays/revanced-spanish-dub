#!/usr/bin/env python3
"""Make source/TTS segmentation follow natural speech pauses instead of width cutoffs.

Applied after apply_overlay.py and before patch_bilingual_subtitles.py. Earlier tuning aggressively
closed caption gaps and lowered character caps, which made the merger lose useful pause information
and then fall back to arbitrary width cuts. This patch preserves meaningful source pauses, restores
longer emergency caps, and uses punctuation+timing as the preferred phrase boundary signal.
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

    # The baseline closes every caption gap below 2.5 seconds before mergeIntoSentences() sees it.
    # That erases the 250-700 ms pause cues the merger itself later tries to use for ASR phrase
    # boundaries. Close only tiny timing jitter; preserve real breathing/phrase pauses.
    replace_once(
        fetcher,
        "    private static final long CLOSE_GAP_THRESHOLD_MS = 2_500;\n",
        "    private static final long CLOSE_GAP_THRESHOLD_MS = 120;\n",
        "preserve natural source pause timing",
    )

    # apply_overlay.py lowers these to 180/120 for quick re-sync. That made width itself act like a
    # speech boundary. Keep length only as an emergency fuse; punctuation and source pause timing
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
     * Mid-sentence punctuation is promoted to an utterance boundary only when the source captions
     * also expose a small timing gap there. This is a lightweight prosody proxy: punctuation plus
     * an actual pause is much more trustworthy than character count. Terminal punctuation remains
     * handled by endsSentence().
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
