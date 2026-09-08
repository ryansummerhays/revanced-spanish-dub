#!/usr/bin/env python3
"""v2.33.27: post-AudioTrack.write accepted-byte/frame accounting.

This is intentionally a diagnostic-only gate on top of v2.33.26.

Goals:
- preserve the proven v2.33.26 render clock and Sherpa stride-4 capture unchanged;
- instrument the *return value* of the exact AudioTrack.write(ByteBuffer, ...) call;
- count requested bytes before the write and accepted bytes only after move-result;
- keep the write invoke and move-result adjacent (Android verifier requirement);
- compare cumulative accepted frames with rendered playback-head frames and videoMs only from the
  controller-side AudioVideoSyncProbe, never by calling YouTube/player APIs from the write hook;
- make no speaker-routing, subtitle-timing, translation-packet, or TTS behavior change.

The hot-path callbacks do primitive counter arithmetic only. v2.33.27 does NOT yet feed Sherpa or
LS-EEND from accepted-write accounting; it exists to prove that accepted PCM duration tracks real
playback before a stateful streaming diarizer is introduced.
"""
from pathlib import Path
import shutil
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: patch_v23327_accepted_write_accounting.py <morphe-root> <repo-root>")

    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    sherpa = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    helper_src = repo / "overlay/v23327/app/spanishstudy/vot/AudioVideoSyncProbe.java"
    helper_dst = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/AudioVideoSyncProbe.java"
    for p in (player, controller, sherpa, hook, helper_src, helper_dst):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.27 input: {p}")

    shutil.copy2(helper_src, helper_dst)
    print("copied: v2.33.27 AudioVideoSyncProbe.java")

    # Primitive write accounting state. These totals are process-lifetime; the controller-side
    # sync helper takes a per-video/continuity/session baseline before comparing with render time.
    rep(
        player,
        "    private static final int STUDY_PCM16_ENCODING = 2;\n",
        "    private static volatile long studyPcmWriteAttempts;\n"
        "    private static volatile long studyPcmWriteSuccessful;\n"
        "    private static volatile long studyPcmWritePartial;\n"
        "    private static volatile long studyPcmWriteZero;\n"
        "    private static volatile long studyPcmWriteErrors;\n"
        "    private static volatile long studyPcmWriteRequestedBytes;\n"
        "    private static volatile long studyPcmWriteAcceptedBytes;\n"
        "    private static volatile long studyPcmWriteAcceptedFrames;\n"
        "    private static volatile int studyPcmWritePendingRequestedBytes;\n"
        "    private static final int STUDY_PCM16_ENCODING = 2;\n",
        "add accepted-write primitive counters",
    )

    callback_anchor = "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n"
    callback_insert = '''    /**
     * v2.33.27 pre-write accounting. The patch passes AudioTrack.write's explicit sizeInBytes
     * argument here immediately before the real write. Primitive state only; no allocation,
     * ByteBuffer access, logging, player API, worker dispatch, or neural work.
     */
    public static void observeAudioTrackWriteRequestedForStudy(int requestedBytes) {
        studyPcmWriteAttempts++;
        final int bounded = Math.max(0, requestedBytes);
        studyPcmWritePendingRequestedBytes = bounded;
        studyPcmWriteRequestedBytes += bounded;
    }

    /**
     * v2.33.27 post-write accounting. Called only after AudioTrack.write's move-result, so a
     * positive result is the number of bytes Android actually accepted on this call.
     */
    public static void observeAudioTrackWriteResultForStudy(int result) {
        final int requested = studyPcmWritePendingRequestedBytes;
        studyPcmWritePendingRequestedBytes = 0;
        if (result > 0) {
            studyPcmWriteSuccessful++;
            studyPcmWriteAcceptedBytes += result;
            if (requested > 0 && result < requested) studyPcmWritePartial++;

            final int channels = studyAudioTrackChannelCount;
            if (studyAudioTrackEncoding == STUDY_PCM16_ENCODING && channels > 0 && channels <= 8) {
                final int bytesPerFrame = channels * 2;
                studyPcmWriteAcceptedFrames += result / bytesPerFrame;
            }
        } else if (result == 0) {
            studyPcmWriteZero++;
        } else {
            studyPcmWriteErrors++;
        }
    }

    public static void observePcmBufferForStudy(ByteBuffer buffer) {
'''
    rep(player, callback_anchor, callback_insert, "add pre/post AudioTrack.write result accounting")

    getter_anchor = "    public static int getAudioTrackPlayStateForStudy() { return studyAudioTrackPlayState; }\n\n"
    getter_insert = '''    public static int getAudioTrackPlayStateForStudy() { return studyAudioTrackPlayState; }
    public static long getPcmWriteAttemptsForStudy() { return studyPcmWriteAttempts; }
    public static long getPcmWriteSuccessfulForStudy() { return studyPcmWriteSuccessful; }
    public static long getPcmWritePartialForStudy() { return studyPcmWritePartial; }
    public static long getPcmWriteZeroForStudy() { return studyPcmWriteZero; }
    public static long getPcmWriteErrorsForStudy() { return studyPcmWriteErrors; }
    public static long getPcmWriteRequestedBytesForStudy() { return studyPcmWriteRequestedBytes; }
    public static long getPcmWriteAcceptedBytesForStudy() { return studyPcmWriteAcceptedBytes; }
    public static long getPcmWriteAcceptedFramesForStudy() { return studyPcmWriteAcceptedFrames; }
    public static int getPcmWritePendingRequestedBytesForStudy() { return studyPcmWritePendingRequestedBytes; }

'''
    rep(player, getter_anchor, getter_insert, "publish accepted-write accounting getters")

    # Extend the source-level bytecode patch. Inspect the original move-result before inserting
    # anything. Insert the post-result callback after it first, then add the pre-write callbacks;
    # this guarantees the final bytecode remains:
    #   pre callbacks -> AudioTrack.write -> move-result -> post-result callback.
    rep(
        hook,
        "import com.android.tools.smali.dexlib2.iface.instruction.FiveRegisterInstruction\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.RegisterRangeInstruction\n",
        "import com.android.tools.smali.dexlib2.Opcode\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.FiveRegisterInstruction\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.OneRegisterInstruction\n"
        "import com.android.tools.smali.dexlib2.iface.instruction.RegisterRangeInstruction\n",
        "import move-result inspection support",
    )

    old_hook = '''        val writeInstruction = pcmMethod.getInstruction(writeIndex)
        val trackRegister = when (writeInstruction) {
            is FiveRegisterInstruction -> writeInstruction.registerC
            is RegisterRangeInstruction -> writeInstruction.startRegister
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        val bufferRegister = when (writeInstruction) {
            is FiveRegisterInstruction -> writeInstruction.registerD
            is RegisterRangeInstruction -> writeInstruction.startRegister + 1
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        pcmMethod.addInstructions(
            writeIndex,
            """
                invoke-static/range { v$trackRegister .. v$trackRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observeAudioTrackForStudy(Landroid/media/AudioTrack;)V
                invoke-static/range { v$bufferRegister .. v$bufferRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V
            """
        )
'''
    new_hook = '''        val writeInstruction = pcmMethod.getInstruction(writeIndex)
        val trackRegister = when (writeInstruction) {
            is FiveRegisterInstruction -> writeInstruction.registerC
            is RegisterRangeInstruction -> writeInstruction.startRegister
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        val bufferRegister = when (writeInstruction) {
            is FiveRegisterInstruction -> writeInstruction.registerD
            is RegisterRangeInstruction -> writeInstruction.startRegister + 1
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        val requestedBytesRegister = when (writeInstruction) {
            is FiveRegisterInstruction -> writeInstruction.registerE
            is RegisterRangeInstruction -> writeInstruction.startRegister + 2
            else -> throw PatchException("Unsupported AudioTrack.write invoke form: $writeInstruction")
        }
        val resultInstruction = pcmMethod.getInstruction(writeIndex + 1)
        if (resultInstruction !is OneRegisterInstruction || resultInstruction.opcode != Opcode.MOVE_RESULT) {
            throw PatchException("AudioTrack.write is not immediately followed by move-result: $resultInstruction")
        }
        val resultRegister = resultInstruction.registerA

        // Add this first while writeIndex still refers to the original write. It lands after the
        // original move-result. The pre-write insertion below then shifts write+move-result+post
        // together, preserving mandatory invoke/move-result adjacency.
        pcmMethod.addInstruction(
            writeIndex + 2,
            "invoke-static/range { v$resultRegister .. v$resultRegister }, " +
                    "$PLAYER_VOLUME_CLASS_DESCRIPTOR->observeAudioTrackWriteResultForStudy(I)V"
        )
        pcmMethod.addInstructions(
            writeIndex,
            """
                invoke-static/range { v$trackRegister .. v$trackRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observeAudioTrackForStudy(Landroid/media/AudioTrack;)V
                invoke-static/range { v$bufferRegister .. v$bufferRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V
                invoke-static/range { v$requestedBytesRegister .. v$requestedBytesRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observeAudioTrackWriteRequestedForStudy(I)V
            """
        )
'''
    rep(hook, old_hook, new_hook, "instrument AudioTrack.write requested bytes and post-move-result value")

    # Self-identifying diagnostics. Keep Sherpa stride-4 and coarse projected timeline unchanged.
    rep(
        controller,
        'report.append("Spanish Dub Study v2.33.26 neural absolute-timeline + audio-render-clock diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.27 accepted-write PCM clock diagnostics\\n");',
        "update v2.33.27 diagnostics header",
    )
    rep(
        controller,
        '        report.append("audioVideoBridge=render-clock-anchor-probe-active;pcm-admission-still-stride4\\n");\n',
        '        report.append("audioVideoBridge=render-clock+accepted-write-accounting-active;pcm-admission-still-stride4\\n");\n'
        '        report.append("pcmAdmission=unchanged-sherpa-stride4-v23327-diagnostic-only\\n");\n',
        "declare accepted-write accounting active without changing PCM admission",
    )

    diag_anchor = '''        report.append("pcmTrackPlayState=").append(PlayerVolumePatch.getAudioTrackPlayStateForStudy()).append('\\n');
'''
    diag_insert = '''        report.append("pcmTrackPlayState=").append(PlayerVolumePatch.getAudioTrackPlayStateForStudy()).append('\\n');
        report.append("pcmWriteAccounting=post-audiotrack-write-return-value-diagnostic-only\\n");
        report.append("pcmWritePairing=single-active-audiosink-request-before-write+result-after-move-result\\n");
        report.append("pcmWriteAttempts=").append(PlayerVolumePatch.getPcmWriteAttemptsForStudy()).append('\\n');
        report.append("pcmWriteSuccessful=").append(PlayerVolumePatch.getPcmWriteSuccessfulForStudy()).append('\\n');
        report.append("pcmWritePartial=").append(PlayerVolumePatch.getPcmWritePartialForStudy()).append('\\n');
        report.append("pcmWriteZero=").append(PlayerVolumePatch.getPcmWriteZeroForStudy()).append('\\n');
        report.append("pcmWriteErrors=").append(PlayerVolumePatch.getPcmWriteErrorsForStudy()).append('\\n');
        report.append("pcmWriteRequestedBytes=").append(PlayerVolumePatch.getPcmWriteRequestedBytesForStudy()).append('\\n');
        report.append("pcmWriteAcceptedBytes=").append(PlayerVolumePatch.getPcmWriteAcceptedBytesForStudy()).append('\\n');
        report.append("pcmWriteAcceptedFrames=").append(PlayerVolumePatch.getPcmWriteAcceptedFramesForStudy()).append('\\n');
        int pcmWriteRate = PlayerVolumePatch.getAudioTrackSampleRateHzForStudy();
        long pcmWriteAcceptedMs = pcmWriteRate > 0
                ? (PlayerVolumePatch.getPcmWriteAcceptedFramesForStudy() * 1000L) / pcmWriteRate : 0L;
        report.append("pcmWriteAcceptedAudioMs=").append(pcmWriteAcceptedMs).append('\\n');
        long pcmWriteResults = PlayerVolumePatch.getPcmWriteSuccessfulForStudy()
                + PlayerVolumePatch.getPcmWriteZeroForStudy()
                + PlayerVolumePatch.getPcmWriteErrorsForStudy();
        report.append("pcmWriteUnpairedAttempts=")
                .append(Math.max(0L, PlayerVolumePatch.getPcmWriteAttemptsForStudy() - pcmWriteResults)).append('\\n');
        report.append("pcmWritePendingRequestedBytes=")
                .append(PlayerVolumePatch.getPcmWritePendingRequestedBytesForStudy()).append('\\n');
'''
    rep(controller, diag_anchor, diag_insert, "publish accepted-write counters")

    # Assert the neural path stays on the proven v2.33.26 containment gate. We deliberately make
    # no source mutation to SherpaNeuralShadow in v2.33.27.
    sherpa_text = sherpa.read_text(encoding="utf-8")
    required = [
        "if ((((int) captureBuffers) & 3) != 0) return;",
        "v2.33.26-neural-only+stride4+absolute-video-projection",
        "speakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse",
    ]
    for needle in required:
        if needle not in sherpa_text:
            raise RuntimeError(f"v2.33.27 containment precondition missing: {needle}")

    print("v2.33.27 accepted-write accounting patch complete")
    print("ACTIVE: post-AudioTrack.write accepted-byte/frame diagnostics + render/video comparison")
    print("UNCHANGED: Sherpa stride-4 admission, neural coarse timeline, translation, TTS, subtitle timing")
    print("NEXT AFTER RUNTIME VALIDATION: feed accepted PCM chronology into LS-EEND live shadow")


if __name__ == "__main__":
    main()
