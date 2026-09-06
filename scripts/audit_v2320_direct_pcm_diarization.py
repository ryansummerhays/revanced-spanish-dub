#!/usr/bin/env python3
"""Audit v2.32 direct PCM diarization without allowing translation packet drift."""
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: audit_v2320_direct_pcm_diarization.py <morphe-root>")

root = Path(sys.argv[1]).resolve()
pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
translator = pkg / "TranscriptTranslator.java"
fetcher = pkg / "TranscriptFetcher.java"
vot = pkg / "VoiceOverTranslationPatch.java"
subtitle = study / "SpanishSubtitleOverlay.java"
speaker = study / "LocalSpeakerDiarizer.java"
pcm = study / "PcmSpeakerFeature.java"
controller = study / "SpanishStudyController.java"
sheet = study / "SpanishStudySheet.java"
bottom = pkg / "VotBottomSheet.java"
volume_hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"

for path in (translator, fetcher, vot, subtitle, speaker, pcm, controller, sheet, bottom, volume_hook):
    if not path.is_file():
        raise RuntimeError(f"missing audited source: {path}")

T = translator.read_text(encoding="utf-8")
F = fetcher.read_text(encoding="utf-8")
V = vot.read_text(encoding="utf-8")
S = subtitle.read_text(encoding="utf-8")
D = speaker.read_text(encoding="utf-8")
P = pcm.read_text(encoding="utf-8")
C = controller.read_text(encoding="utf-8")
H = sheet.read_text(encoding="utf-8")
B = bottom.read_text(encoding="utf-8")
K = volume_hook.read_text(encoding="utf-8")

checks = {
    "hard rule 1500-char packet": "OPENROUTER_MAX_BATCH_CHARS = 1_500" in T,
    "hard rule 350-char first packet": "OPENROUTER_FIRST_BATCH_CHARS = 350" in T,
    "hard rule stock mergeIntoSentences": "mergeIntoSentences" in F,
    "native packet diagnostics": "translationPacketization=stock-morphe-1500char+350char-first-UNCHANGED" in C,
    "anti code-switch wording": "Do not code-switch into English except for proper nouns" in T,
    "direct PCM callback": "onPcmBuffer(ByteBuffer buffer, int requestedBytes)" in D,
    "no Visualizer backend": "android.media.audiofx.Visualizer" not in D and "new Visualizer" not in D,
    "no mic permission in diarizer": "RECORD_AUDIO" not in D,
    "PCM hook bytecode": "LocalSpeakerDiarizer;->onPcmBuffer(Ljava/nio/ByteBuffer;I)V" in K,
    "ByteBuffer duplicate safety": "buffer.duplicate()" in D,
    "bounded PCM queue": "new ArrayBlockingQueue<>(4)" in D,
    "pure PCM helper installed": "class PcmSpeakerFeature" in P,
    "PCM backend diagnostic": "speakerBackend=direct-exoplayer-pcm-local-spectral-clustering-experiment" in D,
    "pre TTS hold": 'clockSource = hasSpanish ? "tts-pending" : "translation-pending"' in S,
    "Edge selection getter": "isEdgeSelectedForStudy" in V,
    "simple VOT entry": 'makeValueRow(context, fg, "Spanish Dub Study")' in B,
    "old clutter removed": "Subtitles · local speakers · deep diagnostics" not in B,
    "sheet title simplified": 'title.setText("Spanish Dub Study")' in H,
    "v2.32 diagnostics": "Spanish Dub Study v2.32.0 diagnostics" in C,
}

failed = [name for name, ok in checks.items() if not ok]
for name, ok in checks.items():
    print(("PASS" if ok else "FAIL") + ": " + name)
if failed:
    raise SystemExit("v2.32 audit failed: " + ", ".join(failed))
print("v2.32 audit passed")
