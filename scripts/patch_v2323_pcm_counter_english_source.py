#!/usr/bin/env python3
"""v2.32.3: English-first Spanish source selection + minimal Stage-A PCM counter probe.

This deliberately does NOT restore the v2.32 diarizer. The AudioTrack.write hook passes one
ByteBuffer reference to the already-known PlayerVolumePatch extension class, where the callback
only increments a primitive counter. No buffer reads, copies, allocation, logging, worker thread,
FFT, VAD, clustering, or speaker assignment happen in the callback.
"""
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
        raise SystemExit("usage: patch_v2323_pcm_counter_english_source.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    pkg = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation"
    study = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    fetcher = pkg / "TranscriptFetcher.java"
    controller = study / "SpanishStudyController.java"
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    translator = pkg / "TranscriptTranslator.java"

    for path in (fetcher, controller, player_volume, hook, translator):
        if not path.is_file():
            raise RuntimeError(f"missing source: {path}")

    # ------------------------------------------------------------------
    # English source repair for the Spanish-study use case.
    # ------------------------------------------------------------------
    # Morphe normally prefers a caption track already in the target language. When the target is
    # Spanish, that can select YouTube's Spanish track, leaving the bilingual subtitle layer with
    # no English source at all. Prefer a non-Gemini English track only for a Spanish target when
    # one exists; all existing fallbacks remain intact.
    rep(
        fetcher,
        "        if (targetLangUrl != null) return targetLangUrl;\n"
        "        if (englishUrl != null) return englishUrl;\n",
        "        // Spanish Dub Study: preserve an English source track for bilingual display and\n"
        "        // English->Spanish translation whenever a real non-Gemini English track exists.\n"
        "        if (\"es\".equals(targetLang) && englishUrl != null) return englishUrl;\n"
        "        if (targetLangUrl != null) return targetLangUrl;\n"
        "        if (englishUrl != null) return englishUrl;\n",
        "prefer English source when Spanish is the target",
    )

    # ------------------------------------------------------------------
    # Stage A direct-PCM probe: one argument, counter only.
    # ------------------------------------------------------------------
    rep(
        player_volume,
        "import android.media.AudioTrack;\n\nimport java.util.concurrent.atomic.AtomicReference;\n",
        "import android.media.AudioTrack;\n\nimport java.nio.ByteBuffer;\nimport java.util.concurrent.atomic.AtomicReference;\n",
        "import ByteBuffer for Stage-A probe",
    )
    rep(
        player_volume,
        "    private static final AtomicReference<AudioTrack> lastAudioTrackRef = new AtomicReference<>(null);\n",
        "    private static final AtomicReference<AudioTrack> lastAudioTrackRef = new AtomicReference<>(null);\n"
        "    private static volatile long studyPcmHookCalls;\n",
        "add Stage-A PCM hook counter",
    )
    rep(
        player_volume,
        "    /**\n"
        "     * Sets the ducking multiplier (0..1). Called from the main thread.\n"
        "     */\n",
        "    /**\n"
        "     * Spanish Dub Study Stage-A injection point. Runs on ExoPlayer's audio thread.\n"
        "     * Intentionally does not inspect, duplicate, copy, log, allocate, or dispatch the buffer.\n"
        "     */\n"
        "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n"
        "        studyPcmHookCalls++;\n"
        "    }\n\n"
        "    /** Read-only diagnostic counter for the Stage-A decoded-PCM hook. */\n"
        "    public static long getPcmHookCallsForStudy() {\n"
        "        return studyPcmHookCalls;\n"
        "    }\n\n"
        "    /**\n"
        "     * Sets the ducking multiplier (0..1). Called from the main thread.\n"
        "     */\n",
        "add counter-only PCM callback",
    )

    # Patch the same decoded ByteBuffer write family as the v2.32 experiment, but the injected
    # call now carries only the ByteBuffer and targets the existing PlayerVolumePatch descriptor.
    # Using invoke-static/range for one register also avoids the short-register encoding constraint.
    rep(
        hook,
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
        "import com.android.tools.smali.dexlib2.iface.instruction.FiveRegisterInstruction\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.RegisterRangeInstruction\n",
        "import minimal PCM hook helpers",
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

        // Spanish Dub Study v2.32.3 Stage A: prove that a decoded ByteBuffer callback can execute
        // safely before AudioTrack.write. The callback only increments a counter.
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

        val bufferRegister = when (val writeInstruction = pcmMethod.getInstruction(writeIndex)) {
            is FiveRegisterInstruction -> writeInstruction.registerD
            is RegisterRangeInstruction -> writeInstruction.startRegister + 1
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        pcmMethod.addInstruction(
            writeIndex,
            "invoke-static/range { v$bufferRegister .. v$bufferRegister }, " +
                    "$PLAYER_VOLUME_CLASS_DESCRIPTOR->observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V"
        )
'''
    rep(hook, old_hook, new_hook, "inject one-register counter-only decoded PCM hook")

    # Diagnostics make this test self-identifying. Keep the old Visualizer diagnostics present as
    # a control; the new pcmProbe lines are independent and are the only success criteria here.
    rep(
        controller,
        "import app.morphe.extension.shared.Utils;\n",
        "import app.morphe.extension.shared.Utils;\n"
        "import app.morphe.extension.youtube.patches.PlayerVolumePatch;\n",
        "controller PCM counter import",
    )
    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.2 control diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.3 Stage-A PCM diagnostics\\n");',
        "update Stage-A diagnostics version",
    )
    rep(
        controller,
        'report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append(\'\\n\');\n',
        'report.append("openRouterModel=").append(Settings.VOT_OPENROUTER_MODEL.get()).append(\'\\n\');\n'
        '        report.append("captionSourcePolicy=english-first-for-spanish-target-when-available\\n");\n'
        '        report.append("pcmProbe=audio-track-write-bytebuffer-counter-only\\n");\n'
        '        report.append("pcmProbeBufferReads=0\\n");\n'
        '        report.append("pcmProbeBufferCopies=0\\n");\n'
        '        report.append("pcmProbeWorkerThreads=0\\n");\n'
        '        report.append("pcmProbeHookCalls=").append(PlayerVolumePatch.getPcmHookCallsForStudy()).append(\'\\n\');\n',
        "report English-source policy and PCM Stage-A counter",
    )

    print("v2.32.3 Stage-A PCM counter + English source repair complete")
    print("UNCHANGED: mergeIntoSentences, 1500/350 OpenRouter packet budgets, packet order, request packing, TTS architecture")


if __name__ == "__main__":
    main()
