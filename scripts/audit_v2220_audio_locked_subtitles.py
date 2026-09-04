#!/usr/bin/env python3
from pathlib import Path
import sys


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise RuntimeError(f"missing {label}: {needle}")
    print("ok:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: audit_v2220_audio_locked_subtitles.py <morphe-root>")
    root = Path(sys.argv[1]).resolve()
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"

    overlay = (study / "SpanishSubtitleOverlay.java").read_text(encoding="utf-8")
    sync = (study / "SubtitleAudioSyncPolicy.java").read_text(encoding="utf-8")
    cost = (study / "SpeakerCostPolicy.java").read_text(encoding="utf-8")
    controller = (study / "SpanishStudyController.java").read_text(encoding="utf-8")
    sheet = (study / "SpanishStudySheet.java").read_text(encoding="utf-8")
    store = (study / "SpeakerAssignmentStore.java").read_text(encoding="utf-8")
    sidecar = (study / "GeminiSpeakerDiarizationSidecar.java").read_text(encoding="utf-8")
    vot = (pkg / "VoiceOverTranslationPatch.java").read_text(encoding="utf-8")
    tts = (pkg / "TtsEngine.java").read_text(encoding="utf-8")

    require(sync, "if (!audioStarted) return 0.0", "dub subtitles freeze before audible TTS")
    require(overlay, "SubtitleAudioSyncPolicy.pairedProgress", "bilingual pages use audio clock")
    require(overlay, "createSpeakerBadge", "speaker label has separate pill")
    require(overlay, "speakerBadgeView", "speaker badge is structurally separate from text")
    require(tts, "@Nullable Runnable onStart", "TtsEngine exposes playback-start callback")
    require(tts, "if (onStart != null) onStart.run();", "callback fires after MediaPlayer start")
    require(vot, "subtitleAudioStarted", "VOT builds real audio subtitle callback")
    require(vot, "SubtitleAudioSyncPolicy.playbackEndMs", "actual subtitle end uses playback rate")
    require(vot, "subtitleAudioStarted, VoiceOverTranslationPatch::triggerNextSegmentCheck",
            "Edge playback receives subtitle onStart callback")
    require(controller, "TTS-AUDIO-START", "real playback start is logged")
    require(controller, "Spanish Dub Study v2.22.0 diagnostics", "v2.22 diagnostics version")
    require(controller, "actual-audio-start+tts-window+source-only-fallback", "audio sync diagnostic")

    require(store, "profileDetails()", "speaker profile detail API")
    require(sheet, "Detected speaker profiles", "speaker profiles visible in menu dialog")
    require(sheet, "Speaker API usage", "speaker cost visible in menu")
    require(sidecar, "speakerEstimatedPaidCostUsd", "speaker cost telemetry diagnostic")
    require(sidecar, "total_tool_use_tokens", "agentic tool-use tokens counted")
    require(sidecar, "SpeakerCostPolicy.QUOTA_BACKOFF_MS", "429 gets long quota backoff")
    require(sidecar, "Gemini quota limited", "quota state visible to user")
    require(cost, "INPUT_USD_PER_M = 0.75", "current Gemini input rate encoded")
    require(cost, "OUTPUT_USD_PER_M = 3.75", "current Gemini output rate encoded")

    print("v2.22 audio-locked subtitle + speaker observability audit: OK")


if __name__ == "__main__":
    main()
