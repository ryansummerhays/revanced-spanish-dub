#!/usr/bin/env python3
"""Wire paired semantic English/Spanish subtitles into Morphe and suppress duplicate auto-CC."""
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
        raise SystemExit("usage: patch_bilingual_subtitles.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    fetcher = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptFetcher.java"
    auto = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/AutoCaptionsPatch.java"

    for path in (fetcher, auto):
        if not path.is_file():
            raise RuntimeError(f"Required source file not found: {path}")

    replace_once(
        fetcher,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SemanticClauseSplitter;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "TranscriptFetcher study imports",
    )

    replace_once(
        fetcher,
        "        return mergeIntoSentences(lines);\n",
        "        return splitIntoStudyClauses(mergeIntoSentences(lines));\n",
        "split merged source transcript into semantic clauses",
    )

    clause_method = r'''
    /**
     * Converts sentence-sized source segments into compact semantic subtitle events.
     *
     * Professional subtitle timing commonly avoids flashes shorter than about 5/6 second. We use
     * 833 ms as the preferred minimum whenever the source span has enough room for it. Fast source
     * speech can make that mathematically impossible; in that case semantic one-line boundaries and
     * exact source synchronization take precedence rather than abandoning the split and showing an
     * oversized multi-line sentence.
     *
     * The English/source timeline is authoritative. Translation receives this exact list 1:1, so
     * English and Spanish always switch on the same event boundary.
     */
    private static List<TranscriptSegment> splitIntoStudyClauses(List<TranscriptSegment> sentences) {
        final long STANDARD_MIN_EVENT_MS = 833;
        List<TranscriptSegment> out = new ArrayList<>();
        for (TranscriptSegment sentence : sentences) {
            List<String> pieces = SemanticClauseSplitter.split(sentence.text);
            if (pieces.size() <= 1) {
                out.add(sentence);
                continue;
            }

            final long span = Math.max(1L, sentence.endMs - sentence.startMs);
            final long minimumSlot = span >= pieces.size() * STANDARD_MIN_EVENT_MS
                    ? STANDARD_MIN_EVENT_MS : 1L;

            int totalWeight = 0;
            for (String piece : pieces) totalWeight += Math.max(1, piece.length());

            long cursor = sentence.startMs;
            int consumedWeight = 0;
            for (int i = 0; i < pieces.size(); i++) {
                String piece = pieces.get(i);
                consumedWeight += Math.max(1, piece.length());
                final int remaining = pieces.size() - i - 1;
                long pieceEnd;
                if (remaining == 0) {
                    pieceEnd = sentence.endMs;
                } else {
                    pieceEnd = sentence.startMs + Math.round(span
                            * (consumedWeight / (double) totalWeight));
                    final long minEnd = cursor + minimumSlot;
                    final long maxEnd = sentence.endMs - remaining * minimumSlot;
                    pieceEnd = Math.max(minEnd, Math.min(maxEnd, pieceEnd));
                }
                out.add(new TranscriptSegment(cursor, pieceEnd, piece, sentence.lang));
                cursor = pieceEnd;
            }
        }
        return out;
    }

'''
    replace_once(
        fetcher,
        "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        clause_method + "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        "add standards-based semantic clause timing mapper",
    )

    replace_once(
        fetcher,
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n",
        "        List<TranscriptSegment> segments = fetchEnglishSegments(videoId);\n        SpanishStudyController.onSourceTranscriptFetched(segments);\n",
        "publish English source transcript",
    )

    replace_once(
        auto,
        "import app.morphe.extension.youtube.settings.Settings;\n",
        "import app.morphe.extension.youtube.settings.Settings;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "AutoCaptions study import",
    )
    replace_once(
        auto,
        '''    public static boolean disableAutoCaptions(boolean original) {
        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        '''    public static boolean disableAutoCaptions(boolean original) {
        // The study overlay can render the original English transcript itself. Keep YouTube's
        // automatically-enabled CC off to prevent a duplicate caption line; a manual CC tap
        // after the guard window still works normally.
        if (SpanishStudyController.suppressNativeCaptions()) return true;

        // After the guard window (150ms), respect the user's manual CC button toggle.''',
        "suppress duplicate YouTube auto captions",
    )

    print("Professional paired bilingual subtitle integration complete")


if __name__ == "__main__":
    main()
