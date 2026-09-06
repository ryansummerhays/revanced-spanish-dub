#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2321_startup_safe.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
player_hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
speaker = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/LocalSpeakerDiarizer.java"
bottom_sheet = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VotBottomSheet.java"
subtitle = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishSubtitleOverlay.java"
translator = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/TranscriptTranslator.java"

texts = {p: p.read_text(encoding="utf-8") for p in (player_hook, controller, speaker, bottom_sheet, subtitle, translator)}

hook = texts[player_hook]
if "LocalSpeakerDiarizer;->onPcmBuffer" in hook or "AudioTrack ByteBuffer write method" in hook:
    raise RuntimeError("unsafe direct PCM bytecode hook still present")
if "setAudioTrack(Landroid/media/AudioTrack;)V" not in hook:
    raise RuntimeError("stock PlayerVolume AudioTrack hook missing")

if "Spanish Dub Study v2.32.1 diagnostics" not in texts[controller]:
    raise RuntimeError("v2.32.1 diagnostics version missing")
if "speakerBackend=direct-pcm-hook-suspended-startup-safe" not in texts[speaker]:
    raise RuntimeError("suspended speaker backend marker missing")
if 'boolean captureAvailable = false;' not in texts[speaker]:
    raise RuntimeError("speaker capture should be hard-disabled")
if 'makeValueRow(context, fg, "Spanish Dub Study")' not in texts[bottom_sheet]:
    raise RuntimeError("clean Spanish Dub Study VOT entry missing")
if 'clockSource = hasSpanish ? "tts-pending" : "translation-pending";' not in texts[subtitle]:
    raise RuntimeError("pre-TTS subtitle hold missing")
if "OPENROUTER_MAX_BATCH_CHARS = 1500" not in texts[translator] or "OPENROUTER_FIRST_BATCH_CHARS = 350" not in texts[translator]:
    raise RuntimeError("Morphe OpenRouter packet invariants changed")

print("v2.32.1 startup-safe audit passed")
