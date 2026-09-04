#!/usr/bin/env python3
from pathlib import Path
import sys


def need(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")
    print("ok:", label)


def forbid(text: str, needle: str, label: str) -> None:
    if needle in text:
        raise SystemExit(f"forbidden {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2210_source_subtitle_sync.py <morphe-root>")
    root = Path(sys.argv[1])
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

    fetcher = (pkg / "TranscriptFetcher.java").read_text()
    overlay = (study / "SpanishSubtitleOverlay.java").read_text()
    controller = (study / "SpanishStudyController.java").read_text()
    sidecar = (study / "GeminiSpeakerDiarizationSidecar.java").read_text()
    source_policy = (study / "CaptionTrackPreference.java").read_text()
    sync_policy = (study / "SubtitleSyncPolicy.java").read_text()

    need(source_policy, 'if ("en".equals(lang)) return nonGemini ? 0 : 10;',
         "English source outranks dub target")
    need(fetcher, "CaptionTrackPreference.rank", "caption selector uses tested source policy")
    need(fetcher, 'SpanishStudyDiagnostics.record("CAPTION-TRACK"', "selected track diagnostics")
    forbid(fetcher, "if (targetLangUrl != null) return targetLangUrl;",
           "old target-language-first selector removed")

    need(sync_policy, "BACKWARD_SEEK_RESET_MS = 1_000L", "real backward seek threshold")
    need(sync_policy, "Math.max(clamp(previousProgress), candidate)", "monotonic progress rule")
    need(overlay, "progressFloors", "per-segment progress floors")
    need(overlay, "SubtitleSyncPolicy.isBackwardSeek", "backward seek detection")
    need(overlay, "SubtitleSyncPolicy.monotonicProgress", "late TTS cannot rewind pages")
    need(overlay, 'SpanishStudyDiagnostics.record("SUBTITLE-SYNC"', "subtitle rewind diagnostics")
    need(overlay, "ShownPage sourcePage", "English and Spanish share one normalized progress")

    need(controller, "Spanish Dub Study v2.21.0 diagnostics", "v2.21 diagnostics")
    need(controller, "sourceTrackPolicy=english-first-non-gemini+target-fallback", "source policy diagnostics")
    need(controller, "subtitlePageDirection=monotonic-unless-backward-seek", "subtitle direction diagnostics")
    need(controller, "englishSubtitlesEnabled=", "English subtitle preference telemetry")
    need(controller, "spanishSubtitlesEnabled=", "Spanish subtitle preference telemetry")

    need(sidecar, "READ_TIMEOUT_MS = 45_000", "longer agentic speaker timeout")
    need(sidecar, '.put("thinking_level", "low")', "low speaker thinking latency")
    need(sidecar, "Math.max(1200, segments.size() * 80)", "larger speaker JSON allowance")
    forbid(sidecar, '.put("temperature", 0.0)', "unsupported Gemini 3.7 sampling parameter removed")

    print("v2.21 source/subtitle/speaker audit passed")


if __name__ == "__main__":
    main()
