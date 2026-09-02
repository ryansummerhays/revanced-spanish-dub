#!/usr/bin/env python3
"""Wire paired natural-phrase English/Spanish subtitles into Morphe and suppress duplicate auto-CC."""
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
        "import app.morphe.extension.shared.Utils;\nimport app.spanishstudy.vot.SemanticClauseSplitter;\nimport app.spanishstudy.vot.SourceCaptionTimingStore;\nimport app.spanishstudy.vot.SpanishStudyController;\n",
        "TranscriptFetcher study imports",
    )

    # Preserve JSON3's inner caption offsets before Morphe concatenates each event to one string.
    # These are the closest thing the caption track gives us to actual source-word timing.
    replace_once(
        fetcher,
        '''        JSONArray events = root.optJSONArray("events");\n        if (events == null) return lines;\n\n        for (int i = 0, eventsLength = events.length(); i < eventsLength; i++) {''',
        '''        JSONArray events = root.optJSONArray("events");\n        if (events == null) return lines;\n        SourceCaptionTimingStore.beginTranscript();\n\n        for (int i = 0, eventsLength = events.length(); i < eventsLength; i++) {''',
        "reset fine-grained source timing for caption track",
    )

    replace_once(
        fetcher,
        '''            StringBuilder text = new StringBuilder();\n            for (int j = 0, segsLength = segs.length(); j < segsLength; j++) {\n                text.append(segs.getJSONObject(j).optString("utf8", ""));\n            }''',
        '''            StringBuilder text = new StringBuilder();\n            final int segsLength = segs.length();\n            for (int j = 0; j < segsLength; j++) {\n                JSONObject inner = segs.getJSONObject(j);\n                String utf8 = inner.optString("utf8", "");\n                text.append(utf8);\n\n                // tOffsetMs is relative to the event start. Some manual tracks omit it; in that\n                // case distribute only inside this one small JSON3 event rather than across the\n                // eventual merged sentence. This is still a much tighter fallback.\n                long offset = inner.has("tOffsetMs")\n                        ? Math.max(0L, inner.optLong("tOffsetMs", 0L))\n                        : Math.round(durationMs * (j / (double) Math.max(1, segsLength)));\n                long nextOffset;\n                if (j + 1 < segsLength) {\n                    JSONObject nextInner = segs.getJSONObject(j + 1);\n                    nextOffset = nextInner.has("tOffsetMs")\n                            ? Math.max(offset + 1L, nextInner.optLong("tOffsetMs", offset + 1L))\n                            : Math.round(durationMs * ((j + 1) / (double) Math.max(1, segsLength)));\n                } else {\n                    nextOffset = durationMs;\n                }\n                nextOffset = Math.max(offset + 1L, Math.min(durationMs, nextOffset));\n                SourceCaptionTimingStore.addTimedChunk(\n                        startMs + offset, startMs + nextOffset, utf8);\n            }''',
        "retain JSON3 inner-segment timing",
    )

    replace_once(
        fetcher,
        "        return mergeIntoSentences(lines);\n",
        "        return splitIntoStudyClauses(mergeIntoSentences(lines));\n",
        "split merged source transcript into natural semantic phrases",
    )

    clause_method = r'''
    /**
     * Converts source sentences into paired natural-phrase subtitle events.
     *
     * Boundary priority is now: actual JSON3 source-word timing -> natural punctuation/meaning ->
     * conservative character-proportional timing only when the track lacks reliable fine timing.
     * Fast tiny pieces are merged again rather than creating subtitle flashes or chopped TTS.
     */
    private static List<TranscriptSegment> splitIntoStudyClauses(List<TranscriptSegment> sentences) {
        final long STANDARD_MIN_EVENT_MS = 833;
        final long HARD_MEASURED_MIN_EVENT_MS = 550;
        List<TranscriptSegment> out = new ArrayList<>();
        for (TranscriptSegment sentence : sentences) {
            List<String> pieces = new ArrayList<>(SemanticClauseSplitter.split(sentence.text));
            if (pieces.size() <= 1) {
                out.add(sentence);
                continue;
            }

            final long span = Math.max(1L, sentence.endMs - sentence.startMs);
            final int maxReadablePieces = Math.max(1, (int) (span / STANDARD_MIN_EVENT_MS));

            while (pieces.size() > maxReadablePieces && pieces.size() > 1) {
                mergeLeastCostAdjacent(pieces);
            }

            // If actual source-word timing says one resulting phrase is still only a blink, merge it
            // with a neighbor. Recompute after every merge because the textual word boundary changes.
            long[] measuredEnds = SourceCaptionTimingStore.phraseEndTimes(
                    sentence.startMs, sentence.endMs, sentence.text, pieces);
            while (measuredEnds != null && pieces.size() > 1) {
                int tooShort = firstTooShort(sentence.startMs, measuredEnds, HARD_MEASURED_MIN_EVENT_MS);
                if (tooShort < 0) break;
                mergeAround(pieces, tooShort);
                measuredEnds = SourceCaptionTimingStore.phraseEndTimes(
                        sentence.startMs, sentence.endMs, sentence.text, pieces);
            }

            if (pieces.size() <= 1) {
                out.add(sentence);
                continue;
            }

            if (measuredEnds != null && measuredEnds.length == pieces.size()) {
                long cursor = sentence.startMs;
                for (int i = 0; i < pieces.size(); i++) {
                    long pieceEnd = i == pieces.size() - 1
                            ? sentence.endMs : Math.max(cursor + 1L, measuredEnds[i]);
                    pieceEnd = Math.min(sentence.endMs, pieceEnd);
                    out.add(new TranscriptSegment(cursor, pieceEnd, pieces.get(i), sentence.lang));
                    cursor = pieceEnd;
                }
                continue;
            }

            // Fallback for caption tracks without usable inner offsets.
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

    private static int firstTooShort(long sentenceStartMs, long[] ends, long minMs) {
        long cursor = sentenceStartMs;
        for (int i = 0; i < ends.length; i++) {
            if (ends[i] - cursor < minMs) return i;
            cursor = ends[i];
        }
        return -1;
    }

    private static void mergeAround(List<String> pieces, int index) {
        if (pieces.size() <= 1) return;
        int left;
        if (index <= 0) left = 0;
        else if (index >= pieces.size() - 1) left = pieces.size() - 2;
        else {
            int mergeLeft = pieces.get(index - 1).length() + 1 + pieces.get(index).length();
            int mergeRight = pieces.get(index).length() + 1 + pieces.get(index + 1).length();
            left = mergeLeft <= mergeRight ? index - 1 : index;
        }
        mergeAt(pieces, left);
    }

    private static void mergeLeastCostAdjacent(List<String> pieces) {
        int bestAt = 0;
        int bestCombinedLength = Integer.MAX_VALUE;
        for (int i = 0; i + 1 < pieces.size(); i++) {
            int combined = pieces.get(i).length() + 1 + pieces.get(i + 1).length();
            if (combined < bestCombinedLength) {
                bestCombinedLength = combined;
                bestAt = i;
            }
        }
        mergeAt(pieces, bestAt);
    }

    private static void mergeAt(List<String> pieces, int left) {
        String merged = (pieces.get(left) + " " + pieces.get(left + 1))
                .replaceAll("\\s+", " ").trim();
        pieces.set(left, merged);
        pieces.remove(left + 1);
    }

'''
    replace_once(
        fetcher,
        "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        clause_method + "    private static boolean detectPunctuation(List<TranscriptSegment> lines) {\n",
        "add source-word-aware natural phrase timing mapper",
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

    print("Source-word-timed natural paired bilingual subtitle integration complete")


if __name__ == "__main__":
    main()
