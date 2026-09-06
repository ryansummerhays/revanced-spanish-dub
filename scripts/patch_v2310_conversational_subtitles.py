#!/usr/bin/env python3
"""v2.31: conversational, semantically paired subtitles without touching Morphe packetization."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v2310_conversational_subtitles.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    translator = pkg / "TranscriptTranslator.java"
    subtitle = study / "SpanishSubtitleOverlay.java"
    controller = study / "SpanishStudyController.java"
    for path in (translator, subtitle, controller):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # HARD RULE: the source segments, Morphe 1500/350 character packet budgets, packet ordering,
    # and request count policy are untouched. Only replace display helpers and add wording guidance
    # to the existing system prompt.
    for name in ("SubtitlePagePolicy.java", "BilingualCardPolicy.java"):
        src = repo / "overlay/v231/app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing v2.31 helper: {src}")
        shutil.copy2(src, study / name)
        print("copied:", name)

    # Ask the same request, with the same numbered lines and same packet size, for idiomatic spoken
    # language instead of literal phrasing. This adds only a few prompt tokens and does not change
    # segmentation/batching/cardinality.
    rep(
        translator,
        '                        + "The text may have misspellings or noise - translate the intent. "\n'
        '                        + "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.");',
        '                        + "The text may have misspellings or noise - translate the intent. "\n'
        '                        + "Use natural conversational spoken Spanish suitable for dubbing and subtitles; prefer idiomatic phrasing over literal word-for-word translation while preserving meaning, names, tone, and line correspondence. Do not summarize or add information. "\n'
        '                        + "Prefix each translation with its original line number and a colon. One line per number. Do not merge or skip.");',
        "request idiomatic conversational translation without changing packets",
    )

    # v2.23/v2.30 only synchronized page number. v2.31 PairPages carries the shared Spanish-audio
    # content boundaries themselves, so English and Spanish transition at the same semantic-progress
    # anchors instead of independently cutting both texts into N equal pieces.
    rep(
        subtitle,
        "            pageIndex = BilingualCardPolicy.pairIndex(pageCount, progress);\n",
        "            pageIndex = pair.index(progress);\n",
        "use shared bilingual content-progress boundaries",
    )

    rep(controller,
        'report.append("Spanish Dub Study v2.30.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.31.0 diagnostics\\n");',
        "update diagnostics version",
    )
    rep(controller,
        'report.append("speechSegmentation=stock-morphe-mergeIntoSentences\\n");',
        'report.append("speechSegmentation=stock-morphe-mergeIntoSentences-UNCHANGED\\n");\n'
        '        report.append("translationPacketization=stock-morphe-1500char+350char-first-UNCHANGED\\n");',
        "declare hard packetization invariant",
    )
    rep(controller,
        'report.append("translationPipeline=morphe-openrouter+char-budget+unique-slot-parser+mixed-language-guard\\n");',
        'report.append("translationPipeline=morphe-openrouter+native-packets+idiomatic-prompt+char-budget+unique-slot-parser+mixed-language-guard\\n");\n'
        '        report.append("translationPromptStyle=natural-conversational-spoken-target-no-packet-change\\n");',
        "report conversational prompt style",
    )
    rep(controller,
        'report.append("subtitleLayer=passive-lossless-pagination\\n");',
        'report.append("subtitleLayer=display-only-conversational-boundary-scoring\\n");',
        "report conversational display pagination",
    )
    rep(controller,
        'report.append("subtitleBilingualCardSync=shared-count+shared-index\\n");',
        'report.append("subtitleBilingualCardSync=spanish-audio-master+shared-content-progress-boundaries\\n");',
        "report semantic bilingual sync",
    )

    print("v2.31 conversational subtitle patch complete")


if __name__ == "__main__":
    main()
