#!/usr/bin/env python3
"""Reconstruct the proven v2.33.19 Sherpa shadow pipeline from normal Java source.

This is intentionally a source-parity gate. It preserves Stage-J as live badge authority and
retains v19's temporary stride-4 containment. It does not activate video-master PCM admission yet.
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
        raise SystemExit("usage: patch_v23319_sherpa_source_parity.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()

    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SpanishStudyController.java"
    gradle = root / "extensions/youtube/build.gradle.kts"
    target = root / "extensions/youtube/src/main/java/app/spanishstudy/vot/SherpaNeuralShadow.java"
    source = repo / "overlay/v23319/app/spanishstudy/vot/SherpaNeuralShadow.java"
    for p in (player, controller, gradle, source):
        if not p.is_file():
            raise RuntimeError(f"missing source-parity input: {p}")

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    print("copied:", target)

    rep(
        gradle,
        "    implementation(libs.protobuf.javalite)\n",
        "    implementation(libs.protobuf.javalite)\n"
        "    // Spanish Dub Study stable Sherpa source-parity compile API only.\n"
        "    implementation(files(\"libs/sherpa-onnx-1.13.7-classes.jar\"))\n",
        "compile official sherpa Java API",
    )

    # v19 observes the first PCM trigger before any diagnostic/reset early return. This only starts
    # model initialization after a context has also been provided; it performs no native work here.
    rep(
        player,
        "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n        studyPcmHookCalls++;\n",
        "    public static void observePcmBufferForStudy(ByteBuffer buffer) {\n"
        "        app.spanishstudy.vot.SherpaNeuralShadow.observePcmTrigger();\n"
        "        studyPcmHookCalls++;\n",
        "restore v19 neural PCM trigger",
    )

    # Feed the same original ByteBuffer plus already-proven AudioTrack format metadata. The neural
    # method duplicates the buffer and fails soft; Stage-E/F/G continue independently afterward.
    rep(
        player,
        "        final int sampleRateHz = studyAudioTrackSampleRateHz;\n"
        "        final int channels = studyAudioTrackChannelCount;\n"
        "        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING\n",
        "        final int sampleRateHz = studyAudioTrackSampleRateHz;\n"
        "        final int channels = studyAudioTrackChannelCount;\n"
        "        try {\n"
        "            app.spanishstudy.vot.SherpaNeuralShadow.observePcmBuffer(\n"
        "                    buffer, sampleRateHz, channels, studyAudioTrackEncoding);\n"
        "        } catch (Throwable ignored) {\n"
        "            // Neural shadow must never escape onto ExoPlayer's audio thread.\n"
        "        }\n"
        "        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING\n",
        "restore v19 bounded neural PCM feed",
    )

    # Invalidate a previous-video partial/in-flight capture before clearing Stage-E/F/G state.
    rep(
        player,
        "        try {\n            // Stage E: per-video voice gate and activity statistics.\n",
        "        try {\n"
        "            app.spanishstudy.vot.SherpaNeuralShadow.resetCaptureForVideo();\n"
        "            // Stage E: per-video voice gate and activity statistics.\n",
        "restore v19 neural epoch reset",
    )

    # The stable runtime provided the Activity from the normal main-thread video callback. No
    # player API is touched from the audio or neural worker threads.
    rep(
        controller,
        "        LocalSpeakerDiarizer.updatePlayhead(timeMs);\n"
        "        Activity activity = Utils.getActivity();\n",
        "        LocalSpeakerDiarizer.updatePlayhead(timeMs);\n"
        "        Activity activity = Utils.getActivity();\n"
        "        SherpaNeuralShadow.provideContext(activity);\n",
        "restore v19 safe context bridge",
    )

    # Replace the Stage-J banner and append the neural block once. Exact diagnostic wording is less
    # important than preserving the runtime invariants; the helper itself reports detailed state.
    rep(
        controller,
        'report.append("Spanish Dub Study v2.32.12 Stage-J per-video-speaker-reset diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.19 source-parity Sherpa bounded shadow diagnostics\\n");',
        "update source-parity diagnostics header",
    )
    anchor = '        report.append("speakerAnalysisResetInProgress=").append(PlayerVolumePatch.isSpeakerAnalysisResetInProgressForStudy()).append(\'\\n\');\n'
    rep(
        controller,
        anchor,
        anchor + '        report.append(SherpaNeuralShadow.diagnostics()).append(\'\\n\');\n',
        "publish source-parity Sherpa diagnostics",
    )

    print("v2.33.19 Sherpa source-parity patch complete")
    print("PRESERVED: Stage-J live badge authority, direct PCM hook, model lifetime, READY gate, epoch invalidation")
    print("PRESERVED: bounded 320000-sample capture and temporary stride-4 containment")
    print("NOT ACTIVE YET: video-master PCM admission, speaker voice routing")


if __name__ == "__main__":
    main()
