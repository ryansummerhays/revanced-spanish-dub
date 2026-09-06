#!/usr/bin/env python3
"""v2.32.4: Stage-B direct PCM metadata probe on top of v2.32.3.

This advances exactly one step beyond the proven counter-only hook: duplicate the decoded
ByteBuffer and inspect position/limit/remaining without reading sample bytes or mutating the
playback buffer. No byte arrays, copying, sample decoding, logging on the audio thread, worker
threads, FFT, VAD, clustering, speaker assignment, or voice routing are introduced.
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
        raise SystemExit("usage: patch_v2324_pcm_metadata_stage_b.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    if not player_volume.is_file() or not controller.is_file():
        raise RuntimeError("missing v2.32.3 source tree")

    rep(
        player_volume,
        "    private static volatile long studyPcmHookCalls;\n",
        "    private static volatile long studyPcmHookCalls;\n"
        "    private static volatile long studyPcmNonNullBuffers;\n"
        "    private static volatile long studyPcmNullBuffers;\n"
        "    private static volatile long studyPcmNonEmptyBuffers;\n"
        "    private static volatile long studyPcmEmptyBuffers;\n"
        "    private static volatile long studyPcmObservedBytes;\n"
        "    private static volatile long studyPcmBufferDuplicates;\n"
        "    private static volatile int studyPcmLastPosition = -1;\n"
        "    private static volatile int studyPcmLastLimit = -1;\n"
        "    private static volatile int studyPcmLastRemaining = -1;\n"
        "    private static volatile int studyPcmMaxRemaining;\n",
        "add Stage-B PCM metadata counters",
    )

    old_callback = '''    /**
     * Spanish Dub Study Stage-A injection point. Runs on ExoPlayer's audio thread.
     * Intentionally does not inspect, duplicate, copy, log, allocate, or dispatch the buffer.
     */
    public static void observePcmBufferForStudy(ByteBuffer buffer) {
        studyPcmHookCalls++;
    }

    /** Read-only diagnostic counter for the Stage-A decoded-PCM hook. */
    public static long getPcmHookCallsForStudy() {
        return studyPcmHookCalls;
    }

'''
    new_callback = '''    /**
     * Spanish Dub Study Stage-B injection point. Runs on ExoPlayer's audio thread.
     * The duplicate has independent position/limit state; no sample bytes are read and the
     * original playback buffer is never mutated.
     */
    public static void observePcmBufferForStudy(ByteBuffer buffer) {
        studyPcmHookCalls++;
        if (buffer == null) {
            studyPcmNullBuffers++;
            return;
        }

        studyPcmNonNullBuffers++;
        ByteBuffer view = buffer.duplicate();
        studyPcmBufferDuplicates++;
        int position = view.position();
        int limit = view.limit();
        int remaining = view.remaining();
        studyPcmLastPosition = position;
        studyPcmLastLimit = limit;
        studyPcmLastRemaining = remaining;
        if (remaining > studyPcmMaxRemaining) studyPcmMaxRemaining = remaining;
        if (remaining > 0) {
            studyPcmNonEmptyBuffers++;
            studyPcmObservedBytes += remaining;
        } else {
            studyPcmEmptyBuffers++;
        }
    }

    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
    public static long getPcmNonNullBuffersForStudy() { return studyPcmNonNullBuffers; }
    public static long getPcmNullBuffersForStudy() { return studyPcmNullBuffers; }
    public static long getPcmNonEmptyBuffersForStudy() { return studyPcmNonEmptyBuffers; }
    public static long getPcmEmptyBuffersForStudy() { return studyPcmEmptyBuffers; }
    public static long getPcmObservedBytesForStudy() { return studyPcmObservedBytes; }
    public static long getPcmBufferDuplicatesForStudy() { return studyPcmBufferDuplicates; }
    public static int getPcmLastPositionForStudy() { return studyPcmLastPosition; }
    public static int getPcmLastLimitForStudy() { return studyPcmLastLimit; }
    public static int getPcmLastRemainingForStudy() { return studyPcmLastRemaining; }
    public static int getPcmMaxRemainingForStudy() { return studyPcmMaxRemaining; }

'''
    rep(player_volume, old_callback, new_callback, "advance Stage-A callback to metadata-only Stage B")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.3 Stage-A PCM diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.4 Stage-B PCM metadata diagnostics\\n");',
        "update Stage-B diagnostics header",
    )

    old_diag = '''        report.append("pcmProbe=audio-track-write-bytebuffer-counter-only\\n");
        report.append("pcmProbeBufferReads=0\\n");
        report.append("pcmProbeBufferCopies=0\\n");
        report.append("pcmProbeWorkerThreads=0\\n");
        report.append("pcmProbeHookCalls=").append(PlayerVolumePatch.getPcmHookCallsForStudy()).append('\\n');
'''
    new_diag = '''        report.append("pcmProbe=audio-track-write-bytebuffer-metadata-only\\n");
        report.append("pcmProbeSampleReads=0\\n");
        report.append("pcmProbeBufferCopies=0\\n");
        report.append("pcmProbeWorkerThreads=0\\n");
        report.append("pcmProbeHookCalls=").append(PlayerVolumePatch.getPcmHookCallsForStudy()).append('\\n');
        report.append("pcmProbeNonNullBuffers=").append(PlayerVolumePatch.getPcmNonNullBuffersForStudy()).append('\\n');
        report.append("pcmProbeNullBuffers=").append(PlayerVolumePatch.getPcmNullBuffersForStudy()).append('\\n');
        report.append("pcmProbeNonEmptyBuffers=").append(PlayerVolumePatch.getPcmNonEmptyBuffersForStudy()).append('\\n');
        report.append("pcmProbeEmptyBuffers=").append(PlayerVolumePatch.getPcmEmptyBuffersForStudy()).append('\\n');
        report.append("pcmProbeObservedBytes=").append(PlayerVolumePatch.getPcmObservedBytesForStudy()).append('\\n');
        report.append("pcmProbeBufferDuplicates=").append(PlayerVolumePatch.getPcmBufferDuplicatesForStudy()).append('\\n');
        report.append("pcmProbeLastPosition=").append(PlayerVolumePatch.getPcmLastPositionForStudy()).append('\\n');
        report.append("pcmProbeLastLimit=").append(PlayerVolumePatch.getPcmLastLimitForStudy()).append('\\n');
        report.append("pcmProbeLastRemaining=").append(PlayerVolumePatch.getPcmLastRemainingForStudy()).append('\\n');
        report.append("pcmProbeMaxRemaining=").append(PlayerVolumePatch.getPcmMaxRemainingForStudy()).append('\\n');
'''
    rep(controller, old_diag, new_diag, "publish Stage-B PCM metadata counters")

    print("v2.32.4 Stage-B PCM metadata probe complete")
    print("UNCHANGED: AudioTrack.write hook point, English-source repair, mergeIntoSentences, 1500/350 OpenRouter batching, subtitles, TTS")
    print("NOT ADDED: PCM sample reads/copies, arrays, logging on audio thread, worker threads, FFT, VAD, clustering, speaker assignment")


if __name__ == "__main__":
    main()
