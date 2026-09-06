#!/usr/bin/env python3
"""v2.32.7: Stage-E bounded PCM16 voice-candidate analysis on top of v2.32.6.

v2.32.6 proved the exact AudioTrack receiver is stable and reports 48 kHz, 2-channel,
ENCODING_PCM_16BIT (2), while the proven decoded ByteBuffer remains readable with no errors.
Stage E therefore advances one step: decode the observed PCM16 frames directly from the duplicated
ByteBuffer and calculate lightweight, allocation-free energy / peak / zero-crossing features.
Those features feed a deliberately conservative *voice-candidate* gate and ~1 s activity windows.
This is not yet speaker clustering and it does not claim accurate diarization.

The work remains on the existing PlayerVolumePatch class, uses no new class/static executor, makes
no byte-array copies, creates no worker thread, and fails soft on the ExoPlayer audio thread.
No FFT, embedding model, clustering, speaker assignment, voice routing, subtitle changes,
translation packet changes, or TTS changes are introduced.
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
        raise SystemExit("usage: patch_v2327_pcm16_vad_stage_e.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for path in (player_volume, controller):
        if not path.is_file():
            raise RuntimeError(f"missing v2.32.6 source: {path}")

    rep(
        player_volume,
        "    private static volatile int studyAudioTrackPlayState = -1;\n",
        "    private static volatile int studyAudioTrackPlayState = -1;\n"
        "    private static final int STUDY_PCM16_ENCODING = 2;\n"
        "    private static final int STUDY_PCM_ANALYSIS_MAX_FRAMES = 2048;\n"
        "    private static final int STUDY_PCM_VOICE_MIN_RMS_PERMILLE = 10;\n"
        "    private static final int STUDY_PCM_VOICE_MIN_PEAK_PERMILLE = 18;\n"
        "    private static final int STUDY_PCM_VOICE_MAX_ZCR_PERMILLE = 500;\n"
        "    private static final int STUDY_PCM_VOICE_WINDOW_MS = 1000;\n"
        "    private static final int STUDY_PCM_VOICE_WINDOW_MIN_ACTIVE_MS = 250;\n"
        "    private static volatile long studyPcmAnalysisCalls;\n"
        "    private static volatile long studyPcmAnalysisEligibleBuffers;\n"
        "    private static volatile long studyPcmAnalysisFormatSkips;\n"
        "    private static volatile long studyPcmAnalysisDecodeErrors;\n"
        "    private static volatile long studyPcmAnalysisDecodedFrames;\n"
        "    private static volatile long studyPcmVoiceCandidateBuffers;\n"
        "    private static volatile long studyPcmVoiceQuietBuffers;\n"
        "    private static volatile long studyPcmVoiceCandidateMs;\n"
        "    private static volatile int studyPcmVoiceLastRmsPermille;\n"
        "    private static volatile int studyPcmVoiceMaxRmsPermille;\n"
        "    private static volatile int studyPcmVoiceLastPeakPermille;\n"
        "    private static volatile int studyPcmVoiceMaxPeakPermille;\n"
        "    private static volatile int studyPcmVoiceLastZcrPermille;\n"
        "    private static volatile int studyPcmVoiceNoiseFloorPermille = 4;\n"
        "    private static volatile int studyPcmVoiceLastThresholdPermille = STUDY_PCM_VOICE_MIN_RMS_PERMILLE;\n"
        "    private static volatile long studyPcmVoiceWindows;\n"
        "    private static volatile long studyPcmVoiceActiveWindows;\n"
        "    private static volatile long studyPcmVoiceQuietWindows;\n"
        "    private static volatile long studyPcmVoiceWindowAccumulatedMs;\n"
        "    private static volatile long studyPcmVoiceWindowCandidateMs;\n"
        "    private static volatile long studyPcmVoiceLastWindowCandidateMs;\n",
        "add Stage-E PCM16 voice-analysis state",
    )

    old_tail = '''            } catch (RuntimeException ex) {
                // Diagnostic probe must fail soft on the audio thread.
                studyPcmSampleReadErrors++;
            }
        }
    }

    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
'''
    new_tail = '''            } catch (RuntimeException ex) {
                // Diagnostic probe must fail soft on the audio thread.
                studyPcmSampleReadErrors++;
            }
        }

        // Stage E: the previous receiver probe established PCM16 and the exact channel/sample
        // metadata. Decode directly from the duplicate using explicit little-endian PCM16 reads.
        // No arrays/copies/allocations are created here. Work is bounded to 2048 frames.
        studyPcmAnalysisCalls++;
        final int sampleRateHz = studyAudioTrackSampleRateHz;
        final int channels = studyAudioTrackChannelCount;
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
                || sampleRateHz <= 0
                || channels <= 0
                || channels > 8
                || remaining < channels * 2) {
            studyPcmAnalysisFormatSkips++;
            return;
        }

        final int bytesPerFrame = channels * 2;
        int frameCount = remaining / bytesPerFrame;
        if (frameCount <= 0) {
            studyPcmAnalysisFormatSkips++;
            return;
        }
        frameCount = Math.min(frameCount, STUDY_PCM_ANALYSIS_MAX_FRAMES);
        studyPcmAnalysisEligibleBuffers++;

        try {
            long sumSquares = 0L;
            int peakAbs = 0;
            int zeroCrossings = 0;
            int previousMono = 0;
            boolean havePrevious = false;

            for (int frame = 0; frame < frameCount; frame++) {
                final int frameOffset = position + (frame * bytesPerFrame);
                long channelSum = 0L;
                for (int channel = 0; channel < channels; channel++) {
                    final int sampleOffset = frameOffset + (channel * 2);
                    final int lo = view.get(sampleOffset) & 0xFF;
                    final int hi = view.get(sampleOffset + 1);
                    final short sample = (short) ((hi << 8) | lo);
                    channelSum += sample;
                }

                final int mono = (int) (channelSum / channels);
                final int abs = mono == Short.MIN_VALUE ? 32768 : Math.abs(mono);
                if (abs > peakAbs) peakAbs = abs;
                sumSquares += (long) mono * (long) mono;

                if (havePrevious && ((previousMono < 0 && mono >= 0) || (previousMono >= 0 && mono < 0))) {
                    zeroCrossings++;
                }
                previousMono = mono;
                havePrevious = true;
            }

            final double meanSquare = sumSquares / (double) frameCount;
            final int rmsPermille = (int) Math.min(1000.0,
                    Math.round((Math.sqrt(meanSquare) * 1000.0) / 32768.0));
            final int peakPermille = (int) Math.min(1000L,
                    Math.round((peakAbs * 1000.0) / 32768.0));
            final int zcrPermille = frameCount <= 1 ? 0
                    : (int) Math.min(1000L, Math.round((zeroCrossings * 1000.0) / (frameCount - 1.0)));

            studyPcmAnalysisDecodedFrames += frameCount;
            studyPcmVoiceLastRmsPermille = rmsPermille;
            studyPcmVoiceLastPeakPermille = peakPermille;
            studyPcmVoiceLastZcrPermille = zcrPermille;
            if (rmsPermille > studyPcmVoiceMaxRmsPermille) studyPcmVoiceMaxRmsPermille = rmsPermille;
            if (peakPermille > studyPcmVoiceMaxPeakPermille) studyPcmVoiceMaxPeakPermille = peakPermille;

            final int adaptiveThreshold = Math.max(STUDY_PCM_VOICE_MIN_RMS_PERMILLE,
                    Math.min(120, studyPcmVoiceNoiseFloorPermille * 3));
            studyPcmVoiceLastThresholdPermille = adaptiveThreshold;
            final boolean voiceCandidate = rmsPermille >= adaptiveThreshold
                    && peakPermille >= Math.max(STUDY_PCM_VOICE_MIN_PEAK_PERMILLE, adaptiveThreshold * 2)
                    && zcrPermille <= STUDY_PCM_VOICE_MAX_ZCR_PERMILLE;

            final long durationMs = Math.max(1L, (frameCount * 1000L) / sampleRateHz);
            studyPcmVoiceWindowAccumulatedMs += durationMs;
            if (voiceCandidate) {
                studyPcmVoiceCandidateBuffers++;
                studyPcmVoiceCandidateMs += durationMs;
                studyPcmVoiceWindowCandidateMs += durationMs;
            } else {
                studyPcmVoiceQuietBuffers++;
                // Update the floor only on frames currently considered non-voice so speech does
                // not immediately drag the threshold upward. Integer EMA ~= 1/32 new sample.
                int floor = ((studyPcmVoiceNoiseFloorPermille * 31) + rmsPermille) / 32;
                studyPcmVoiceNoiseFloorPermille = Math.max(1, Math.min(100, floor));
            }

            if (studyPcmVoiceWindowAccumulatedMs >= STUDY_PCM_VOICE_WINDOW_MS) {
                studyPcmVoiceWindows++;
                studyPcmVoiceLastWindowCandidateMs = studyPcmVoiceWindowCandidateMs;
                if (studyPcmVoiceWindowCandidateMs >= STUDY_PCM_VOICE_WINDOW_MIN_ACTIVE_MS) {
                    studyPcmVoiceActiveWindows++;
                } else {
                    studyPcmVoiceQuietWindows++;
                }
                studyPcmVoiceWindowAccumulatedMs = 0L;
                studyPcmVoiceWindowCandidateMs = 0L;
            }
        } catch (Throwable ignored) {
            // This callback is on ExoPlayer's audio thread. Diagnostics must always fail soft.
            studyPcmAnalysisDecodeErrors++;
        }
    }

    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
'''
    rep(player_volume, old_tail, new_tail, "decode bounded PCM16 and classify voice-candidate windows")

    getter_anchor = '''    public static int getAudioTrackPlayStateForStudy() { return studyAudioTrackPlayState; }

'''
    getter_insert = '''    public static int getAudioTrackPlayStateForStudy() { return studyAudioTrackPlayState; }
    public static int getPcmAnalysisMaxFramesForStudy() { return STUDY_PCM_ANALYSIS_MAX_FRAMES; }
    public static int getPcmVoiceMinRmsPermilleForStudy() { return STUDY_PCM_VOICE_MIN_RMS_PERMILLE; }
    public static int getPcmVoiceMinPeakPermilleForStudy() { return STUDY_PCM_VOICE_MIN_PEAK_PERMILLE; }
    public static int getPcmVoiceMaxZcrPermilleForStudy() { return STUDY_PCM_VOICE_MAX_ZCR_PERMILLE; }
    public static int getPcmVoiceWindowMsForStudy() { return STUDY_PCM_VOICE_WINDOW_MS; }
    public static int getPcmVoiceWindowMinActiveMsForStudy() { return STUDY_PCM_VOICE_WINDOW_MIN_ACTIVE_MS; }
    public static long getPcmAnalysisCallsForStudy() { return studyPcmAnalysisCalls; }
    public static long getPcmAnalysisEligibleBuffersForStudy() { return studyPcmAnalysisEligibleBuffers; }
    public static long getPcmAnalysisFormatSkipsForStudy() { return studyPcmAnalysisFormatSkips; }
    public static long getPcmAnalysisDecodeErrorsForStudy() { return studyPcmAnalysisDecodeErrors; }
    public static long getPcmAnalysisDecodedFramesForStudy() { return studyPcmAnalysisDecodedFrames; }
    public static long getPcmVoiceCandidateBuffersForStudy() { return studyPcmVoiceCandidateBuffers; }
    public static long getPcmVoiceQuietBuffersForStudy() { return studyPcmVoiceQuietBuffers; }
    public static long getPcmVoiceCandidateMsForStudy() { return studyPcmVoiceCandidateMs; }
    public static int getPcmVoiceLastRmsPermilleForStudy() { return studyPcmVoiceLastRmsPermille; }
    public static int getPcmVoiceMaxRmsPermilleForStudy() { return studyPcmVoiceMaxRmsPermille; }
    public static int getPcmVoiceLastPeakPermilleForStudy() { return studyPcmVoiceLastPeakPermille; }
    public static int getPcmVoiceMaxPeakPermilleForStudy() { return studyPcmVoiceMaxPeakPermille; }
    public static int getPcmVoiceLastZcrPermilleForStudy() { return studyPcmVoiceLastZcrPermille; }
    public static int getPcmVoiceNoiseFloorPermilleForStudy() { return studyPcmVoiceNoiseFloorPermille; }
    public static int getPcmVoiceLastThresholdPermilleForStudy() { return studyPcmVoiceLastThresholdPermille; }
    public static long getPcmVoiceWindowsForStudy() { return studyPcmVoiceWindows; }
    public static long getPcmVoiceActiveWindowsForStudy() { return studyPcmVoiceActiveWindows; }
    public static long getPcmVoiceQuietWindowsForStudy() { return studyPcmVoiceQuietWindows; }
    public static long getPcmVoiceLastWindowCandidateMsForStudy() { return studyPcmVoiceLastWindowCandidateMs; }

'''
    rep(player_volume, getter_anchor, getter_insert, "publish Stage-E PCM16 analysis getters")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.6 Stage-D AudioTrack format diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.7 Stage-E PCM16 voice-analysis diagnostics\\n");',
        "update Stage-E diagnostics header",
    )

    diag_anchor = '''        report.append("pcmTrackPlayState=").append(PlayerVolumePatch.getAudioTrackPlayStateForStudy()).append('\\n');
'''
    diag_insert = '''        report.append("pcmTrackPlayState=").append(PlayerVolumePatch.getAudioTrackPlayStateForStudy()).append('\\n');
        report.append("pcmVoiceAnalysis=direct-pcm16-energy-peak-zcr-voice-candidate-stage-e\\n");
        report.append("pcmVoiceAnalysisByteOrder=explicit-little-endian\\n");
        report.append("pcmVoiceAnalysisWorkerThreads=0\\n");
        report.append("pcmVoiceAnalysisBufferCopies=0\\n");
        report.append("pcmVoiceAnalysisMaxFrames=").append(PlayerVolumePatch.getPcmAnalysisMaxFramesForStudy()).append('\\n');
        report.append("pcmVoiceMinRmsPermille=").append(PlayerVolumePatch.getPcmVoiceMinRmsPermilleForStudy()).append('\\n');
        report.append("pcmVoiceMinPeakPermille=").append(PlayerVolumePatch.getPcmVoiceMinPeakPermilleForStudy()).append('\\n');
        report.append("pcmVoiceMaxZcrPermille=").append(PlayerVolumePatch.getPcmVoiceMaxZcrPermilleForStudy()).append('\\n');
        report.append("pcmVoiceWindowMs=").append(PlayerVolumePatch.getPcmVoiceWindowMsForStudy()).append('\\n');
        report.append("pcmVoiceWindowMinActiveMs=").append(PlayerVolumePatch.getPcmVoiceWindowMinActiveMsForStudy()).append('\\n');
        report.append("pcmVoiceAnalysisCalls=").append(PlayerVolumePatch.getPcmAnalysisCallsForStudy()).append('\\n');
        report.append("pcmVoiceEligibleBuffers=").append(PlayerVolumePatch.getPcmAnalysisEligibleBuffersForStudy()).append('\\n');
        report.append("pcmVoiceFormatSkips=").append(PlayerVolumePatch.getPcmAnalysisFormatSkipsForStudy()).append('\\n');
        report.append("pcmVoiceDecodeErrors=").append(PlayerVolumePatch.getPcmAnalysisDecodeErrorsForStudy()).append('\\n');
        report.append("pcmVoiceDecodedFrames=").append(PlayerVolumePatch.getPcmAnalysisDecodedFramesForStudy()).append('\\n');
        report.append("pcmVoiceCandidateBuffers=").append(PlayerVolumePatch.getPcmVoiceCandidateBuffersForStudy()).append('\\n');
        report.append("pcmVoiceQuietBuffers=").append(PlayerVolumePatch.getPcmVoiceQuietBuffersForStudy()).append('\\n');
        report.append("pcmVoiceCandidateMs=").append(PlayerVolumePatch.getPcmVoiceCandidateMsForStudy()).append('\\n');
        report.append("pcmVoiceLastRmsPermille=").append(PlayerVolumePatch.getPcmVoiceLastRmsPermilleForStudy()).append('\\n');
        report.append("pcmVoiceMaxRmsPermille=").append(PlayerVolumePatch.getPcmVoiceMaxRmsPermilleForStudy()).append('\\n');
        report.append("pcmVoiceLastPeakPermille=").append(PlayerVolumePatch.getPcmVoiceLastPeakPermilleForStudy()).append('\\n');
        report.append("pcmVoiceMaxPeakPermille=").append(PlayerVolumePatch.getPcmVoiceMaxPeakPermilleForStudy()).append('\\n');
        report.append("pcmVoiceLastZcrPermille=").append(PlayerVolumePatch.getPcmVoiceLastZcrPermilleForStudy()).append('\\n');
        report.append("pcmVoiceNoiseFloorPermille=").append(PlayerVolumePatch.getPcmVoiceNoiseFloorPermilleForStudy()).append('\\n');
        report.append("pcmVoiceLastThresholdPermille=").append(PlayerVolumePatch.getPcmVoiceLastThresholdPermilleForStudy()).append('\\n');
        report.append("pcmVoiceWindows=").append(PlayerVolumePatch.getPcmVoiceWindowsForStudy()).append('\\n');
        report.append("pcmVoiceActiveWindows=").append(PlayerVolumePatch.getPcmVoiceActiveWindowsForStudy()).append('\\n');
        report.append("pcmVoiceQuietWindows=").append(PlayerVolumePatch.getPcmVoiceQuietWindowsForStudy()).append('\\n');
        report.append("pcmVoiceLastWindowCandidateMs=").append(PlayerVolumePatch.getPcmVoiceLastWindowCandidateMsForStudy()).append('\\n');
        report.append("speakerPcmDiarizationStatus=pre-clustering-real-pcm-voice-candidate-analysis\\n");
'''
    rep(controller, diag_anchor, diag_insert, "publish Stage-E real PCM voice-analysis diagnostics")

    print("v2.32.7 Stage-E PCM16 voice-candidate analysis complete")
    print("UNCHANGED: mergeIntoSentences, 1500/350 OpenRouter packetization, translation priority/order, subtitles, TTS, Stage-D hook point")
    print("NOT ADDED: byte-array copies, worker threads, FFT, embeddings, clustering, speaker assignment, voice routing")


if __name__ == "__main__":
    main()
