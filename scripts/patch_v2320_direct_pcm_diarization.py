#!/usr/bin/env python3
"""v2.32: direct PCM diarization probe + pre-TTS subtitle hold + cleaner study entry."""
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
        raise SystemExit("usage: patch_v2320_direct_pcm_diarization.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    patches_volume = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"

    vot = pkg / "VoiceOverTranslationPatch.java"
    translator = pkg / "TranscriptTranslator.java"
    subtitle = study / "SpanishSubtitleOverlay.java"
    controller = study / "SpanishStudyController.java"
    sheet = study / "SpanishStudySheet.java"
    bottom_sheet = pkg / "VotBottomSheet.java"

    for path in (vot, translator, subtitle, controller, sheet, bottom_sheet, patches_volume):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # Replace the failed Visualizer implementation after the v2.30 latch has already been applied.
    # The new backend reads only a copied slice of the decoded PCM buffer; no microphone/audio-capture
    # permission and no cloud diarization service are used.
    for name in ("LocalSpeakerDiarizer.java", "PcmSpeakerFeature.java"):
        src = repo / "overlay/v232/app/spanishstudy/vot" / name
        if not src.is_file():
            raise RuntimeError(f"missing v2.32 source: {src}")
        shutil.copy2(src, study / name)
        print("copied:", name)

    # Hook the actual ExoPlayer -> AudioTrack ByteBuffer write. We first try the normal invoke and
    # then the range form, and support both the common 3-argument and timestamped 4-argument write.
    rep(
        patches_volume,
        "import app.morphe.patcher.extensions.InstructionExtensions.addInstruction\n"
        "import app.morphe.patcher.extensions.InstructionExtensions.addInstructions\n"
        "import app.morphe.patcher.patch.bytecodePatch\n",
        "import app.morphe.patcher.extensions.InstructionExtensions.addInstruction\n"
        "import app.morphe.patcher.extensions.InstructionExtensions.addInstructions\n"
        "import app.morphe.patcher.extensions.InstructionExtensions.getInstruction\n"
        "import app.morphe.patcher.methodCall\n"
        "import app.morphe.patcher.patch.PatchException\n"
        "import app.morphe.patcher.patch.bytecodePatch\n"
        "import app.morphe.util.indexOfFirstInstruction\n"
        "import com.android.tools.smali.dexlib2.Opcode\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.FiveRegisterInstruction\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.RegisterRangeInstruction\n",
        "import PCM hook patch helpers",
    )

    old_hook = '''        AudioTrackWrapperInitFingerprint.method.addInstruction(
            0,
            "invoke-static { p1 }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->setAudioTrack(Landroid/media/AudioTrack;)V"
        )
'''
    new_hook = '''        AudioTrackWrapperInitFingerprint.method.addInstruction(
            0,
            "invoke-static { p1 }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->setAudioTrack(Landroid/media/AudioTrack;)V"
        )

        // Spanish Dub Study v2.32: read-only PCM probe immediately before YouTube writes decoded
        // audio to AudioTrack. The extension duplicates the ByteBuffer before reading it, so this
        // hook cannot advance or mutate ExoPlayer's playback buffer.
        val write3 = methodCall(
            definingClass = "Landroid/media/AudioTrack;",
            name = "write",
            returnType = "I",
            parameters = listOf("Ljava/nio/ByteBuffer;", "I", "I")
        )
        val write4 = methodCall(
            definingClass = "Landroid/media/AudioTrack;",
            name = "write",
            returnType = "I",
            parameters = listOf("Ljava/nio/ByteBuffer;", "I", "I", "J")
        )
        val audioSinkClass = this@execute.mutableClassDefBy(AudioSinkSetVolumeFingerprint.method.definingClass)
        val pcmMethod = audioSinkClass.methods.firstOrNull { method ->
            method.indexOfFirstInstruction(write3) >= 0 || method.indexOfFirstInstruction(write4) >= 0
        } ?: throw PatchException("AudioTrack ByteBuffer write method not found in ${audioSinkClass.type}")

        var writeIndex = pcmMethod.indexOfFirstInstruction(write3)
        if (writeIndex < 0) writeIndex = pcmMethod.indexOfFirstInstruction(write4)
        if (writeIndex < 0) throw PatchException("AudioTrack ByteBuffer write invoke disappeared")

        when (val writeInstruction = pcmMethod.getInstruction(writeIndex)) {
            is FiveRegisterInstruction -> {
                val bufferRegister = writeInstruction.registerD
                val sizeRegister = writeInstruction.registerE
                pcmMethod.addInstruction(
                    writeIndex,
                    "invoke-static { v$bufferRegister, v$sizeRegister }, " +
                            "Lapp/spanishstudy/vot/LocalSpeakerDiarizer;->onPcmBuffer(Ljava/nio/ByteBuffer;I)V"
                )
            }
            is RegisterRangeInstruction -> {
                val bufferRegister = writeInstruction.startRegister + 1
                val sizeRegister = writeInstruction.startRegister + 2
                pcmMethod.addInstruction(
                    writeIndex,
                    "invoke-static/range { v$bufferRegister .. v$sizeRegister }, " +
                            "Lapp/spanishstudy/vot/LocalSpeakerDiarizer;->onPcmBuffer(Ljava/nio/ByteBuffer;I)V"
                )
            }
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
'''
    rep(patches_volume, old_hook, new_hook, "inject direct decoded PCM hook")

    # Let the subtitle layer know whether the selected speech path is Edge even before MediaPlayer
    # starts. This is display-only state and does not modify the TTS or translation pipeline.
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

    # v2.31 could render page 2/3/4 from the video clock before Edge speech started, then jump back
    # to page 1 as soon as MediaPlayer began. While translation/Edge speech is pending, hold page 1.
    # After audio has actually played this segment, the v2.30 audio-progress latch still handles the
    # post-speech handoff and prevents backwards movement.
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

    # Keep the original Morphe packets. Only strengthen the wording request against accidental
    # English code-switching that was still visible in v2.31 (e.g. 'collecting', 'exactly', 'maybe').
    rep(
        translator,
        "Use natural conversational spoken Spanish suitable for dubbing and subtitles; prefer idiomatic phrasing over literal word-for-word translation while preserving meaning, names, tone, and line correspondence. Do not summarize or add information. ",
        "Use natural conversational spoken Spanish suitable for dubbing and subtitles; prefer idiomatic phrasing over literal word-for-word translation while preserving meaning, names, tone, and line correspondence. Do not code-switch into English except for proper nouns, branded names, titles, or source terms that intentionally need to remain in English. Do not summarize or add information. ",
        "discourage accidental English code-switching without packet changes",
    )

    # One clean entry in Morphe's VOT sheet. All custom controls remain inside the study sheet.
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
    rep(
        sheet,
        '"$0 API cost. Reads YouTube\'s AudioTrack visualization session; no microphone. Labels only in v2.28.",',
        '"$0 API cost. Analyzes a copied slice of YouTube\'s decoded playback PCM; no microphone or cloud audio.",',
        "update speaker setting description",
    )
    rep(
        sheet,
        '"This is a capture/clustering probe, not the final sherpa-onnx model. The diagnostics report AudioTrack attach status, waveform/FFT callbacks, voiced frames, per-segment assignments, cluster creation and similarity scores.");',
        '"This is still an experimental local A/B/C/D clustering probe. v2.32 reads decoded PCM directly before AudioTrack.write; diagnostics report PCM hook calls, analyzed chunks, voiced frames, assignments, clusters and similarity scores.");',
        "update speaker experiment note",
    )
    rep(
        sheet,
        '"AudioTrack session, Visualizer attach and callback health",',
        '"AudioTrack format, direct PCM hook calls and copied-buffer analysis health",',
        "update audio diagnostic description",
    )
    rep(
        sheet,
        '"v2.28 keeps Mistral/OpenRouter and Morphe\'s normal sentence-sized VOT speech. Diagnostic hooks are intended to observe the pipeline, not change its decisions.");',
        '"Translation packetization remains stock Morphe. Subtitle presentation and local PCM speaker analysis are downstream layers and do not change the source translation packets.");',
        "update sheet architecture note",
    )

    rep(controller,
        'report.append("Spanish Dub Study v2.31.0 diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.0 diagnostics\\n");',
        "update diagnostics version")
    rep(controller,
        'report.append("subtitleClock=edge-mediaplayer+video-fallback+monotonic-audio-handoff\\n");',
        'report.append("subtitleClock=edge-mediaplayer+pre-tts-hold+video-fallback+monotonic-audio-handoff\\n");',
        "report pre-TTS subtitle hold")
    rep(controller,
        'report.append("translationPromptStyle=natural-conversational-spoken-target-no-packet-change\\n");',
        'report.append("translationPromptStyle=natural-conversational-spoken-target+anti-code-switch-no-packet-change\\n");',
        "report anti-code-switch prompt")

    print("v2.32 direct PCM diarization patch complete")


if __name__ == "__main__":
    main()
