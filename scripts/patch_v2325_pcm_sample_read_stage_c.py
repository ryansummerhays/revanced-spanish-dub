#!/usr/bin/env python3
"""v2.32.5: Stage-C sparse bounded PCM byte-read probe on top of v2.32.4.

This advances exactly one step beyond Stage B. The existing duplicated decoded ByteBuffer is
sampled very sparsely (every 32nd hook call), reading at most 64 bytes with absolute get(index)
operations. Reads do not change the duplicate's position and cannot mutate the original playback
buffer. No byte arrays, buffer copies, PCM16/float decoding, AudioTrack format assumptions,
logging on the audio thread, worker threads, FFT, VAD, clustering, speaker assignment, or voice
routing are introduced.
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
        raise SystemExit("usage: patch_v2325_pcm_sample_read_stage_c.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    if not player_volume.is_file() or not controller.is_file():
        raise RuntimeError("missing v2.32.4 source tree")

    rep(
        player_volume,
        "    private static volatile int studyPcmMaxRemaining;\n",
        "    private static volatile int studyPcmMaxRemaining;\n"
        "    private static final int STUDY_PCM_SAMPLE_STRIDE = 32;\n"
        "    private static final int STUDY_PCM_SAMPLE_MAX_BYTES = 64;\n"
        "    private static volatile long studyPcmSampleReadCalls;\n"
        "    private static volatile long studyPcmSampleBytesRead;\n"
        "    private static volatile long studyPcmSampleZeroBytes;\n"
        "    private static volatile long studyPcmSampleNonZeroBytes;\n"
        "    private static volatile long studyPcmSampleReadErrors;\n"
        "    private static volatile long studyPcmSampleRollingHash = 1125899906842597L;\n",
        "add Stage-C sparse sample-read counters",
    )

    old_tail = '''        if (remaining > 0) {
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
    new_tail = '''        if (remaining > 0) {
            studyPcmNonEmptyBuffers++;
            studyPcmObservedBytes += remaining;
        } else {
            studyPcmEmptyBuffers++;
        }

        // Stage C intentionally samples only 1/32 callbacks and at most 64 bytes. Absolute
        // ByteBuffer.get(index) reads leave both the original and duplicated positions untouched.
        if (remaining > 0 && (studyPcmHookCalls % STUDY_PCM_SAMPLE_STRIDE) == 0) {
            final int bytesToRead = Math.min(remaining, STUDY_PCM_SAMPLE_MAX_BYTES);
            final int start = position;
            studyPcmSampleReadCalls++;
            try {
                long hash = studyPcmSampleRollingHash;
                long zero = 0;
                long nonZero = 0;
                for (int i = 0; i < bytesToRead; i++) {
                    int value = view.get(start + i) & 0xFF;
                    if (value == 0) zero++;
                    else nonZero++;
                    hash = (hash * 1315423911L) ^ value;
                }
                studyPcmSampleBytesRead += bytesToRead;
                studyPcmSampleZeroBytes += zero;
                studyPcmSampleNonZeroBytes += nonZero;
                studyPcmSampleRollingHash = hash;
            } catch (RuntimeException ex) {
                // Diagnostic probe must fail soft on the audio thread.
                studyPcmSampleReadErrors++;
            }
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
    public static int getPcmSampleStrideForStudy() { return STUDY_PCM_SAMPLE_STRIDE; }
    public static int getPcmSampleMaxBytesForStudy() { return STUDY_PCM_SAMPLE_MAX_BYTES; }
    public static long getPcmSampleReadCallsForStudy() { return studyPcmSampleReadCalls; }
    public static long getPcmSampleBytesReadForStudy() { return studyPcmSampleBytesRead; }
    public static long getPcmSampleZeroBytesForStudy() { return studyPcmSampleZeroBytes; }
    public static long getPcmSampleNonZeroBytesForStudy() { return studyPcmSampleNonZeroBytes; }
    public static long getPcmSampleReadErrorsForStudy() { return studyPcmSampleReadErrors; }
    public static long getPcmSampleRollingHashForStudy() { return studyPcmSampleRollingHash; }

'''
    rep(player_volume, old_tail, new_tail, "add sparse bounded absolute sample reads")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.4 Stage-B PCM metadata diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.5 Stage-C PCM sample-read diagnostics\\n");',
        "update Stage-C diagnostics header",
    )

    old_diag = '''        report.append("pcmProbe=audio-track-write-bytebuffer-metadata-only\\n");
        report.append("pcmProbeSampleReads=0\\n");
        report.append("pcmProbeBufferCopies=0\\n");
        report.append("pcmProbeWorkerThreads=0\\n");
'''
    new_diag = '''        report.append("pcmProbe=audio-track-write-bytebuffer-sparse-bounded-read\\n");
        report.append("pcmProbeBufferCopies=0\\n");
        report.append("pcmProbeWorkerThreads=0\\n");
        report.append("pcmProbeSampleStride=").append(PlayerVolumePatch.getPcmSampleStrideForStudy()).append('\\n');
        report.append("pcmProbeSampleMaxBytes=").append(PlayerVolumePatch.getPcmSampleMaxBytesForStudy()).append('\\n');
        report.append("pcmProbeSampleReadCalls=").append(PlayerVolumePatch.getPcmSampleReadCallsForStudy()).append('\\n');
        report.append("pcmProbeSampleBytesRead=").append(PlayerVolumePatch.getPcmSampleBytesReadForStudy()).append('\\n');
        report.append("pcmProbeSampleZeroBytes=").append(PlayerVolumePatch.getPcmSampleZeroBytesForStudy()).append('\\n');
        report.append("pcmProbeSampleNonZeroBytes=").append(PlayerVolumePatch.getPcmSampleNonZeroBytesForStudy()).append('\\n');
        report.append("pcmProbeSampleReadErrors=").append(PlayerVolumePatch.getPcmSampleReadErrorsForStudy()).append('\\n');
        report.append("pcmProbeSampleRollingHash=").append(PlayerVolumePatch.getPcmSampleRollingHashForStudy()).append('\\n');
'''
    rep(controller, old_diag, new_diag, "publish Stage-C sparse sample-read counters")

    print("v2.32.5 Stage-C sparse bounded sample-read probe complete")
    print("UNCHANGED: one-register AudioTrack.write hook, English-source repair, mergeIntoSentences, 1500/350 OpenRouter batching, subtitles, TTS")
    print("NOT ADDED: byte arrays/copies, PCM decoding, format assumptions, audio-thread logging, workers, FFT, VAD, clustering, speaker assignment")


if __name__ == "__main__":
    main()
