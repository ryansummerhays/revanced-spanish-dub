#!/usr/bin/env python3
"""Normalize one overly strict source-shape check in the v2.16 reconciliation script."""
from pathlib import Path
import sys


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "scripts/patch_v2160_morphe_core.py")
    text = path.read_text(encoding="utf-8")
    start_marker = "    # Stock stream callback receives a full result array whose unmatched slots still contain source\n"
    end_marker = "    # Retry a malformed/truncated OpenRouter response using Morphe's same batch, with bounded delay.\n"
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    replacement = r'''    # Stock stream callback receives a full result array whose unmatched slots still contain source
    # English. Publish only slots that actually changed, so subtitles never mistake placeholders for
    # completed Spanish while the same Morphe request is still streaming.
    rep_section(
        translator,
        "private static Consumer<List<String>> streamCallback(",
        "\n    @Nullable\n    private static List<String> translateBatchSafe",
        ''' + "'''" + r'''        return partial -> {
            List<TranscriptSegment> snap = new ArrayList<>(working);
            applyBatch(snap, batch, offset, partial, lang);
            mainHandler.post(() -> onUpdate.accept(snap));
        };''' + "'''" + r''',
        ''' + "'''" + r'''        return partial -> {
            List<TranscriptSegment> snap = new ArrayList<>(working);
            final int limit = Math.min(batch.size(), partial.size());
            for (int j = 0; j < limit; j++) {
                TranscriptSegment orig = batch.get(j);
                String raw = partial.get(j);
                if (raw == null || raw.equals(orig.text)) continue;
                String clean = DubTextSanitizer.cleanForSpeech(raw);
                if (clean == null) continue;
                snap.set(offset + j, new TranscriptSegment(orig.startMs, orig.endMs, clean, lang));
            }
            mainHandler.post(() -> onUpdate.accept(snap));
        };''' + "'''" + r''',
        "stream only actually translated OpenRouter slots")

'''
    path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
    print("normalized: stream callback source-shape check")


if __name__ == "__main__":
    main()
