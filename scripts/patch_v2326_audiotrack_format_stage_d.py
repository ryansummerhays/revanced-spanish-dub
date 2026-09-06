#!/usr/bin/env python3
"""v2.32.6: Stage-D actual AudioTrack format metadata probe on top of v2.32.5.

Stage C proved that the decoded ByteBuffer can be read safely and contains real non-zero audio.
Before interpreting any bytes as PCM16/float, Stage D captures metadata from the *actual*
AudioTrack receiver used by the proven ByteBuffer write call. The receiver probe is one-register,
allocation-free, fail-soft, and only performs AudioTrack getters on the first call and then once
every 4096 callbacks after a successful observation. The proven Stage-C ByteBuffer callback is
left intact.

No PCM decoding, byte arrays/copies, workers, FFT, VAD, clustering, speaker assignment, voice
routing, subtitle changes, translation packet changes, or TTS changes are introduced.
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
        raise SystemExit("usage: patch_v2326_audiotrack_format_stage_d.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    for path in (player_volume, controller, hook):
        if not path.is_file():
            raise RuntimeError(f"missing v2.32.5 source: {path}")

    rep(
        player_volume,
        "    private static volatile long studyPcmSampleRollingHash = 1125899906842597L;\n",
        "    private static volatile long studyPcmSampleRollingHash = 1125899906842597L;\n"
        "    private static final int STUDY_AUDIO_TRACK_PROBE_STRIDE = 4096;\n"
        "    private static volatile long studyAudioTrackProbeCalls;\n"
        "    private static volatile long studyAudioTrackProbeAttempts;\n"
        "    private static volatile long studyAudioTrackProbeSuccess;\n"
        "    private static volatile long studyAudioTrackProbeErrors;\n"
        "    private static volatile int studyAudioTrackSessionId = -1;\n"
        "    private static volatile int studyAudioTrackSampleRateHz;\n"
        "    private static volatile int studyAudioTrackChannelCount;\n"
        "    private static volatile int studyAudioTrackEncoding;\n"
        "    private static volatile int studyAudioTrackState = -1;\n"
        "    private static volatile int studyAudioTrackPlayState = -1;\n",
        "add Stage-D AudioTrack metadata counters",
    )

    callback_anchor = '''    /**
     * Spanish Dub Study Stage-B injection point. Runs on ExoPlayer's audio thread.
     * The duplicate has independent position/limit state; no sample bytes are read and the
     * original playback buffer is never mutated.
     */
    public static void observePcmBufferForStudy(ByteBuffer buffer) {
'''
    callback_insert = '''    /**
     * Spanish Dub Study Stage-D receiver probe. This receives the exact AudioTrack object on
     * which ExoPlayer is about to call write(ByteBuffer,...). Getter work is deliberately sparse
     * after the first successful observation and all failures are swallowed into counters.
     */
    public static void observeAudioTrackForStudy(AudioTrack track) {
        studyAudioTrackProbeCalls++;
        if (track == null) return;

        final long calls = studyAudioTrackProbeCalls;
        if (studyAudioTrackProbeSuccess > 0 && (calls % STUDY_AUDIO_TRACK_PROBE_STRIDE) != 0) return;

        studyAudioTrackProbeAttempts++;
        try {
            final int sessionId = track.getAudioSessionId();
            final int sampleRateHz = track.getSampleRate();
            final int channelCount = track.getChannelCount();
            final int encoding = track.getAudioFormat();
            final int state = track.getState();
            final int playState = track.getPlayState();

            studyAudioTrackSessionId = sessionId;
            studyAudioTrackSampleRateHz = sampleRateHz;
            studyAudioTrackChannelCount = channelCount;
            studyAudioTrackEncoding = encoding;
            studyAudioTrackState = state;
            studyAudioTrackPlayState = playState;
            if (sampleRateHz > 0 && channelCount > 0 && encoding > 0) {
                studyAudioTrackProbeSuccess++;
            }
        } catch (Throwable ignored) {
            // Stage-D diagnostics must never take down ExoPlayer's audio thread.
            studyAudioTrackProbeErrors++;
        }
    }

    /**
     * Spanish Dub Study Stage-B injection point. Runs on ExoPlayer's audio thread.
     * The duplicate has independent position/limit state; no sample bytes are read and the
     * original playback buffer is never mutated.
     */
    public static void observePcmBufferForStudy(ByteBuffer buffer) {
'''
    rep(player_volume, callback_anchor, callback_insert, "add fail-soft actual AudioTrack receiver probe")

    getter_anchor = '''    public static long getPcmSampleRollingHashForStudy() { return studyPcmSampleRollingHash; }

'''
    getter_insert = '''    public static long getPcmSampleRollingHashForStudy() { return studyPcmSampleRollingHash; }
    public static int getAudioTrackProbeStrideForStudy() { return STUDY_AUDIO_TRACK_PROBE_STRIDE; }
    public static long getAudioTrackProbeCallsForStudy() { return studyAudioTrackProbeCalls; }
    public static long getAudioTrackProbeAttemptsForStudy() { return studyAudioTrackProbeAttempts; }
    public static long getAudioTrackProbeSuccessForStudy() { return studyAudioTrackProbeSuccess; }
    public static long getAudioTrackProbeErrorsForStudy() { return studyAudioTrackProbeErrors; }
    public static int getAudioTrackSessionIdForStudy() { return studyAudioTrackSessionId; }
    public static int getAudioTrackSampleRateHzForStudy() { return studyAudioTrackSampleRateHz; }
    public static int getAudioTrackChannelCountForStudy() { return studyAudioTrackChannelCount; }
    public static int getAudioTrackEncodingForStudy() { return studyAudioTrackEncoding; }
    public static int getAudioTrackStateForStudy() { return studyAudioTrackState; }
    public static int getAudioTrackPlayStateForStudy() { return studyAudioTrackPlayState; }

'''
    rep(player_volume, getter_anchor, getter_insert, "publish Stage-D AudioTrack metadata getters")

    old_hook = '''        val bufferRegister = when (val writeInstruction = pcmMethod.getInstruction(writeIndex)) {
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
        pcmMethod.addInstructions(
            writeIndex,
            """
                invoke-static/range { v$trackRegister .. v$trackRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observeAudioTrackForStudy(Landroid/media/AudioTrack;)V
                invoke-static/range { v$bufferRegister .. v$bufferRegister }, $PLAYER_VOLUME_CLASS_DESCRIPTOR->observePcmBufferForStudy(Ljava/nio/ByteBuffer;)V
            """
        )
'''
    rep(hook, old_hook, new_hook, "inject actual AudioTrack receiver metadata callback beside proven PCM callback")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.5 Stage-C PCM sample-read diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.6 Stage-D AudioTrack format diagnostics\\n");',
        "update Stage-D diagnostics header",
    )

    diag_anchor = '''        report.append("pcmProbeSampleRollingHash=").append(PlayerVolumePatch.getPcmSampleRollingHashForStudy()).append('\\n');
'''
    diag_insert = '''        report.append("pcmProbeSampleRollingHash=").append(PlayerVolumePatch.getPcmSampleRollingHashForStudy()).append('\\n');
        report.append("pcmTrackProbe=actual-audiotrack-write-receiver-format-metadata\\n");
        report.append("pcmTrackProbeStride=").append(PlayerVolumePatch.getAudioTrackProbeStrideForStudy()).append('\\n');
        report.append("pcmTrackProbeCalls=").append(PlayerVolumePatch.getAudioTrackProbeCallsForStudy()).append('\\n');
        report.append("pcmTrackProbeAttempts=").append(PlayerVolumePatch.getAudioTrackProbeAttemptsForStudy()).append('\\n');
        report.append("pcmTrackProbeSuccess=").append(PlayerVolumePatch.getAudioTrackProbeSuccessForStudy()).append('\\n');
        report.append("pcmTrackProbeErrors=").append(PlayerVolumePatch.getAudioTrackProbeErrorsForStudy()).append('\\n');
        report.append("pcmTrackSessionId=").append(PlayerVolumePatch.getAudioTrackSessionIdForStudy()).append('\\n');
        report.append("pcmTrackSampleRateHz=").append(PlayerVolumePatch.getAudioTrackSampleRateHzForStudy()).append('\\n');
        report.append("pcmTrackChannelCount=").append(PlayerVolumePatch.getAudioTrackChannelCountForStudy()).append('\\n');
        report.append("pcmTrackEncoding=").append(PlayerVolumePatch.getAudioTrackEncodingForStudy()).append('\\n');
        report.append("pcmTrackState=").append(PlayerVolumePatch.getAudioTrackStateForStudy()).append('\\n');
        report.append("pcmTrackPlayState=").append(PlayerVolumePatch.getAudioTrackPlayStateForStudy()).append('\\n');
'''
    rep(controller, diag_anchor, diag_insert, "publish actual AudioTrack format metadata")

    print("v2.32.6 Stage-D actual AudioTrack format probe complete")
    print("UNCHANGED: Stage-C sparse raw-byte reads, English-source repair, mergeIntoSentences, 1500/350 OpenRouter batching, subtitles, TTS")
    print("NOT ADDED: PCM decoding, sample copies/arrays, workers, FFT, VAD, clustering, speaker assignment, voice routing")


if __name__ == "__main__":
    main()
