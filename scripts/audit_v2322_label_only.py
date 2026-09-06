#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2322_label_only.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
player_hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
translator = pkg / "TranscriptTranslator.java"
bottom_sheet = pkg / "VotBottomSheet.java"
sheet = study / "SpanishStudySheet.java"
controller = study / "SpanishStudyController.java"
speaker = study / "LocalSpeakerDiarizer.java"

texts = {p: p.read_text(encoding="utf-8") for p in (player_hook, translator, bottom_sheet, sheet, controller, speaker)}

# Runtime control invariant: no v2.32 direct PCM path is present at all.
if "onPcmBuffer" in texts[player_hook] or "AudioTrack ByteBuffer write method" in texts[player_hook]:
    raise RuntimeError("direct PCM bytecode hook unexpectedly present")
if "onPcmBuffer" in texts[speaker] or "ThreadPoolExecutor" in texts[speaker] or "direct-exoplayer-pcm" in texts[speaker]:
    raise RuntimeError("v2.32 direct PCM diarizer unexpectedly present")
if (study / "PcmSpeakerFeature.java").exists():
    raise RuntimeError("v2.32 PCM feature helper unexpectedly present")

# Preserve the exact known-good Morphe/v2.31 translation architecture.
if "OPENROUTER_MAX_BATCH_CHARS = 1_500" not in texts[translator]:
    raise RuntimeError("1500-char OpenRouter packet invariant changed")
if "OPENROUTER_FIRST_BATCH_CHARS = 350" not in texts[translator]:
    raise RuntimeError("350-char first OpenRouter packet invariant changed")
if "Use natural conversational spoken Spanish suitable for dubbing and subtitles" not in texts[translator]:
    raise RuntimeError("v2.31 conversational prompt missing")
if "Do not code-switch into English" in texts[translator]:
    raise RuntimeError("v2.32 anti-code-switch change unexpectedly present")

# This release intentionally changes only visible naming/version text after v2.31.
if 'makeValueRow(context, fg, "Spanish Dub Study")' not in texts[bottom_sheet]:
    raise RuntimeError("clean VOT label missing")
if '((TextView) studyRow.getTag()).setText("");' not in texts[bottom_sheet]:
    raise RuntimeError("VOT subtitle text not cleared")
if 'title.setText("Spanish Dub Study");' not in texts[sheet]:
    raise RuntimeError("sheet title not simplified")
if "Spanish Dub Study v2.32.2 control diagnostics" not in texts[controller]:
    raise RuntimeError("control diagnostics marker missing")

# v2.31 speaker backend must still be the Visualizer-latched implementation.
if "android.media.audiofx.Visualizer" not in texts[speaker]:
    raise RuntimeError("known-good v2.31 speaker implementation not retained")

print("v2.32.2 label-only control audit passed")
