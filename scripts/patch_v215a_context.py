#!/usr/bin/env python3
"""v2.15.0: realtime OpenRouter microbatches, video-specific raw-caption context, provenance, and UI cleanup."""
from pathlib import Path
import re
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def insert_after(path: Path, anchor: str, addition: str, label: str) -> None:
    rep(path, anchor, anchor + addition, label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v215_realtime_context.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    fetcher = pkg / "TranscriptFetcher.java"
    translator = pkg / "TranscriptTranslator.java"
    vot = pkg / "VoiceOverTranslationPatch.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    for p in (fetcher, translator, vot, controller, sheet):
        if not p.is_file():
            raise RuntimeError(f"missing required source: {p}")

    # 1) Preserve raw pre-parser English and video metadata as context already available locally.
    insert_after(fetcher,
                 "import app.spanishstudy.vot.SourceCaptionTimingStore;\n",
                 "import app.spanishstudy.vot.CaptionTextRepair;\n"
                 "import app.spanishstudy.vot.VideoTranslationContext;\n",
                 "import v2.15 caption/context helpers")

    rep(fetcher,
        "    private static List<TranscriptSegment> fetchEnglishSegments(String videoId) {\n",
        "    private static List<TranscriptSegment> fetchEnglishSegments(String videoId) {\n"
        "        VideoTranslationContext.beginCaptionLoad(videoId);\n",
        "reset raw-caption translation context before every caption load")

    metadata_anchor = '''                GeminiTranslator.prepareVideoMetadata(
                        videoId,
                        details.optString("title", ""),
                        details.optString("author", ""),
                        subjectDetails.toString());'''
    metadata_new = '''                VideoTranslationContext.prepareMetadata(
                        videoId,
                        details.optString("title", ""),
                        details.optString("author", ""),
                        subjectDetails.toString());
                GeminiTranslator.prepareVideoMetadata(
                        videoId,
                        details.optString("title", ""),
                        details.optString("author", ""),
                        subjectDetails.toString());'''
    rep(fetcher, metadata_anchor, metadata_new,
        "share existing YouTube metadata with all AI translation providers")

    rep(fetcher,
        '''            String textStr = text.toString()
''',
        '''            // Preserve the original YouTube event before marker stripping, punctuation cleanup,
            // sentence merging, or speech-unit planning. This raw evidence is useful for resolving
            // names/ASR fragments that a later parser may accidentally obscure.
            VideoTranslationContext.addRawCue(startMs, startMs + durationMs, text.toString());

            String textStr = text.toString()
''',
        "capture raw pre-parser caption cue")

    rep(fetcher,
        '''        List<SpeechUnitPlanner.Unit> plannedUnits = SpeechUnitPlanner.coalesce(rawUnits);
        if (plannedUnits.size() == out.size()) return out;
''',
        '''        CaptionTextRepair.RepairResult repaired = CaptionTextRepair.repair(rawUnits);
        rawUnits = new ArrayList<>(repaired.units());
        List<SpeechUnitPlanner.Unit> plannedUnits = SpeechUnitPlanner.coalesce(rawUnits);
''',
        "repair dangling caption fragments before speech-unit coalescing")

    rep(fetcher,
        '''                + " speakerTurns=" + CaptionSpeakerTurnStore.count());''',
        '''                + " speakerTurns=" + CaptionSpeakerTurnStore.count()
                + " localTextRepairs=" + repaired.textRepairs()
                + " boundaryRepairs=" + repaired.boundaryMerges());''',
        "diagnose local caption repairs")

    print("v2.15a context/caption integration complete")


if __name__ == "__main__":
    main()
