#!/usr/bin/env python3
"""Audit v2.27: stock Morphe VOT core with only passive subtitle hooks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise RuntimeError(f"forbidden {label}: {needle}")
    print("ok:", label)


def assert_git_clean(root: Path, rel: str, label: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(root), "diff", "--exit-code", "--", rel],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    if result.returncode != 0:
        raise RuntimeError(f"{label} changed from stock Morphe:\n{result.stdout}")
    print("ok:", label, "is byte-for-byte stock checkout")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2270_stock_morphe_subtitles.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()

    pkg_rel = "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    assert_git_clean(root, f"{pkg_rel}/TranscriptTranslator.java", "TranscriptTranslator")
    assert_git_clean(root, f"{pkg_rel}/TtsEngine.java", "TtsEngine")
    assert_git_clean(root, f"{pkg_rel}/TtsPrefetcher.java", "TtsPrefetcher")
    assert_git_clean(root, f"{pkg_rel}/TranscriptSegment.java", "TranscriptSegment")

    pkg = root / pkg_rel
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    fetcher = (pkg / "TranscriptFetcher.java").read_text(encoding="utf-8")
    controller = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java").read_text(encoding="utf-8")
    overlay = (root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
    study_dir = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"

    require(vot, "SpanishStudyController.onVideoTimeChanged(timeMs);", "playhead observer")
    require(vot, "SpanishStudyController.onTranscriptUpdated(updated);", "progressive transcript observer")
    require(vot, "getActiveSpokenIndexForStudy()", "read-only active speech getter")
    require(vot, "getTtsEndVideoTimeMsForStudy()", "read-only TTS end getter")

    require(fetcher, "return mergeIntoSentences(lines);", "stock sentence merge return")
    forbid(fetcher, "splitIntoStudyClauses", "study clause splitting absent")
    forbid(fetcher, "SemanticClauseSplitter", "semantic resegmentation absent")
    forbid(fetcher, "SourceCaptionTimingStore", "custom source timing absent")

    require(controller, "translationPipeline=stock-morphe-unmodified", "stock translation diagnostic")
    require(controller, "translationCustomRecovery=none", "no custom recovery diagnostic")
    require(controller, "ttsArchitecture=stock-morphe-unmodified", "stock TTS diagnostic")
    require(controller, "speakerBackend=disabled", "speaker backend disabled")
    require(controller, "speakerRequests=0", "zero remote speaker requests")

    require(overlay, "BilingualCardPolicy.build", "lossless paired pagination")
    require(overlay, "SubtitleLinePolicy.format", "two-line display formatting")
    require(overlay, "getActiveSpokenIndexForStudy", "keep spoken segment visible")
    require(overlay, "getTtsEndVideoTimeMsForStudy", "follow stock TTS overrun window")
    forbid(overlay, "SpeakerAssignmentStore", "no speaker display dependency")

    forbidden_files = [
        "GeminiSpeakerDiarizationSidecar.java",
        "SpeakerAssignmentStore.java",
        "SpeakerNamePolicy.java",
    ]
    for name in forbidden_files:
        if study_dir.joinpath(name).exists():
            raise RuntimeError(f"speaker experiment unexpectedly packaged: {name}")
        print("ok: speaker experiment absent:", name)

    print("v2.27 stock Morphe audit passed")


if __name__ == "__main__":
    main()
