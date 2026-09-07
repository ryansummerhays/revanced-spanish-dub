#!/usr/bin/env python3
"""v2.32.10: Stage-H live committed-cluster badge for manual speaker validation.

Stage G proved stable direct-PCM online clustering into anonymous A/B/C/D groups. Stage H does
not change PCM capture, VAD, feature extraction, clustering, translation, subtitle pagination,
or TTS. It only exposes the already-committed Stage-G cluster as the existing speaker badge and
subtitle diagnostic field so the user can visually compare A/B/C/D against the person speaking.

The label is live diagnostic state only. It is not persisted to source segments and is not used
for TTS voice routing.
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
        raise SystemExit("usage: patch_v23210_live_cluster_label_stage_h.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    subtitle = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishSubtitleOverlay.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    for path in (subtitle, controller):
        if not path.is_file():
            raise RuntimeError(f"missing v2.32.9 source: {path}")

    rep(
        subtitle,
        "import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;\n",
        "import app.morphe.extension.youtube.patches.PlayerVolumePatch;\n"
        "import app.morphe.extension.youtube.patches.voiceovertranslation.TranscriptSegment;\n",
        "import Stage-G cluster state into subtitle overlay",
    )

    rep(
        subtitle,
        '''        String speaker = SpanishStudyPrefs.speakerExperiment(a)\n                ? LocalSpeakerDiarizer.labelForSegment(index) : "";\n''',
        '''        int committedCluster = PlayerVolumePatch.getSpeakerClusterCommittedForStudy();\n        int clusterCount = PlayerVolumePatch.getSpeakerClusterCountForStudy();\n        String speaker = SpanishStudyPrefs.speakerExperiment(a)\n                && committedCluster >= 0 && committedCluster < clusterCount\n                ? String.valueOf((char) ('A' + committedCluster)) : "";\n''',
        "show live committed Stage-G cluster in existing speaker badge",
    )

    rep(
        subtitle,
        '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,\n                        "speaker badge segment=" + index + " label=" + speaker\n                                + " detail=" + LocalSpeakerDiarizer.assignmentDetails(index));\n''',
        '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,\n                        "speaker badge segment=" + index + " label=" + speaker\n                                + " detail=stage-h-live-committed-cluster"\n                                + " raw=" + PlayerVolumePatch.getSpeakerClusterLastRawForStudy()\n                                + " committed=" + committedCluster\n                                + " distancePermille=" + PlayerVolumePatch.getSpeakerClusterLastDistancePermilleForStudy()\n                                + " marginPermille=" + PlayerVolumePatch.getSpeakerClusterLastMarginPermilleForStudy());\n''',
        "publish live cluster confidence when badge changes",
    )

    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.9 Stage-G online-clustering diagnostics\\n");',
        'report.append("Spanish Dub Study v2.32.10 Stage-H live-cluster-label diagnostics\\n");',
        "update Stage-H diagnostics header",
    )

    rep(
        controller,
        '        report.append("speakerPcmDiarizationStatus=diagnostic-online-clustering-no-label-routing\\n");\n',
        '        report.append("speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing\\n");\n',
        "update Stage-H speaker status",
    )

    rep(
        controller,
        '        report.append("speakerFeatureAssignment=cluster-window-only-no-subtitle-labels-stage-g\\n");\n',
        '        report.append("speakerFeatureAssignment=committed-cluster-live-subtitle-badge-stage-h\\n");\n'
        '        report.append("speakerLabelClock=live-source-pcm-committed-cluster\\n");\n'
        '        report.append("speakerLabelPersistence=none-live-diagnostic-only\\n");\n',
        "publish Stage-H label-only behavior",
    )

    print("v2.32.10 Stage-H live cluster badge patch complete")
    print("UNCHANGED: PCM hook, AudioTrack metadata, Stage-E VAD, Stage-F features, Stage-G clustering, mergeIntoSentences, 1500/350 OpenRouter packets, subtitle pagination/timing, Edge TTS")
    print("ADDED: existing on-screen speaker badge now shows live committed A/B/C/D cluster and subtitle diagnostics record badge changes")
    print("NOT ADDED: segment persistence, named speakers, voice routing, worker thread, new PCM reads, clustering changes")


if __name__ == "__main__":
    main()
