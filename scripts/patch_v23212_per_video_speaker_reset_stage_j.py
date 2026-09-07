#!/usr/bin/env python3
"""v2.32.12 Stage J: reset direct-PCM speaker analysis on every genuinely new video.

Stage I exposed an important validation bug: Stage-E/F/G state was process-global, so cluster
centroids and counters learned on one YouTube video carried into the next. Stage J adds a narrow
lifecycle reset after Morphe's same-video guard and before the new transcript/playback session is
started. This makes A/B/C/D clustering video-local and makes the speaker diagnostics meaningful
for one-video benchmarks.

No PCM hook, voice gate, feature math, cluster distance/threshold, subtitle logic, translation
segmentation/packetization, TTS scheduling, or Spanish-voice-toggle behavior is changed.
"""
from pathlib import Path
import sys


def rep(path: Path, old: str, new: str, label: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    found = text.count(old)
    if found != count:
        raise RuntimeError(f"{label}: expected {count} anchor(s), found {found} in {path}")
    path.write_text(text.replace(old, new, count), encoding="utf-8")
    print("patched:", label)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_v23212_per_video_speaker_reset_stage_j.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    vot = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/voiceovertranslation/VoiceOverTranslationPatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for path in (player_volume, vot, controller):
        if not path.is_file():
            raise RuntimeError(f"missing Stage-I source: {path}")

    rep(
        player_volume,
        "    private static volatile int studySpeakerClusterLastMarginPermille;\n",
        "    private static volatile int studySpeakerClusterLastMarginPermille;\n"
        "    private static volatile boolean studySpeakerAnalysisResetInProgress;\n"
        "    private static volatile long studySpeakerAnalysisEpoch;\n"
        "    private static volatile long studySpeakerAnalysisResetCount;\n"
        "    private static volatile long studySpeakerAnalysisLastResetPcmHookCalls;\n",
        "add Stage-J reset state",
    )

    # Do not let a lifecycle reset race with the audio-thread diagnostic work. This is only a
    # fail-soft guard; normal PCM observation is otherwise byte-for-byte unchanged.
    rep(
        player_volume,
        "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n        studyPcmHookCalls++;\n",
        "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n"
        "        studyPcmHookCalls++;\n"
        "        if (studySpeakerAnalysisResetInProgress) return;\n",
        "guard PCM speaker analysis during reset",
    )

    reset_method = r'''    /**
     * Clears only the direct-PCM speaker-analysis state for a genuinely new video.
     * Low-level PCM proof counters and AudioTrack metadata remain lifetime diagnostics.
     */
    public static void resetSpeakerAnalysisForStudy() {
        studySpeakerAnalysisResetInProgress = true;
        try {
            // Stage E: per-video voice gate and activity statistics.
            studyPcmAnalysisCalls = 0L;
            studyPcmAnalysisEligibleBuffers = 0L;
            studyPcmAnalysisFormatSkips = 0L;
            studyPcmAnalysisDecodeErrors = 0L;
            studyPcmAnalysisDecodedFrames = 0L;
            studyPcmVoiceCandidateBuffers = 0L;
            studyPcmVoiceQuietBuffers = 0L;
            studyPcmVoiceCandidateMs = 0L;
            studyPcmVoiceLastRmsPermille = 0;
            studyPcmVoiceMaxRmsPermille = 0;
            studyPcmVoiceLastPeakPermille = 0;
            studyPcmVoiceMaxPeakPermille = 0;
            studyPcmVoiceLastZcrPermille = 0;
            studyPcmVoiceNoiseFloorPermille = 4;
            studyPcmVoiceLastThresholdPermille = STUDY_PCM_VOICE_MIN_RMS_PERMILLE;
            studyPcmVoiceWindows = 0L;
            studyPcmVoiceActiveWindows = 0L;
            studyPcmVoiceQuietWindows = 0L;
            studyPcmVoiceWindowAccumulatedMs = 0L;
            studyPcmVoiceWindowCandidateMs = 0L;
            studyPcmVoiceLastWindowCandidateMs = 0L;

            // Stage F: discard any partial feature window and all previous-video feature stats.
            studySpeakerFeatureCandidateTicks = 0L;
            studySpeakerFeatureAttempts = 0L;
            studySpeakerFeatureSuccess = 0L;
            studySpeakerFeatureErrors = 0L;
            studySpeakerFeatureWindows = 0L;
            studySpeakerFeatureValidWindows = 0L;
            studySpeakerFeatureRejectedWindows = 0L;
            studySpeakerFeatureWindowElapsedMs = 0L;
            studySpeakerFeatureWindowVoiceMs = 0L;
            studySpeakerFeatureWindowSamples = 0;
            studySpeakerWindowPitchWeightedHz = 0.0;
            studySpeakerWindowPitchWeight = 0.0;
            studySpeakerWindowPitchConfidenceSum = 0.0;
            studySpeakerWindowCentroidHzSum = 0.0;
            studySpeakerWindowZcrPermilleSum = 0.0;
            studySpeakerFeatureLastWindowVoiceMs = 0L;
            studySpeakerFeatureLastWindowSamples = 0;
            studySpeakerFeatureLastPitchHz = 0;
            studySpeakerFeatureLastPitchConfidencePermille = 0;
            studySpeakerFeatureLastCentroidHz = 0;
            studySpeakerFeatureLastZcrPermille = 0;
            studySpeakerFeatureLastLowPermille = 0;
            studySpeakerFeatureLastMidPermille = 0;
            studySpeakerFeatureLastHighPermille = 0;
            studySpeakerFeatureMinPitchHz = Integer.MAX_VALUE;
            studySpeakerFeatureMaxPitchHz = 0;
            studySpeakerFeatureMinCentroidHz = Integer.MAX_VALUE;
            studySpeakerFeatureMaxCentroidHz = 0;
            studySpeakerFeatureRollingHash = 1469598103934665603L;
            for (int i = 0; i < 7; i++) {
                studySpeakerWindowBandSums[i] = 0.0;
                studySpeakerLastBandPermille[i] = 0;
            }
            for (int i = 0; i < STUDY_SPEAKER_FEATURE_MAX_MONO; i++) studySpeakerMonoScratch[i] = 0;

            // Stage G: cluster identities must never leak from one video into another.
            for (int cluster = 0; cluster < STUDY_SPEAKER_CLUSTER_MAX; cluster++) {
                studySpeakerClusterCounts[cluster] = 0L;
                studySpeakerClusterPitchCount[cluster] = 0L;
                studySpeakerClusterPitchSum[cluster] = 0.0;
                studySpeakerClusterCentroidSum[cluster] = 0.0;
                studySpeakerClusterZcrSum[cluster] = 0.0;
                for (int dim = 0; dim < STUDY_SPEAKER_CLUSTER_DIMS; dim++) {
                    studySpeakerClusterCentroids[cluster][dim] = 0.0;
                }
                for (int band = 0; band < 7; band++) {
                    studySpeakerClusterBandSums[cluster][band] = 0.0;
                }
            }
            for (int dim = 0; dim < STUDY_SPEAKER_CLUSTER_DIMS; dim++) {
                studySpeakerClusterFeatureScratch[dim] = 0.0;
            }
            studySpeakerClusterCount = 0;
            studySpeakerClusterWindows = 0L;
            studySpeakerClusterCreates = 0L;
            studySpeakerClusterAssignments = 0L;
            studySpeakerClusterRawSwitches = 0L;
            studySpeakerClusterCommittedSwitches = 0L;
            studySpeakerClusterWindowsSinceCreate = 0L;
            studySpeakerClusterLastRaw = -1;
            studySpeakerClusterPending = -1;
            studySpeakerClusterPendingRun = 0;
            studySpeakerClusterCommitted = -1;
            studySpeakerClusterLastDistancePermille = 0;
            studySpeakerClusterLastMarginPermille = 0;

            studySpeakerAnalysisLastResetPcmHookCalls = studyPcmHookCalls;
            studySpeakerAnalysisEpoch++;
            studySpeakerAnalysisResetCount++;
        } finally {
            studySpeakerAnalysisResetInProgress = false;
        }
    }

    public static long getSpeakerAnalysisEpochForStudy() { return studySpeakerAnalysisEpoch; }
    public static long getSpeakerAnalysisResetCountForStudy() { return studySpeakerAnalysisResetCount; }
    public static long getSpeakerAnalysisLastResetPcmHookCallsForStudy() { return studySpeakerAnalysisLastResetPcmHookCalls; }
    public static boolean isSpeakerAnalysisResetInProgressForStudy() { return studySpeakerAnalysisResetInProgress; }

'''
    rep(
        player_volume,
        "    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }\n",
        reset_method + "    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }\n",
        "add Stage-J per-video speaker reset",
    )

    # The stock same-video guard is intentionally retained. Repeated callbacks for the same video
    # must not erase a cluster model that is still being learned.
    rep(
        vot,
        "        if (videoId.equals(currentVideoId)) return;\n\n        Logger.printDebug(() -> \"preloadTranslations newVideoLoaded\");\n",
        "        if (videoId.equals(currentVideoId)) return;\n\n"
        "        PlayerVolumePatch.resetSpeakerAnalysisForStudy();\n"
        "        SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SPEAKER,\n"
        "                \"per-video speaker reset epoch=\" + PlayerVolumePatch.getSpeakerAnalysisEpochForStudy()\n"
        "                        + \" video=\" + videoId\n"
        "                        + \" pcmHookCalls=\" + PlayerVolumePatch.getPcmHookCallsForStudy());\n\n"
        "        Logger.printDebug(() -> \"preloadTranslations newVideoLoaded\");\n",
        "reset speaker analysis only for a genuinely new video",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.11 Stage-I Spanish-voice-toggle diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.12 Stage-J per-video-speaker-reset diagnostics\\n");',
        "update Stage-J diagnostics header",
    )

    diag_anchor = '        report.append("speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing\\n");\n'
    diag_insert = (
        '        report.append("speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing\\n");\n'
        '        report.append("speakerAnalysisScope=per-video-reset-stage-j\\n");\n'
        '        report.append("speakerAnalysisEpoch=").append(PlayerVolumePatch.getSpeakerAnalysisEpochForStudy()).append(\'\\n\');\n'
        '        report.append("speakerAnalysisResetCount=").append(PlayerVolumePatch.getSpeakerAnalysisResetCountForStudy()).append(\'\\n\');\n'
        '        report.append("speakerAnalysisLastResetPcmHookCalls=").append(PlayerVolumePatch.getSpeakerAnalysisLastResetPcmHookCallsForStudy()).append(\'\\n\');\n'
        '        report.append("speakerAnalysisResetInProgress=").append(PlayerVolumePatch.isSpeakerAnalysisResetInProgressForStudy()).append(\'\\n\');\n'
    )
    rep(controller, diag_anchor, diag_insert, "publish Stage-J reset diagnostics")

    print("v2.32.12 Stage-J per-video speaker reset patch complete")
    print("UNCHANGED: AudioTrack.write PCM hook, Stage-E voice gate math, Stage-F pitch/Goertzel features, Stage-G cluster thresholds/distance, Stage-H badge, Stage-I Spanish voice toggle")
    print("UNCHANGED: mergeIntoSentences, OpenRouter 1500/350 packetization, translation ordering, subtitle pagination/timing, Edge TTS")
    print("ADDED: one reset after the existing same-video guard; E/F/G speaker state and counters are now video-local")


if __name__ == "__main__":
    main()
