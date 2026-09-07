#!/usr/bin/env python3
"""v2.32.9: Stage-G diagnostic online clustering on top of proven v2.32.8 speaker features.

Stage F proved stable short speaker-feature extraction from direct PCM16 with zero feature errors.
Stage G keeps the same capture/features and adds only tiny fixed-size online centroid clustering
when a valid ~800 ms feature window is finalized.

The clustering is diagnostic-only: up to four anonymous A/B/C/D clusters, fixed preallocated
primitive arrays, no worker thread, no per-window object allocation, no subtitle speaker labels,
no TTS voice routing, and no Morphe segmentation/translation/subtitle/TTS changes.
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
        raise SystemExit("usage: patch_v2329_online_clustering_stage_g.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    player_volume = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for path in (player_volume, controller):
        if not path.is_file():
            raise RuntimeError(f"missing v2.32.8 source: {path}")

    rep(
        player_volume,
        "    private static volatile long studySpeakerFeatureRollingHash = 1469598103934665603L;\n",
        "    private static volatile long studySpeakerFeatureRollingHash = 1469598103934665603L;\n"
        "    private static final int STUDY_SPEAKER_CLUSTER_MAX = 4;\n"
        "    private static final int STUDY_SPEAKER_CLUSTER_DIMS = 10;\n"
        "    private static final int STUDY_SPEAKER_CLUSTER_MIN_SEED_GAP = 6;\n"
        "    private static final double STUDY_SPEAKER_CLUSTER_NEW_DISTANCE = 0.255;\n"
        "    private static final int STUDY_SPEAKER_CLUSTER_STABLE_RUN = 2;\n"
        "    private static final double[][] studySpeakerClusterCentroids = new double[STUDY_SPEAKER_CLUSTER_MAX][STUDY_SPEAKER_CLUSTER_DIMS];\n"
        "    private static final long[] studySpeakerClusterCounts = new long[STUDY_SPEAKER_CLUSTER_MAX];\n"
        "    private static final long[] studySpeakerClusterPitchCount = new long[STUDY_SPEAKER_CLUSTER_MAX];\n"
        "    private static final double[] studySpeakerClusterPitchSum = new double[STUDY_SPEAKER_CLUSTER_MAX];\n"
        "    private static final double[] studySpeakerClusterCentroidSum = new double[STUDY_SPEAKER_CLUSTER_MAX];\n"
        "    private static final double[] studySpeakerClusterZcrSum = new double[STUDY_SPEAKER_CLUSTER_MAX];\n"
        "    private static final double[][] studySpeakerClusterBandSums = new double[STUDY_SPEAKER_CLUSTER_MAX][7];\n"
        "    private static final double[] studySpeakerClusterFeatureScratch = new double[STUDY_SPEAKER_CLUSTER_DIMS];\n"
        "    private static volatile int studySpeakerClusterCount;\n"
        "    private static volatile long studySpeakerClusterWindows;\n"
        "    private static volatile long studySpeakerClusterCreates;\n"
        "    private static volatile long studySpeakerClusterAssignments;\n"
        "    private static volatile long studySpeakerClusterRawSwitches;\n"
        "    private static volatile long studySpeakerClusterCommittedSwitches;\n"
        "    private static volatile long studySpeakerClusterWindowsSinceCreate;\n"
        "    private static volatile int studySpeakerClusterLastRaw = -1;\n"
        "    private static volatile int studySpeakerClusterPending = -1;\n"
        "    private static volatile int studySpeakerClusterPendingRun;\n"
        "    private static volatile int studySpeakerClusterCommitted = -1;\n"
        "    private static volatile int studySpeakerClusterLastDistancePermille;\n"
        "    private static volatile int studySpeakerClusterLastMarginPermille;\n",
        "add Stage-G fixed clustering state",
    )

    rep(
        player_volume,
        "            studySpeakerFeatureRollingHash = hash;\n",
        "            studySpeakerFeatureRollingHash = hash;\n"
        "            studyAssignSpeakerCluster(pitchHz, pitchConfidencePermille, centroidHz, zcrPermille);\n",
        "assign valid Stage-F window to Stage-G cluster",
    )

    helper_anchor = "    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }\n"
    helper_insert = r'''    private static double studyClamp01(double value) {
        return value < 0.0 ? 0.0 : (value > 1.0 ? 1.0 : value);
    }

    private static void studyBuildSpeakerClusterFeature(int pitchHz, int pitchConfidencePermille,
            int centroidHz, int zcrPermille) {
        final double[] f = studySpeakerClusterFeatureScratch;
        f[0] = studySpeakerLastBandPermille[0] / 1000.0;
        f[1] = studySpeakerLastBandPermille[1] / 1000.0;
        f[2] = studySpeakerLastBandPermille[2] / 1000.0;
        f[3] = studySpeakerLastBandPermille[3] / 1000.0;
        f[4] = studySpeakerLastBandPermille[4] / 1000.0;
        f[5] = (studySpeakerLastBandPermille[5] + studySpeakerLastBandPermille[6]) / 1000.0;
        f[6] = studyClamp01(Math.log(Math.max(100.0, centroidHz) / 100.0) / Math.log(60.0));
        f[7] = studyClamp01(zcrPermille / 350.0);
        f[8] = pitchHz > 0
                ? studyClamp01(Math.log(pitchHz / 70.0) / Math.log(350.0 / 70.0)) : 0.5;
        f[9] = studyClamp01(pitchConfidencePermille / 1000.0);
    }

    private static double studySpeakerClusterDistance(int cluster) {
        final double[] f = studySpeakerClusterFeatureScratch;
        final double[] c = studySpeakerClusterCentroids[cluster];
        double band = 0.0;
        for (int i = 0; i < 6; i++) {
            final double d = f[i] - c[i];
            band += d * d;
        }
        band /= 6.0;
        final double dc = f[6] - c[6];
        final double dz = f[7] - c[7];
        final double pitchReliability = Math.min(f[9], c[9]);
        final double dp = f[8] - c[8];
        final double dq = f[9] - c[9];
        final double squared = (0.50 * band)
                + (0.17 * dc * dc)
                + (0.10 * dz * dz)
                + (0.18 * pitchReliability * dp * dp)
                + (0.05 * dq * dq);
        return Math.sqrt(Math.max(0.0, squared));
    }

    private static void studySeedSpeakerCluster(int cluster) {
        final double[] f = studySpeakerClusterFeatureScratch;
        final double[] c = studySpeakerClusterCentroids[cluster];
        for (int i = 0; i < STUDY_SPEAKER_CLUSTER_DIMS; i++) c[i] = f[i];
        studySpeakerClusterCounts[cluster] = 0L;
        studySpeakerClusterPitchCount[cluster] = 0L;
        studySpeakerClusterPitchSum[cluster] = 0.0;
        studySpeakerClusterCentroidSum[cluster] = 0.0;
        studySpeakerClusterZcrSum[cluster] = 0.0;
        for (int i = 0; i < 7; i++) studySpeakerClusterBandSums[cluster][i] = 0.0;
    }

    private static void studyUpdateSpeakerCluster(int cluster, int pitchHz, int centroidHz, int zcrPermille) {
        final long oldCount = studySpeakerClusterCounts[cluster];
        final long capped = Math.min(63L, oldCount);
        final double alpha = 1.0 / (capped + 1.0);
        final double[] f = studySpeakerClusterFeatureScratch;
        final double[] c = studySpeakerClusterCentroids[cluster];
        for (int i = 0; i < STUDY_SPEAKER_CLUSTER_DIMS; i++) {
            c[i] += alpha * (f[i] - c[i]);
        }
        studySpeakerClusterCounts[cluster] = oldCount + 1L;
        if (pitchHz > 0) {
            studySpeakerClusterPitchCount[cluster]++;
            studySpeakerClusterPitchSum[cluster] += pitchHz;
        }
        studySpeakerClusterCentroidSum[cluster] += centroidHz;
        studySpeakerClusterZcrSum[cluster] += zcrPermille;
        for (int i = 0; i < 7; i++) studySpeakerClusterBandSums[cluster][i] += studySpeakerLastBandPermille[i];
    }

    private static void studyAssignSpeakerCluster(int pitchHz, int pitchConfidencePermille,
            int centroidHz, int zcrPermille) {
        studySpeakerClusterWindows++;
        studySpeakerClusterWindowsSinceCreate++;
        studyBuildSpeakerClusterFeature(pitchHz, pitchConfidencePermille, centroidHz, zcrPermille);

        int best = -1;
        double bestDistance = Double.MAX_VALUE;
        double secondDistance = Double.MAX_VALUE;
        for (int cluster = 0; cluster < studySpeakerClusterCount; cluster++) {
            final double distance = studySpeakerClusterDistance(cluster);
            if (distance < bestDistance) {
                secondDistance = bestDistance;
                bestDistance = distance;
                best = cluster;
            } else if (distance < secondDistance) {
                secondDistance = distance;
            }
        }

        if (best < 0) {
            best = 0;
            studySeedSpeakerCluster(best);
            studySpeakerClusterCount = 1;
            studySpeakerClusterCreates++;
            studySpeakerClusterWindowsSinceCreate = 0L;
            bestDistance = 0.0;
            secondDistance = 1.0;
        } else if (studySpeakerClusterCount < STUDY_SPEAKER_CLUSTER_MAX
                && bestDistance >= STUDY_SPEAKER_CLUSTER_NEW_DISTANCE
                && studySpeakerClusterWindowsSinceCreate >= STUDY_SPEAKER_CLUSTER_MIN_SEED_GAP) {
            best = studySpeakerClusterCount;
            studySeedSpeakerCluster(best);
            studySpeakerClusterCount++;
            studySpeakerClusterCreates++;
            studySpeakerClusterWindowsSinceCreate = 0L;
            secondDistance = bestDistance;
            bestDistance = 0.0;
        }

        studyUpdateSpeakerCluster(best, pitchHz, centroidHz, zcrPermille);
        studySpeakerClusterAssignments++;
        studySpeakerClusterLastDistancePermille = (int) Math.round(Math.min(1.0, bestDistance) * 1000.0);
        if (secondDistance == Double.MAX_VALUE) secondDistance = 1.0;
        studySpeakerClusterLastMarginPermille = (int) Math.round(
                Math.max(0.0, Math.min(1.0, secondDistance - bestDistance)) * 1000.0);

        if (studySpeakerClusterLastRaw >= 0 && best != studySpeakerClusterLastRaw) {
            studySpeakerClusterRawSwitches++;
        }
        studySpeakerClusterLastRaw = best;

        if (best == studySpeakerClusterPending) {
            studySpeakerClusterPendingRun++;
        } else {
            studySpeakerClusterPending = best;
            studySpeakerClusterPendingRun = 1;
        }
        if (studySpeakerClusterPendingRun >= STUDY_SPEAKER_CLUSTER_STABLE_RUN
                && studySpeakerClusterCommitted != best) {
            if (studySpeakerClusterCommitted >= 0) studySpeakerClusterCommittedSwitches++;
            studySpeakerClusterCommitted = best;
        }
    }

    public static long getPcmHookCallsForStudy() { return studyPcmHookCalls; }
'''
    rep(player_volume, helper_anchor, helper_insert, "add Stage-G online clustering helpers")

    getter_anchor = "    public static long getSpeakerFeatureRollingHashForStudy() { return studySpeakerFeatureRollingHash; }\n\n"
    getter_insert = r'''    public static long getSpeakerFeatureRollingHashForStudy() { return studySpeakerFeatureRollingHash; }
    public static int getSpeakerClusterMaxForStudy() { return STUDY_SPEAKER_CLUSTER_MAX; }
    public static int getSpeakerClusterMinSeedGapForStudy() { return STUDY_SPEAKER_CLUSTER_MIN_SEED_GAP; }
    public static int getSpeakerClusterStableRunForStudy() { return STUDY_SPEAKER_CLUSTER_STABLE_RUN; }
    public static int getSpeakerClusterNewDistancePermilleForStudy() { return (int) Math.round(STUDY_SPEAKER_CLUSTER_NEW_DISTANCE * 1000.0); }
    public static int getSpeakerClusterCountForStudy() { return studySpeakerClusterCount; }
    public static long getSpeakerClusterWindowsForStudy() { return studySpeakerClusterWindows; }
    public static long getSpeakerClusterCreatesForStudy() { return studySpeakerClusterCreates; }
    public static long getSpeakerClusterAssignmentsForStudy() { return studySpeakerClusterAssignments; }
    public static long getSpeakerClusterRawSwitchesForStudy() { return studySpeakerClusterRawSwitches; }
    public static long getSpeakerClusterCommittedSwitchesForStudy() { return studySpeakerClusterCommittedSwitches; }
    public static int getSpeakerClusterLastDistancePermilleForStudy() { return studySpeakerClusterLastDistancePermille; }
    public static int getSpeakerClusterLastMarginPermilleForStudy() { return studySpeakerClusterLastMarginPermille; }
    public static int getSpeakerClusterLastRawForStudy() { return studySpeakerClusterLastRaw; }
    public static int getSpeakerClusterCommittedForStudy() { return studySpeakerClusterCommitted; }
    public static long getSpeakerClusterCountForStudy(int cluster) {
        return cluster >= 0 && cluster < STUDY_SPEAKER_CLUSTER_MAX ? studySpeakerClusterCounts[cluster] : 0L;
    }
    public static int getSpeakerClusterAveragePitchHzForStudy(int cluster) {
        if (cluster < 0 || cluster >= STUDY_SPEAKER_CLUSTER_MAX || studySpeakerClusterPitchCount[cluster] == 0L) return 0;
        return (int) Math.round(studySpeakerClusterPitchSum[cluster] / studySpeakerClusterPitchCount[cluster]);
    }
    public static int getSpeakerClusterAverageCentroidHzForStudy(int cluster) {
        if (cluster < 0 || cluster >= STUDY_SPEAKER_CLUSTER_MAX || studySpeakerClusterCounts[cluster] == 0L) return 0;
        return (int) Math.round(studySpeakerClusterCentroidSum[cluster] / studySpeakerClusterCounts[cluster]);
    }
    public static int getSpeakerClusterAverageZcrPermilleForStudy(int cluster) {
        if (cluster < 0 || cluster >= STUDY_SPEAKER_CLUSTER_MAX || studySpeakerClusterCounts[cluster] == 0L) return 0;
        return (int) Math.round(studySpeakerClusterZcrSum[cluster] / studySpeakerClusterCounts[cluster]);
    }
    public static int getSpeakerClusterAverageBandPermilleForStudy(int cluster, int band) {
        if (cluster < 0 || cluster >= STUDY_SPEAKER_CLUSTER_MAX || band < 0 || band >= 7
                || studySpeakerClusterCounts[cluster] == 0L) return 0;
        return (int) Math.round(studySpeakerClusterBandSums[cluster][band] / studySpeakerClusterCounts[cluster]);
    }

'''
    rep(player_volume, getter_anchor, getter_insert, "publish Stage-G cluster getters")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.8 Stage-F speaker-feature diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.9 Stage-G online-clustering diagnostics\\n");',
        "update Stage-G diagnostics header",
    )

    rep(
        controller,
        '        report.append("speakerPcmDiarizationStatus=pre-clustering-short-speaker-feature-windows\\n");\n',
        '        report.append("speakerPcmDiarizationStatus=diagnostic-online-clustering-no-label-routing\\n");\n',
        "update Stage-G speaker status",
    )

    diag_anchor = '''        report.append("speakerFeatureClustering=disabled-stage-f\\n");
        report.append("speakerFeatureAssignment=disabled-stage-f\\n");
'''
    diag_insert = '''        report.append("speakerFeatureClustering=online-fixed-centroid-stage-g-diagnostic-only\\n");
        report.append("speakerFeatureAssignment=cluster-window-only-no-subtitle-labels-stage-g\\n");
        report.append("speakerClusterMax=").append(PlayerVolumePatch.getSpeakerClusterMaxForStudy()).append('\\n');
        report.append("speakerClusterNewDistancePermille=").append(PlayerVolumePatch.getSpeakerClusterNewDistancePermilleForStudy()).append('\\n');
        report.append("speakerClusterMinSeedGapWindows=").append(PlayerVolumePatch.getSpeakerClusterMinSeedGapForStudy()).append('\\n');
        report.append("speakerClusterStableRunWindows=").append(PlayerVolumePatch.getSpeakerClusterStableRunForStudy()).append('\\n');
        report.append("speakerClusterCount=").append(PlayerVolumePatch.getSpeakerClusterCountForStudy()).append('\\n');
        report.append("speakerClusterWindows=").append(PlayerVolumePatch.getSpeakerClusterWindowsForStudy()).append('\\n');
        report.append("speakerClusterCreates=").append(PlayerVolumePatch.getSpeakerClusterCreatesForStudy()).append('\\n');
        report.append("speakerClusterAssignments=").append(PlayerVolumePatch.getSpeakerClusterAssignmentsForStudy()).append('\\n');
        report.append("speakerClusterRawSwitches=").append(PlayerVolumePatch.getSpeakerClusterRawSwitchesForStudy()).append('\\n');
        report.append("speakerClusterCommittedSwitches=").append(PlayerVolumePatch.getSpeakerClusterCommittedSwitchesForStudy()).append('\\n');
        report.append("speakerClusterLastRaw=").append(PlayerVolumePatch.getSpeakerClusterLastRawForStudy()).append('\\n');
        report.append("speakerClusterCommitted=").append(PlayerVolumePatch.getSpeakerClusterCommittedForStudy()).append('\\n');
        report.append("speakerClusterLastDistancePermille=").append(PlayerVolumePatch.getSpeakerClusterLastDistancePermilleForStudy()).append('\\n');
        report.append("speakerClusterLastMarginPermille=").append(PlayerVolumePatch.getSpeakerClusterLastMarginPermilleForStudy()).append('\\n');
        for (int cluster = 0; cluster < PlayerVolumePatch.getSpeakerClusterMaxForStudy(); cluster++) {
            report.append("speakerCluster").append((char) ('A' + cluster)).append("Windows=")
                    .append(PlayerVolumePatch.getSpeakerClusterCountForStudy(cluster)).append('\\n');
            report.append("speakerCluster").append((char) ('A' + cluster)).append("AveragePitchHz=")
                    .append(PlayerVolumePatch.getSpeakerClusterAveragePitchHzForStudy(cluster)).append('\\n');
            report.append("speakerCluster").append((char) ('A' + cluster)).append("AverageCentroidHz=")
                    .append(PlayerVolumePatch.getSpeakerClusterAverageCentroidHzForStudy(cluster)).append('\\n');
            report.append("speakerCluster").append((char) ('A' + cluster)).append("AverageZcrPermille=")
                    .append(PlayerVolumePatch.getSpeakerClusterAverageZcrPermilleForStudy(cluster)).append('\\n');
            report.append("speakerCluster").append((char) ('A' + cluster)).append("AverageBandsPermille=");
            for (int band = 0; band < 7; band++) {
                if (band > 0) report.append(',');
                report.append(PlayerVolumePatch.getSpeakerClusterAverageBandPermilleForStudy(cluster, band));
            }
            report.append('\\n');
        }
'''
    rep(controller, diag_anchor, diag_insert, "publish Stage-G clustering diagnostics")

    print("v2.32.9 Stage-G online diagnostic clustering complete")
    print("UNCHANGED: direct PCM hook, Stage-E VAD, Stage-F features, mergeIntoSentences, 1500/350 OpenRouter packets, subtitles, TTS")
    print("NOT ADDED: runtime helper class, worker thread, per-window object allocation, subtitle speaker labels, TTS voice routing")


if __name__ == "__main__":
    main()
