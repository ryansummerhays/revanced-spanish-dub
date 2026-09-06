#!/usr/bin/env python3
"""v2.32.2: add only safe UI/subtitle/prompt improvements on top of known-good v2.31 runtime."""
from __future__ import annotations

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
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v2322_v231_safe_features.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    subtitle = study / "SpanishSubtitleOverlay.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    bottom_sheet = pkg / "VotBottomSheet.java"

    for path in (vot, translator, subtitle, controller, sheet, bottom_sheet):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # No speaker classes and no bytecode patch files are touched in this release.
    # The v2.31 Visualizer-latched speaker implementation remains byte-for-byte as produced by
    # the v2.28 + v2.30 chain.

    rep(
        vot,
        "    /** Actual Edge MediaPlayer progress in [0,1], or -1 before playback has started. */\n",
        "    /** Whether the currently selected VOT voice resolves to Edge rather than System TTS. */\n"
        "    public static boolean isEdgeSelectedForStudy() {\n"
        "        Utils.verifyOnMainThread();\n"
        "        String voice = resolveVoice(resolveTargetLang());\n"
        "        return voice != null && !TTS_ENGINE_SYSTEM.equals(voice);\n"
        "    }\n\n"
        "    /** Actual Edge MediaPlayer progress in [0,1], or -1 before playback has started. */\n",
        "expose pre-playback Edge selection",
    )

    rep(
        subtitle,
        "        } else {\n"
        "            progress = SubtitlePagePolicy.progress(timeMs, windowStart, windowEnd);\n"
        "            clockSource = \"video\";\n"
        "        }\n",
        "        } else if (VoiceOverTranslationPatch.isTranslationActive()\n"
        "                && VoiceOverTranslationPatch.isEdgeSelectedForStudy()\n"
        "                && lastAudioProgressSegment != index) {\n"
        "            progress = 0.0;\n"
        "            clockSource = hasSpanish ? \"tts-pending\" : \"translation-pending\";\n"
        "        } else {\n"
        "            progress = SubtitlePagePolicy.progress(timeMs, windowStart, windowEnd);\n"
        "            clockSource = \"video\";\n"
        "        }\n",
        "hold subtitle page one before first Edge audio",
    )

    rep(
        translator,
        "Use natural conversational spoken Spanish suitable for dubbing and subtitles; prefer idiomatic phrasing over literal word-for-word translation while preserving meaning, names, tone, and line correspondence. Do not summarize or add information. ",
        "Use natural conversational spoken Spanish suitable for dubbing and subtitles; prefer idiomatic phrasing over literal word-for-word translation while preserving meaning, names, tone, and line correspondence. Do not code-switch into English except for proper nouns, branded names, titles, or source terms that intentionally need to remain in English. Do not summarize or add information. ",
        "discourage accidental English code-switching without packet changes",
    )

    rep(
        bottom_sheet,
        "        LinearLayout studyRow = makeValueRow(context, fg, \"Spanish study\");\n"
        "        ((TextView) studyRow.getTag()).setText(\"Subtitles · local speakers · deep diagnostics\");\n",
        "        LinearLayout studyRow = makeValueRow(context, fg, \"Spanish Dub Study\");\n"
        "        ((TextView) studyRow.getTag()).setText(\"\");\n",
        "simplify VOT study entry",
    )
    rep(sheet, 'title.setText("Spanish study");', 'title.setText("Spanish Dub Study");',
        "rename custom settings sheet")

    rep(controller,
        'report.append("Spanish Dub Study v2.31.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.2 diagnostics\\n");',
        "update diagnostics version")
    rep(controller,
        'report.append("translationPromptStyle=natural-conversational-spoken-target-no-packet-change\\n");',
        'report.append("translationPromptStyle=natural-conversational-spoken-target+anti-code-switch-no-packet-change\\n");',
        "report anti-code-switch prompt")
    rep(controller,
        'report.append("subtitleClock=edge-mediaplayer+video-fallback+monotonic-audio-handoff\\n");',
        'report.append("subtitleClock=edge-mediaplayer+pre-tts-hold+video-fallback+monotonic-audio-handoff\\n");',
        "report pre-TTS subtitle hold")

    print("v2.32.2 v2.31-safe feature patch complete")


if __name__ == "__main__":
    main()
