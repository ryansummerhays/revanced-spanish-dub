#!/usr/bin/env python3
from pathlib import Path
import sys


def req(text, needle, label):
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2221_speaker_oneshot.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    sidecar = (study / "GeminiSpeakerDiarizationSidecar.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    req(sidecar, "analysisComplete", "one-shot completion latch")
    req(sidecar, "MAX_EVENTS_PER_WINDOW = 1200", "full caption timeline capacity")
    req(sidecar, "READ_TIMEOUT_MS = 120_000", "full-video request timeout")
    req(sidecar, "CAPTION EVENTS ACROSS FULL VIDEO", "full-video speaker prompt")
    req(sidecar, "mapping full video", "menu in-flight status")
    req(sidecar, "· mapped", "menu completion status")
    req(controller, "speakerAnalysisMode=one-shot-full-video-caption-map", "diagnostic architecture")
    print("v2.22 one-shot speaker map audit: OK")


if __name__ == "__main__":
    main()
