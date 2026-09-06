#!/usr/bin/env python3
"""v2.32.8: Stage-F short speaker-feature windows on top of proven v2.32.7 PCM16 analysis.

Stage E proved stable in-place PCM16 decoding over every AudioTrack ByteBuffer with zero format
skips and zero decode errors. Stage F keeps that exact capture path and adds sparse, bounded
speaker-oriented feature extraction on the same existing PlayerVolumePatch class.

Every fifth voice-candidate buffer, Stage F copies at most 1024 decoded mono samples into one
small preallocated static short[] scratch buffer, estimates coarse pitch/autocorrelation and a
7-point Goertzel spectral profile, and aggregates those measurements into independent ~800 ms
feature windows. The windows remain diagnostic-only: no clustering, speaker assignment, subtitle
labels, or voice routing are introduced yet.

No new runtime class, no executor/worker thread, no byte[] PCM copies, no logging from the audio
thread, no Morphe segmentation/translation/TTS/subtitle changes.
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
        raise SystemExit("usage: patch_v2328_speaker_features_stage_f.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for path in (player_volume, controller):
        if not path.is_file():
            raise RuntimeError(f"missing v2.32.7 source: {path}")

    rep(
        player_volume,
        "    private static volatile long studyPcmVoiceLastWindowCandidateMs;\n",
        "    private static volatile long studyPcmVoiceLastWindowCandidateMs;\n"
        "    private static final int STUDY_SPEAKER_FEATURE_STRIDE = 5;\n"
        "    private static final int STUDY_SPEAKER_FEATURE_MAX_MONO = 1024;\n"
        "    private static final int STUDY_SPEAKER_FEATURE_WINDOW_MS = 800;\n"
        "    private static final int STUDY_SPEAKER_FEATURE_MIN_VOICE_MS = 480;\n"
        "    private static final int STUDY_SPEAKER_FEATURE_MIN_SAMPLES = 4;\n"
        "    private static final short[] studySpeakerMonoScratch = new short[STUDY_SPEAKER_FEATURE_MAX_MONO];\n"
        "    private static final double[] studySpeakerWindowBandSums = new double[7];\n"
        "    private static final int[] studySpeakerLastBandPermille = new int[7];\n"
        "    private static volatile long studySpeakerFeatureCandidateTicks;\n"
        "    private static volatile long studySpeakerFeatureAttempts;\n"
        "    private static volatile long studySpeakerFeatureSuccess;\n"
        "    private static volatile long studySpeakerFeatureErrors;\n"
        "    private static volatile long studySpeakerFeatureWindows;\n"
        "    private static volatile long studySpeakerFeatureValidWindows;\n"
        "    private static volatile long studySpeakerFeatureRejectedWindows;\n"
        "    private static volatile long studySpeakerFeatureWindowElapsedMs;\n"
        "    private static volatile long studySpeakerFeatureWindowVoiceMs;\n"
        "    private static volatile int studySpeakerFeatureWindowSamples;\n"
        "    private static volatile double studySpeakerWindowPitchWeightedHz;\n"
        "    private static volatile double studySpeakerWindowPitchWeight;\n"
        "    private static volatile double studySpeakerWindowPitchConfidenceSum;\n"
        "    private static volatile double studySpeakerWindowCentroidHzSum;\n"
        "    private static volatile double studySpeakerWindowZcrPermilleSum;\n"
        "    private static volatile long studySpeakerFeatureLastWindowVoiceMs;\n"
        "    private static volatile int studySpeakerFeatureLastWindowSamples;\n"
        "    private static volatile int studySpeakerFeatureLastPitchHz;\n"
        "    private static volatile int studySpeakerFeatureLastPitchConfidencePermille;\n"
        "    private static volatile int studySpeakerFeatureLastCentroidHz;\n"
        "    private static volatile int studySpeakerFeatureLastZcrPermille;\n"
        "    private static volatile int studySpeakerFeatureLastLowPermille;\n"
        "    private static volatile int studySpeakerFeatureLastMidPermille;\n"
        "    private static volatile int studySpeakerFeatureLastHighPermille;\n"
        "    private static volatile int studySpeakerFeatureMinPitchHz = Integer.MAX_VALUE;\n"
        "    private static volatile int studySpeakerFeatureMaxPitchHz;\n"
        "    private static volatile int studySpeakerFeatureMinCentroidHz = Integer.MAX_VALUE;\n"
        "    private static volatile int studySpeakerFeatureMaxCentroidHz;\n"
        "    private static volatile long studySpeakerFeatureRollingHash = 1469598103934665603L;\n",
        "add Stage-F speaker-feature state",
    )

    window_anchor = '''            if (studyPcmVoiceWindowAccumulatedMs >= STUDY_PCM_VOICE_WINDOW_MS) {
'''
    window_insert = '''            // Stage F: independent ~800 ms speaker-feature windows. Feature extraction itself
            // is sparse (every fifth voice-candidate buffer) and uses a single preallocated
            // short[] scratch array. No byte[] copy, no allocation per callback, no worker thread.
            studySpeakerFeatureWindowElapsedMs += durationMs;
            if (voiceCandidate) {
                studySpeakerFeatureWindowVoiceMs += durationMs;
                studySpeakerFeatureCandidateTicks++;
                if ((studySpeakerFeatureCandidateTicks % STUDY_SPEAKER_FEATURE_STRIDE) == 0) {
                    studyAnalyzeSpeakerFeatureSample(view, position, frameCount, bytesPerFrame,
                            channels, sampleRateHz, zcrPermille);
                }
            }
            if (studySpeakerFeatureWindowElapsedMs >= STUDY_SPEAKER_FEATURE_WINDOW_MS) {
                studyFinalizeSpeakerFeatureWindow();
            }

            if (studyPcmVoiceWindowAccumulatedMs >= STUDY_PCM_VOICE_WINDOW_MS) {
'''
    rep(player_volume, window_anchor, window_insert, "add Stage-F sparse feature-window sampling")

    helper_anchor = '''    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
'''
    helper_insert = '''    private static void studyAnalyzeSpeakerFeatureSample(ByteBuffer view, int position,
            int frameCount, int bytesPerFrame, int channels, int sampleRateHz, int zcrPermille) {
        studySpeakerFeatureAttempts++;
        try {
            final int n = Math.min(frameCount, STUDY_SPEAKER_FEATURE_MAX_MONO);
            if (n < 256 || sampleRateHz < 8000) return;

            long sum = 0L;
            for (int frame = 0; frame < n; frame++) {
                final int frameOffset = position + (frame * bytesPerFrame);
                long channelSum = 0L;
                for (int channel = 0; channel < channels; channel++) {
                    final int sampleOffset = frameOffset + (channel * 2);
                    final int lo = view.get(sampleOffset) & 0xFF;
                    final int hi = view.get(sampleOffset + 1);
                    final short sample = (short) ((hi << 8) | lo);
                    channelSum += sample;
                }
                final short mono = (short) (channelSum / channels);
                studySpeakerMonoScratch[frame] = mono;
                sum += mono;
            }
            final double mean = sum / (double) n;

            final int minLag = Math.max(2, sampleRateHz / 320);
            final int maxLag = Math.min(n / 2, sampleRateHz / 80);
            double bestCorr = 0.0;
            int bestLag = 0;
            for (int lag = minLag; lag <= maxLag; lag += 4) {
                double num = 0.0, a = 0.0, b = 0.0;
                for (int i = 0; i + lag < n; i += 4) {
                    final double p = studySpeakerMonoScratch[i] - mean;
                    final double q = studySpeakerMonoScratch[i + lag] - mean;
                    num += p * q;
                    a += p * p;
                    b += q * q;
                }
                final double denom = Math.sqrt(Math.max(1.0, a * b));
                final double corr = num / denom;
                if (corr > bestCorr) {
                    bestCorr = corr;
                    bestLag = lag;
                }
            }
            final double pitchHz = bestLag > 0 && bestCorr >= 0.18
                    ? sampleRateHz / (double) bestLag : 0.0;
            final double pitchConfidence = Math.max(0.0, Math.min(1.0, bestCorr));

            final double b0 = studyGoertzelPower(n, mean, sampleRateHz, 125.0);
            final double b1 = studyGoertzelPower(n, mean, sampleRateHz, 250.0);
            final double b2 = studyGoertzelPower(n, mean, sampleRateHz, 500.0);
            final double b3 = studyGoertzelPower(n, mean, sampleRateHz, 1000.0);
            final double b4 = studyGoertzelPower(n, mean, sampleRateHz, 2000.0);
            final double b5 = studyGoertzelPower(n, mean, sampleRateHz, 4000.0);
            final double b6 = studyGoertzelPower(n, mean, sampleRateHz, 6000.0);
            final double total = b0 + b1 + b2 + b3 + b4 + b5 + b6 + 1e-9;
            final double[] sums = studySpeakerWindowBandSums;
            sums[0] += b0 / total;
            sums[1] += b1 / total;
            sums[2] += b2 / total;
            sums[3] += b3 / total;
            sums[4] += b4 / total;
            sums[5] += b5 / total;
            sums[6] += b6 / total;

            final double centroidHz = (125.0 * b0 + 250.0 * b1 + 500.0 * b2
                    + 1000.0 * b3 + 2000.0 * b4 + 4000.0 * b5 + 6000.0 * b6) / total;
            if (pitchHz > 0.0) {
                studySpeakerWindowPitchWeightedHz += pitchHz * pitchConfidence;
                studySpeakerWindowPitchWeight += pitchConfidence;
            }
            studySpeakerWindowPitchConfidenceSum += pitchConfidence;
            studySpeakerWindowCentroidHzSum += centroidHz;
            studySpeakerWindowZcrPermilleSum += zcrPermille;
            studySpeakerFeatureWindowSamples++;
            studySpeakerFeatureSuccess++;
        } catch (Throwable ignored) {
            studySpeakerFeatureErrors++;
        }
    }

    private static double studyGoertzelPower(int n, double mean, int sampleRateHz, double frequencyHz) {
        final double omega = (2.0 * Math.PI * frequencyHz) / sampleRateHz;
        final double coeff = 2.0 * Math.cos(omega);
        double q1 = 0.0, q2 = 0.0;
        for (int i = 0; i < n; i++) {
            final double sample = studySpeakerMonoScratch[i] - mean;
            final double q0 = (coeff * q1) - q2 + sample;
            q2 = q1;
            q1 = q0;
        }
        return Math.max(0.0, (q1 * q1) + (q2 * q2) - (coeff * q1 * q2));
    }

    private static void studyFinalizeSpeakerFeatureWindow() {
        studySpeakerFeatureWindows++;
        final int samples = studySpeakerFeatureWindowSamples;
        final long voiceMs = studySpeakerFeatureWindowVoiceMs;
        studySpeakerFeatureLastWindowVoiceMs = voiceMs;
        studySpeakerFeatureLastWindowSamples = samples;

        if (voiceMs >= STUDY_SPEAKER_FEATURE_MIN_VOICE_MS
                && samples >= STUDY_SPEAKER_FEATURE_MIN_SAMPLES) {
            studySpeakerFeatureValidWindows++;
            final double inv = 1.0 / samples;
            double bandTotal = 0.0;
            for (int i = 0; i < 7; i++) bandTotal += studySpeakerWindowBandSums[i] * inv;
            bandTotal = Math.max(1e-9, bandTotal);
            for (int i = 0; i < 7; i++) {
                studySpeakerLastBandPermille[i] = (int) Math.round(
                        ((studySpeakerWindowBandSums[i] * inv) / bandTotal) * 1000.0);
            }

            final int pitchHz = studySpeakerWindowPitchWeight > 0.25
                    ? (int) Math.round(studySpeakerWindowPitchWeightedHz / studySpeakerWindowPitchWeight)
                    : 0;
            final int pitchConfidencePermille = (int) Math.round(
                    Math.min(1.0, studySpeakerWindowPitchConfidenceSum * inv) * 1000.0);
            final int centroidHz = (int) Math.round(studySpeakerWindowCentroidHzSum * inv);
            final int zcrPermille = (int) Math.round(studySpeakerWindowZcrPermilleSum * inv);
            final int low = studySpeakerLastBandPermille[0] + studySpeakerLastBandPermille[1]
                    + studySpeakerLastBandPermille[2];
            final int mid = studySpeakerLastBandPermille[3] + studySpeakerLastBandPermille[4];
            final int high = studySpeakerLastBandPermille[5] + studySpeakerLastBandPermille[6];

            studySpeakerFeatureLastPitchHz = pitchHz;
            studySpeakerFeatureLastPitchConfidencePermille = pitchConfidencePermille;
            studySpeakerFeatureLastCentroidHz = centroidHz;
            studySpeakerFeatureLastZcrPermille = zcrPermille;
            studySpeakerFeatureLastLowPermille = low;
            studySpeakerFeatureLastMidPermille = mid;
            studySpeakerFeatureLastHighPermille = high;
            if (pitchHz > 0) {
                if (pitchHz < studySpeakerFeatureMinPitchHz) studySpeakerFeatureMinPitchHz = pitchHz;
                if (pitchHz > studySpeakerFeatureMaxPitchHz) studySpeakerFeatureMaxPitchHz = pitchHz;
            }
            if (centroidHz > 0) {
                if (centroidHz < studySpeakerFeatureMinCentroidHz) studySpeakerFeatureMinCentroidHz = centroidHz;
                if (centroidHz > studySpeakerFeatureMaxCentroidHz) studySpeakerFeatureMaxCentroidHz = centroidHz;
            }

            long hash = studySpeakerFeatureRollingHash;
            hash = (hash ^ pitchHz) * 1099511628211L;
            hash = (hash ^ pitchConfidencePermille) * 1099511628211L;
            hash = (hash ^ centroidHz) * 1099511628211L;
            hash = (hash ^ zcrPermille) * 1099511628211L;
            for (int i = 0; i < 7; i++) hash = (hash ^ studySpeakerLastBandPermille[i]) * 1099511628211L;
            studySpeakerFeatureRollingHash = hash;
        } else {
            studySpeakerFeatureRejectedWindows++;
        }

        studySpeakerFeatureWindowElapsedMs = 0L;
        studySpeakerFeatureWindowVoiceMs = 0L;
        studySpeakerFeatureWindowSamples = 0;
        studySpeakerWindowPitchWeightedHz = 0.0;
        studySpeakerWindowPitchWeight = 0.0;
        studySpeakerWindowPitchConfidenceSum = 0.0;
        studySpeakerWindowCentroidHzSum = 0.0;
        studySpeakerWindowZcrPermilleSum = 0.0;
        for (int i = 0; i < 7; i++) studySpeakerWindowBandSums[i] = 0.0;
    }

    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
'''
    rep(player_volume, helper_anchor, helper_insert, "add Stage-F pitch/spectral feature helpers")

    getter_anchor = '''    public static long getPcmVoiceLastWindowCandidateMsForStudy() { return studyPcmVoiceLastWindowCandidateMs; }

'''
    getter_insert = '''    public static long getPcmVoiceLastWindowCandidateMsForStudy() { return studyPcmVoiceLastWindowCandidateMs; }
    public static int getSpeakerFeatureStrideForStudy() { return STUDY_SPEAKER_FEATURE_STRIDE; }
    public static int getSpeakerFeatureMaxMonoForStudy() { return STUDY_SPEAKER_FEATURE_MAX_MONO; }
    public static int getSpeakerFeatureWindowMsForStudy() { return STUDY_SPEAKER_FEATURE_WINDOW_MS; }
    public static int getSpeakerFeatureMinVoiceMsForStudy() { return STUDY_SPEAKER_FEATURE_MIN_VOICE_MS; }
    public static int getSpeakerFeatureMinSamplesForStudy() { return STUDY_SPEAKER_FEATURE_MIN_SAMPLES; }
    public static long getSpeakerFeatureAttemptsForStudy() { return studySpeakerFeatureAttempts; }
    public static long getSpeakerFeatureSuccessForStudy() { return studySpeakerFeatureSuccess; }
    public static long getSpeakerFeatureErrorsForStudy() { return studySpeakerFeatureErrors; }
    public static long getSpeakerFeatureWindowsForStudy() { return studySpeakerFeatureWindows; }
    public static long getSpeakerFeatureValidWindowsForStudy() { return studySpeakerFeatureValidWindows; }
    public static long getSpeakerFeatureRejectedWindowsForStudy() { return studySpeakerFeatureRejectedWindows; }
    public static long getSpeakerFeatureLastWindowVoiceMsForStudy() { return studySpeakerFeatureLastWindowVoiceMs; }
    public static int getSpeakerFeatureLastWindowSamplesForStudy() { return studySpeakerFeatureLastWindowSamples; }
    public static int getSpeakerFeatureLastPitchHzForStudy() { return studySpeakerFeatureLastPitchHz; }
    public static int getSpeakerFeatureLastPitchConfidencePermilleForStudy() { return studySpeakerFeatureLastPitchConfidencePermille; }
    public static int getSpeakerFeatureLastCentroidHzForStudy() { return studySpeakerFeatureLastCentroidHz; }
    public static int getSpeakerFeatureLastZcrPermilleForStudy() { return studySpeakerFeatureLastZcrPermille; }
    public static int getSpeakerFeatureLastLowPermilleForStudy() { return studySpeakerFeatureLastLowPermille; }
    public static int getSpeakerFeatureLastMidPermilleForStudy() { return studySpeakerFeatureLastMidPermille; }
    public static int getSpeakerFeatureLastHighPermilleForStudy() { return studySpeakerFeatureLastHighPermille; }
    public static int getSpeakerFeatureLastBandPermilleForStudy(int index) {
        return index >= 0 && index < studySpeakerLastBandPermille.length ? studySpeakerLastBandPermille[index] : 0;
    }
    public static int getSpeakerFeatureMinPitchHzForStudy() { return studySpeakerFeatureMinPitchHz == Integer.MAX_VALUE ? 0 : studySpeakerFeatureMinPitchHz; }
    public static int getSpeakerFeatureMaxPitchHzForStudy() { return studySpeakerFeatureMaxPitchHz; }
    public static int getSpeakerFeatureMinCentroidHzForStudy() { return studySpeakerFeatureMinCentroidHz == Integer.MAX_VALUE ? 0 : studySpeakerFeatureMinCentroidHz; }
    public static int getSpeakerFeatureMaxCentroidHzForStudy() { return studySpeakerFeatureMaxCentroidHz; }
    public static long getSpeakerFeatureRollingHashForStudy() { return studySpeakerFeatureRollingHash; }

'''
    rep(player_volume, getter_anchor, getter_insert, "publish Stage-F speaker-feature getters")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.7 Stage-E PCM16 voice-analysis diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.8 Stage-F speaker-feature diagnostics\\n");',
        "update Stage-F diagnostics header",
    )

    diag_anchor = '''        report.append("speakerPcmDiarizationStatus=pre-clustering-real-pcm-voice-candidate-analysis\\n");
'''
    diag_insert = '''        report.append("speakerPcmDiarizationStatus=pre-clustering-short-speaker-feature-windows\\n");
        report.append("speakerFeatureBackend=pcm16-autocorrelation+7point-goertzel-diagnostic-only\\n");
        report.append("speakerFeatureWorkerThreads=0\\n");
        report.append("speakerFeatureByteArrayCopies=0\\n");
        report.append("speakerFeatureStaticMonoScratchSamples=").append(PlayerVolumePatch.getSpeakerFeatureMaxMonoForStudy()).append('\\n');
        report.append("speakerFeatureStride=").append(PlayerVolumePatch.getSpeakerFeatureStrideForStudy()).append('\\n');
        report.append("speakerFeatureWindowMs=").append(PlayerVolumePatch.getSpeakerFeatureWindowMsForStudy()).append('\\n');
        report.append("speakerFeatureMinVoiceMs=").append(PlayerVolumePatch.getSpeakerFeatureMinVoiceMsForStudy()).append('\\n');
        report.append("speakerFeatureMinSamples=").append(PlayerVolumePatch.getSpeakerFeatureMinSamplesForStudy()).append('\\n');
        report.append("speakerFeatureAttempts=").append(PlayerVolumePatch.getSpeakerFeatureAttemptsForStudy()).append('\\n');
        report.append("speakerFeatureSuccess=").append(PlayerVolumePatch.getSpeakerFeatureSuccessForStudy()).append('\\n');
        report.append("speakerFeatureErrors=").append(PlayerVolumePatch.getSpeakerFeatureErrorsForStudy()).append('\\n');
        report.append("speakerFeatureWindows=").append(PlayerVolumePatch.getSpeakerFeatureWindowsForStudy()).append('\\n');
        report.append("speakerFeatureValidWindows=").append(PlayerVolumePatch.getSpeakerFeatureValidWindowsForStudy()).append('\\n');
        report.append("speakerFeatureRejectedWindows=").append(PlayerVolumePatch.getSpeakerFeatureRejectedWindowsForStudy()).append('\\n');
        report.append("speakerFeatureLastWindowVoiceMs=").append(PlayerVolumePatch.getSpeakerFeatureLastWindowVoiceMsForStudy()).append('\\n');
        report.append("speakerFeatureLastWindowSamples=").append(PlayerVolumePatch.getSpeakerFeatureLastWindowSamplesForStudy()).append('\\n');
        report.append("speakerFeatureLastPitchHz=").append(PlayerVolumePatch.getSpeakerFeatureLastPitchHzForStudy()).append('\\n');
        report.append("speakerFeatureLastPitchConfidencePermille=").append(PlayerVolumePatch.getSpeakerFeatureLastPitchConfidencePermilleForStudy()).append('\\n');
        report.append("speakerFeatureLastCentroidHz=").append(PlayerVolumePatch.getSpeakerFeatureLastCentroidHzForStudy()).append('\\n');
        report.append("speakerFeatureLastZcrPermille=").append(PlayerVolumePatch.getSpeakerFeatureLastZcrPermilleForStudy()).append('\\n');
        report.append("speakerFeatureLastLowPermille=").append(PlayerVolumePatch.getSpeakerFeatureLastLowPermilleForStudy()).append('\\n');
        report.append("speakerFeatureLastMidPermille=").append(PlayerVolumePatch.getSpeakerFeatureLastMidPermilleForStudy()).append('\\n');
        report.append("speakerFeatureLastHighPermille=").append(PlayerVolumePatch.getSpeakerFeatureLastHighPermilleForStudy()).append('\\n');
        report.append("speakerFeatureLastBandsPermille=")
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(0)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(1)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(2)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(3)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(4)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(5)).append(',')
                .append(PlayerVolumePatch.getSpeakerFeatureLastBandPermilleForStudy(6)).append('\\n');
        report.append("speakerFeaturePitchRangeHz=").append(PlayerVolumePatch.getSpeakerFeatureMinPitchHzForStudy())
                .append('-').append(PlayerVolumePatch.getSpeakerFeatureMaxPitchHzForStudy()).append('\\n');
        report.append("speakerFeatureCentroidRangeHz=").append(PlayerVolumePatch.getSpeakerFeatureMinCentroidHzForStudy())
                .append('-').append(PlayerVolumePatch.getSpeakerFeatureMaxCentroidHzForStudy()).append('\\n');
        report.append("speakerFeatureRollingHash=").append(PlayerVolumePatch.getSpeakerFeatureRollingHashForStudy()).append('\\n');
        report.append("speakerFeatureClustering=disabled-stage-f\\n");
        report.append("speakerFeatureAssignment=disabled-stage-f\\n");
'''
    rep(controller, diag_anchor, diag_insert, "publish Stage-F speaker-feature diagnostics")

    print("v2.32.8 Stage-F short speaker-feature windows complete")
    print("UNCHANGED: decoded PCM hook geometry, Stage-E PCM16 VAD, mergeIntoSentences, 1500/350 OpenRouter packets, subtitles, TTS")
    print("NOT ADDED: runtime helper class, executor, byte[] PCM copy, clustering, speaker labels/assignment, voice routing")


if __name__ == "__main__":
    main()
