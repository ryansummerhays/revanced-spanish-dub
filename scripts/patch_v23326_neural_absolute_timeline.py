#!/usr/bin/env python3
"""v2.33.26: neural-only speaker authority + first absolute video-time projection.

Goals:
- stop using the legacy Stage-E/F/G/J heuristic diarizer as a speaker authority;
- stop the old Visualizer/local-clustering experiment from running;
- sample AudioTrack playback-head/AudioTimestamp on the controller thread against videoMs;
- stamp the bounded Sherpa capture with video epoch/continuity/start/end;
- project Sherpa's relative 20 s result into an absolute YouTube-ms timeline for validation;
- show only the projected neural label in the subtitle badge;
- update diagnostics version and repurpose existing Audio/Speaker logging toggles.

The absolute projection is deliberately labeled coarse: capture callback start/end video time is
used to scale the 20 s neural result. AudioTrack render-clock anchors are collected in parallel so
a later gate can replace this projection with frame-accurate mapping.
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
        raise SystemExit("usage: patch_v23326_neural_absolute_timeline.py <morphe-root> <repo-root>")
    root = Path(sys.argv[1]).resolve()
    repo = Path(sys.argv[2]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    controller = base / "SpanishStudyController.java"
    subtitle = base / "SpanishSubtitleOverlay.java"
    sheet = base / "SpanishStudySheet.java"
    sherpa = base / "SherpaNeuralShadow.java"
    helper_src = repo / "overlay/v23326/app/spanishstudy/vot/AudioVideoSyncProbe.java"
    for p in (player, controller, subtitle, sheet, sherpa, helper_src):
        if not p.is_file(): raise RuntimeError(f"missing v2.33.26 input: {p}")
    shutil.copy2(helper_src, base / "AudioVideoSyncProbe.java")
    print("copied: AudioVideoSyncProbe.java")

    # Expose Morphe's already-retained active AudioTrack only to the controller-side probe.
    rep(
        player,
        '''    public static boolean isMuted() {
        return muted;
    }

''',
        '''    public static boolean isMuted() {
        return muted;
    }

    /** Read-only study accessor. Never call this from the AudioTrack.write hook. */
    public static AudioTrack getActiveAudioTrackForStudy() {
        return lastAudioTrackRef.get();
    }

''',
        "expose active AudioTrack for controller-side clock sampling",
    )

    # The neural feed occurs before Stage-E. Return immediately after it so the old hand-built
    # VAD/features/clustering path no longer consumes PCM or drives labels.
    old_neural_feed = '''        try {
            app.spanishstudy.vot.SherpaNeuralShadow.observePcmBuffer(
                    buffer, sampleRateHz, channels, studyAudioTrackEncoding);
        } catch (Throwable ignored) {
            // Neural shadow must never escape onto ExoPlayer's audio thread.
        }
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    new_neural_feed = '''        try {
            app.spanishstudy.vot.SherpaNeuralShadow.observePcmBuffer(
                    buffer, sampleRateHz, channels, studyAudioTrackEncoding);
        } catch (Throwable ignored) {
            // Neural shadow must never escape onto ExoPlayer's audio thread.
        }
        // v2.33.26: Sherpa is the only speaker detector. Legacy Stage-E/F/G/J is retired.
        return;
        /* legacy Stage-E/F/G/J retained below for source history but unreachable */
        /*
        if (studyAudioTrackEncoding != STUDY_PCM16_ENCODING
'''
    rep(player, old_neural_feed, new_neural_feed, "retire legacy PCM diarization after neural feed")
    # Close the comment just before the method's final catch. The exact anchor belongs to the
    # Stage-E/F/G body and occurs once in observePcmBufferForStudy.
    legacy_end = '''        } catch (Throwable ignored) {
            studyPcmAnalysisDecodeErrors++;
        }
    }
'''
    legacy_end_new = '''        } catch (Throwable ignored) {
            studyPcmAnalysisDecodeErrors++;
        }
        */
    }
'''
    rep(player, legacy_end, legacy_end_new, "close retired legacy PCM diarization source block")

    # Controller publishes videoMs first, then samples Android's rendered-audio clock. No player
    # API is touched from the AudioTrack callback.
    old_time = '''    public static void onVideoTimeChanged(long timeMs) {
        VideoSessionClock.publishVideoTime(timeMs);
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        LocalSpeakerDiarizer.updatePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        SherpaNeuralShadow.provideContext(activity);
'''
    new_time = '''    public static void onVideoTimeChanged(long timeMs) {
        VideoSessionClock.publishVideoTime(timeMs);
        VideoSessionClock.Snapshot videoClock = VideoSessionClock.snapshot();
        SpanishStudyDiagnostics.samplePlayhead(timeMs);
        Activity activity = Utils.getActivity();
        SherpaNeuralShadow.provideContext(activity);
        SherpaNeuralShadow.observeVideoClock(videoClock);
        AudioVideoSyncProbe.sample(videoClock,
                app.morphe.extension.youtube.patches.PlayerVolumePatch.getActiveAudioTrackForStudy(),
                SpanishStudyDiagnostics.isEnabled(SpanishStudyDiagnostics.AUDIO));
'''
    rep(controller, old_time, new_time, "sample rendered-audio clock beside authoritative video clock")

    # Force the obsolete Visualizer experiment off even if an old preference was left enabled.
    rep(controller,
        "            LocalSpeakerDiarizer.setEnabled(activity, SpanishStudyPrefs.speakerExperiment(activity));\n",
        "            LocalSpeakerDiarizer.setEnabled(activity, false);\n",
        "disable legacy Visualizer on controller init")
    rep(controller,
        "        LocalSpeakerDiarizer.setEnabled(activity, SpanishStudyPrefs.speakerExperiment(activity));\n",
        "        LocalSpeakerDiarizer.setEnabled(activity, false);\n",
        "disable legacy Visualizer from tools sheet")

    # Header and clock diagnostics.
    rep(controller,
        'report.append("Spanish Dub Study v2.33.19 source-parity Sherpa bounded shadow diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.26 neural absolute-timeline + audio-render-clock diagnostics\\n");',
        "update diagnostics version")
    rep(controller,
        '        report.append("audioVideoBridge=compiled-inert-until-next-gate\\n");\n'
        '        report.append("speakerTimeline=compiled-absolute-video-ms-inert-until-next-gate\\n");\n',
        '        report.append("audioVideoBridge=render-clock-anchor-probe-active;pcm-admission-still-stride4\\n");\n'
        '        report.append("speakerTimeline=neural-relative-to-video-span-projection-active-coarse\\n");\n'
        '        report.append(AudioVideoSyncProbe.diagnostics());\n',
        "publish active audio/video anchor diagnostics")

    # Re-label legacy diagnostic fields so zero Stage-J counters are not mistaken for authority.
    rep(controller,
        '        report.append("speakerPcmDiarizationStatus=diagnostic-live-committed-cluster-badge-no-voice-routing\\n");\n',
        '        report.append("speakerPcmDiarizationStatus=legacy-stage-e-f-g-j-disabled-v23326\\n");\n',
        "mark legacy PCM diarizer disabled")
    rep(controller,
        '        report.append("speakerFeatureAssignment=committed-cluster-live-subtitle-badge-stage-h\\n");\n',
        '        report.append("speakerFeatureAssignment=disabled-legacy-stage-j\\n");\n',
        "mark legacy feature assignment disabled")
    rep(controller,
        '        report.append("speakerLabelClock=live-source-pcm-committed-cluster\\n");\n',
        '        report.append("speakerLabelClock=neural-absolute-video-ms-projection\\n");\n',
        "declare neural label clock")
    rep(controller,
        '        report.append("speakerLabelPersistence=none-live-diagnostic-only\\n");\n',
        '        report.append("speakerLabelPersistence=per-video-neural-projected-timeline-diagnostic-only\\n");\n',
        "declare neural timeline persistence")

    # Replace Stage-H live heuristic badge with the projected Sherpa timeline.
    old_badge = '''        int committedCluster = PlayerVolumePatch.getSpeakerClusterCommittedForStudy();
        int clusterCount = PlayerVolumePatch.getSpeakerClusterCountForStudy();
        String speaker = SpanishStudyPrefs.speakerExperiment(a)
                && committedCluster >= 0 && committedCluster < clusterCount
                ? String.valueOf((char) ('A' + committedCluster)) : "";
'''
    new_badge = '''        String speaker = SpanishStudyPrefs.speakerExperiment(a)
                ? SherpaNeuralShadow.labelAtVideoMs(timeMs) : "";
'''
    rep(subtitle, old_badge, new_badge, "use neural absolute timeline for speaker badge")

    old_badge_log = '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,
                        "speaker badge segment=" + index + " label=" + speaker
                                + " detail=stage-h-live-committed-cluster"
                                + " raw=" + PlayerVolumePatch.getSpeakerClusterLastRawForStudy()
                                + " committed=" + committedCluster
                                + " distancePermille=" + PlayerVolumePatch.getSpeakerClusterLastDistancePermilleForStudy()
                                + " marginPermille=" + PlayerVolumePatch.getSpeakerClusterLastMarginPermilleForStudy());
'''
    new_badge_log = '''                SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.SUBTITLES,
                        "speaker badge segment=" + index + " label=" + speaker
                                + " detail=" + SherpaNeuralShadow.labelDetailsAtVideoMs(timeMs));
'''
    rep(subtitle, old_badge_log, new_badge_log, "log neural badge timing details")

    # Repurpose the old speaker-experiment switch as neural-label visibility. The first detector
    # is not offered anymore.
    rep(sheet,
        '        content.addView(section(activity, "Local speaker experiment", secondary));\n',
        '        content.addView(section(activity, "Neural speaker timing", secondary));\n',
        "rename speaker section")
    rep(sheet,
        '        content.addView(switchRow(activity, fg, "Detect speaker A/B locally",\n'
        '                "$0 API cost. Reads YouTube\'s AudioTrack visualization session; no microphone. Labels only in v2.28.",\n'
        '                SpanishStudyPrefs.speakerExperiment(activity), value -> {\n'
        '                    SpanishStudyPrefs.setSpeakerExperiment(activity, value);\n'
        '                    LocalSpeakerDiarizer.setEnabled(activity, value);\n'
        '                }));\n',
        '        content.addView(switchRow(activity, fg, "Show neural speaker labels",\n'
        '                "Uses local Sherpa diarization projected onto YouTube video time. No microphone and no speaker API.",\n'
        '                SpanishStudyPrefs.speakerExperiment(activity),\n'
        '                value -> SpanishStudyPrefs.setSpeakerExperiment(activity, value)));\n',
        "replace legacy detector toggle with neural label toggle")
    rep(sheet,
        '                "This is a capture/clustering probe, not the final sherpa-onnx model. The diagnostics report AudioTrack attach status, waveform/FFT callbacks, voiced frames, per-segment assignments, cluster creation and similarity scores.");',
        '                "v2.33.26 retires the old heuristic/Visualizer speaker detector. Sherpa is the only speaker detector. The current badge uses a coarse video-time projection while AudioTrack playback-head and AudioTimestamp anchors are collected for the next frame-accurate alignment gate.");',
        "update speaker note")
    rep(sheet,
        '        content.addView(diagSwitch(activity, fg, "Audio capture",\n'
        '                "AudioTrack session, Visualizer attach and callback health",\n',
        '        content.addView(diagSwitch(activity, fg, "Audio / video clock",\n'
        '                "AudioTrack playback-head and AudioTimestamp anchors against YouTube video milliseconds",\n',
        "repurpose audio logging option")
    rep(sheet,
        '        content.addView(diagSwitch(activity, fg, "Speaker clustering",\n'
        '                "Voiced-frame accumulation, similarity and A/B/C/D decisions",\n',
        '        content.addView(diagSwitch(activity, fg, "Neural speaker timeline",\n'
        '                "Sherpa capture, inference, projected video-ms segments and neural badge changes",\n',
        "repurpose speaker logging option")

    # Sherpa capture ownership/timing fields.
    rep(sherpa,
        '    private static volatile String inferenceError = "none";\n',
        '    private static volatile String inferenceError = "none";\n'
        '    private static volatile long captureVideoEpoch = -1L;\n'
        '    private static volatile long captureContinuityEpoch = -1L;\n'
        '    private static volatile long captureStartVideoMs = -1L;\n'
        '    private static volatile long captureEndVideoMs = -1L;\n'
        '    private static volatile boolean absoluteTimelineValid;\n'
        '    private static volatile int absoluteTimelineScalePermille;\n'
        '    private static volatile String absoluteTimelineSummary = "none";\n'
        '    private static final int ABS_MAX_SEGMENTS = 64;\n'
        '    private static final long[] ABS_START_MS = new long[ABS_MAX_SEGMENTS];\n'
        '    private static final long[] ABS_END_MS = new long[ABS_MAX_SEGMENTS];\n'
        '    private static final int[] ABS_SPEAKER = new int[ABS_MAX_SEGMENTS];\n'
        '    private static volatile int absoluteSegmentCount;\n',
        "add neural capture video ownership and absolute timeline state")

    stride_anchor = '''                captureBuffers++;
                if ((((int) captureBuffers) & 3) != 0) return;

                if (captureSourceRateHz != sourceRateHz || captureChannels != channels) {
'''
    stride_insert = '''                captureBuffers++;
                if ((((int) captureBuffers) & 3) != 0) return;

                if (captureSamples == 0) {
                    VideoSessionClock.Snapshot clock = VideoSessionClock.snapshot();
                    captureVideoEpoch = clock.videoEpoch;
                    captureContinuityEpoch = clock.continuityEpoch;
                    captureStartVideoMs = clock.videoMs;
                    captureEndVideoMs = -1L;
                    absoluteTimelineValid = false;
                    absoluteSegmentCount = 0;
                    absoluteTimelineSummary = "none";
                    absoluteTimelineScalePermille = 0;
                }

                if (captureSourceRateHz != sourceRateHz || captureChannels != channels) {
'''
    rep(sherpa, stride_anchor, stride_insert, "stamp first accepted neural PCM with video clock")

    complete_anchor = '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {
                    captureComplete = true;
                    inferenceStarted = true;
                    inference = Arrays.copyOf(CAPTURE, CAPTURE_TARGET_SAMPLES);
                    epoch = captureEpoch;
                }
'''
    complete_insert = '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {
                    VideoSessionClock.Snapshot clock = VideoSessionClock.snapshot();
                    captureEndVideoMs = clock.videoMs;
                    captureComplete = true;
                    inferenceStarted = true;
                    inference = Arrays.copyOf(CAPTURE, CAPTURE_TARGET_SAMPLES);
                    epoch = captureEpoch;
                }
'''
    rep(sherpa, complete_anchor, complete_insert, "stamp completed neural capture with video clock")

    sync_anchor = '''            synchronized (LOCK) {
                if (epoch != captureEpoch) return;
                inferenceMs = elapsed;
                inferenceSegments = segmentCount;
                inferenceSpeakers = speakers.size();
                inferenceSummary = summary.length() == 0 ? "none" : summary.toString();
                inferenceError = "none";
                inferenceDone = true;
            }
'''
    sync_insert = '''            synchronized (LOCK) {
                if (epoch != captureEpoch) return;
                inferenceMs = elapsed;
                inferenceSegments = segmentCount;
                inferenceSpeakers = speakers.size();
                inferenceSummary = summary.length() == 0 ? "none" : summary.toString();

                VideoSessionClock.Snapshot now = VideoSessionClock.snapshot();
                long spanMs = captureEndVideoMs - captureStartVideoMs;
                boolean ownerStillValid = captureVideoEpoch > 0L
                        && captureVideoEpoch == now.videoEpoch
                        && captureContinuityEpoch == now.continuityEpoch;
                absoluteTimelineValid = ownerStillValid && captureStartVideoMs >= 0L
                        && spanMs > 0L && result != null;
                absoluteSegmentCount = 0;
                StringBuilder absolute = new StringBuilder();
                if (absoluteTimelineValid) {
                    absoluteTimelineScalePermille = (int) Math.max(1L, Math.min(10_000L,
                            (spanMs * 1000L) / (CAPTURE_SECONDS * 1000L)));
                    int limit = Math.min(result.length, ABS_MAX_SEGMENTS);
                    for (int i = 0; i < limit; i++) {
                        OfflineSpeakerDiarizationSegment s = result[i];
                        if (s == null) continue;
                        int speaker = s.getSpeaker();
                        long relStart = Math.round(s.getStart() * 1000.0f);
                        long relEnd = Math.round(s.getEnd() * 1000.0f);
                        long absStart = captureStartVideoMs
                                + (relStart * spanMs) / (CAPTURE_SECONDS * 1000L);
                        long absEnd = captureStartVideoMs
                                + (relEnd * spanMs) / (CAPTURE_SECONDS * 1000L);
                        if (absEnd <= absStart) continue;
                        int slot = absoluteSegmentCount++;
                        ABS_START_MS[slot] = absStart;
                        ABS_END_MS[slot] = absEnd;
                        ABS_SPEAKER[slot] = speaker;
                        if (absolute.length() > 0) absolute.append(',');
                        absolute.append(speaker).append('@').append(absStart).append('-').append(absEnd);
                    }
                } else {
                    absoluteTimelineScalePermille = 0;
                }
                absoluteTimelineSummary = absolute.length() == 0 ? "none" : absolute.toString();
                inferenceError = "none";
                inferenceDone = true;
            }
'''
    rep(sherpa, sync_anchor, sync_insert, "project Sherpa relative segments into absolute video milliseconds")

    method_anchor = '''    /** Invalidates partial and in-flight results but never destroys/interrupts native inference. */
    public static void resetCaptureForVideo() {
'''
    methods = '''    /** Reject a partial capture if a seek/discontinuity changes its continuity owner. */
    public static void observeVideoClock(VideoSessionClock.Snapshot clock) {
        if (clock == null || !clock.open) return;
        boolean reset = false;
        synchronized (LOCK) {
            reset = captureSamples > 0 && !inferenceStarted
                    && captureVideoEpoch == clock.videoEpoch
                    && captureContinuityEpoch >= 0L
                    && captureContinuityEpoch != clock.continuityEpoch;
        }
        if (reset) resetCaptureForVideo();
    }

    /** Neural label at an absolute YouTube video timestamp. Supports overlap as A+B. */
    public static String labelAtVideoMs(long videoMs) {
        if (!absoluteTimelineValid || videoMs < 0L) return "";
        int mask = 0;
        int n = absoluteSegmentCount;
        for (int i = 0; i < n; i++) {
            if (videoMs >= ABS_START_MS[i] && videoMs < ABS_END_MS[i]) {
                int speaker = ABS_SPEAKER[i];
                if (speaker >= 0 && speaker < 26) mask |= (1 << Math.min(speaker, 25));
            }
        }
        if (mask == 0) return "";
        StringBuilder label = new StringBuilder();
        for (int s = 0; s < 26; s++) {
            if ((mask & (1 << s)) == 0) continue;
            if (label.length() > 0) label.append('+');
            label.append((char) ('A' + s));
        }
        return label.toString();
    }

    public static String labelDetailsAtVideoMs(long videoMs) {
        return "sherpa-video-projection videoMs=" + videoMs
                + " capture=" + captureStartVideoMs + "-" + captureEndVideoMs
                + " scalePermille=" + absoluteTimelineScalePermille
                + " alignment=" + (absoluteTimelineValid ? "coarse-valid" : "unavailable");
    }

    /** Invalidates partial and in-flight results but never destroys/interrupts native inference. */
    public static void resetCaptureForVideo() {
'''
    rep(sherpa, method_anchor, methods, "add neural absolute timeline lookup and seek invalidation")

    reset_anchor = '''            inferenceSummary = "none";
            inferenceError = "none";
'''
    reset_insert = '''            inferenceSummary = "none";
            inferenceError = "none";
            VideoSessionClock.Snapshot clock = VideoSessionClock.snapshot();
            captureVideoEpoch = clock.videoEpoch;
            captureContinuityEpoch = clock.continuityEpoch;
            captureStartVideoMs = -1L;
            captureEndVideoMs = -1L;
            absoluteTimelineValid = false;
            absoluteTimelineScalePermille = 0;
            absoluteTimelineSummary = "none";
            absoluteSegmentCount = 0;
'''
    # This pair occurs in reset and not in the inference catch path.
    rep(sherpa, reset_anchor, reset_insert, "reset neural absolute timeline with capture epoch", count=1)

    diag_anchor = '''        out.append("speakerNeuralInferenceSummary=").append(inferenceSummary).append('\\n');
        out.append("speakerNeuralInferenceLastError=").append(inferenceError).append('\\n');
        out.append("speakerNeuralLiveBadgeAuthority=false-stage-j-remains-control\\n");
'''
    diag_insert = '''        out.append("speakerNeuralInferenceSummary=").append(inferenceSummary).append('\\n');
        out.append("speakerNeuralInferenceLastError=").append(inferenceError).append('\\n');
        out.append("speakerNeuralCaptureVideoEpoch=").append(captureVideoEpoch).append('\\n');
        out.append("speakerNeuralCaptureContinuityEpoch=").append(captureContinuityEpoch).append('\\n');
        out.append("speakerNeuralCaptureStartVideoMs=").append(captureStartVideoMs).append('\\n');
        out.append("speakerNeuralCaptureEndVideoMs=").append(captureEndVideoMs).append('\\n');
        out.append("speakerNeuralAbsoluteTimelineValid=").append(absoluteTimelineValid).append('\\n');
        out.append("speakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse\\n");
        out.append("speakerNeuralAbsoluteScalePermille=").append(absoluteTimelineScalePermille).append('\\n');
        out.append("speakerNeuralAbsoluteSegments=").append(absoluteSegmentCount).append('\\n');
        out.append("speakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary).append('\\n');
        out.append("speakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline\\n");
'''
    rep(sherpa, diag_anchor, diag_insert, "publish neural absolute timeline diagnostics")

    # The v19 gate string should no longer imply Stage-J is the intended next authority.
    rep(sherpa,
        '        out.append("speakerNeuralGate=v2.33.19-source-parity+stride4-only\\n");\n',
        '        out.append("speakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection\\n");\n',
        "update neural gate diagnostic")

    print("v2.33.26 neural absolute-timeline patch complete")
    print("ACTIVE: videoMs master clock + controller-side AudioTrack render anchors")
    print("ACTIVE: Sherpa-only speaker authority + coarse absolute video-ms projection")
    print("DISABLED: Visualizer and Stage-E/F/G/J heuristic diarization")
    print("NEXT: use observed rendered-frame anchors to replace coarse capture-span projection")


if __name__ == "__main__":
    main()
