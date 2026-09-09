#!/usr/bin/env python3
"""v2.33.28: render-clock credit admission for bounded Sherpa capture.

This is the narrow follow-up to v2.33.27.

Runtime goals:
- keep YouTube videoMs as the authoritative content clock;
- keep AudioTrack.getPlaybackHeadPosition()/AudioTimestamp sampling on the controller thread;
- publish an immutable render anchor for the AudioTrack hot path to READ only;
- replace the temporary stride-4 Sherpa gate with a rendered-frame credit budget;
- stamp Sherpa capture start/end from the render/video anchor so a 20 s capture maps to ~20 s video time;
- add bounded, allocation-free PCM fingerprints to diagnose repeated/retried buffers;
- retain v2.33.27 post-write accepted-byte/frame accounting so the newly compiled patch hook can be verified;
- do not add LS-EEND/live diarization, TTS voice routing, subtitle timing changes, or translation changes yet.

Important containment: the AudioTrack callback never calls AudioTrack methods or YouTube/player APIs. It only
reads a volatile immutable controller-published render anchor and performs bounded PCM work under the existing
Sherpa capture lock. Model inference remains on the dedicated low-priority worker.
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
        raise SystemExit("usage: patch_v23328_render_clock_admission.py <morphe-root>")

    root = Path(sys.argv[1]).resolve()
    base = root / "extensions/youtube/src/main/java/app/spanishstudy/vot"
    probe = base / "AudioVideoSyncProbe.java"
    sherpa = base / "SherpaNeuralShadow.java"
    controller = base / "SpanishStudyController.java"
    hook = root / "patches/src/main/kotlin/app/morphe/patches/youtube/video/volume/PlayerVolumeHookPatch.kt"
    player = root / "extensions/youtube/src/main/java/app/morphe/extension/youtube/patches/PlayerVolumePatch.java"
    for p in (probe, sherpa, controller, hook, player):
        if not p.is_file():
            raise RuntimeError(f"missing v2.33.28 input: {p}")

    rep(
        probe,
        '''public final class AudioVideoSyncProbe {
    private static final Object LOCK = new Object();
    private static final int RECENT = 8;
''',
        '''public final class AudioVideoSyncProbe {
    /** Immutable controller-published mapping between rendered AudioTrack frames and YouTube videoMs. */
    public static final class RenderAnchor {
        public final boolean valid;
        public final long videoEpoch;
        public final long continuityEpoch;
        public final int sessionId;
        public final int sampleRateHz;
        public final long headFrames;
        public final long videoMs;
        public final boolean timestampAvailable;
        public final long timestampFrame;

        private RenderAnchor(boolean valid, long videoEpoch, long continuityEpoch,
                             int sessionId, int sampleRateHz, long headFrames, long videoMs,
                             boolean timestampAvailable, long timestampFrame) {
            this.valid = valid;
            this.videoEpoch = videoEpoch;
            this.continuityEpoch = continuityEpoch;
            this.sessionId = sessionId;
            this.sampleRateHz = sampleRateHz;
            this.headFrames = headFrames;
            this.videoMs = videoMs;
            this.timestampAvailable = timestampAvailable;
            this.timestampFrame = timestampFrame;
        }
    }

    private static final RenderAnchor INVALID_RENDER_ANCHOR = new RenderAnchor(
            false, -1L, -1L, -1, 0, -1L, -1L, false, -1L);
    private static volatile RenderAnchor publishedRenderAnchor = INVALID_RENDER_ANCHOR;

    /** Hot-path safe: returns an immutable object; does not touch AudioTrack or player APIs. */
    public static RenderAnchor latestRenderAnchor() {
        return publishedRenderAnchor;
    }

    private static final Object LOCK = new Object();
    private static final int RECENT = 8;
''',
        "publish immutable controller render anchor",
    )

    rep(
        probe,
        '''                lastRawHead = raw;
                extendedHead = head;
                lastVideoMs = clock.videoMs;
                lastHeadFrames = head;
                successfulSamples++;
''',
        '''                lastRawHead = raw;
                extendedHead = head;
                lastVideoMs = clock.videoMs;
                lastHeadFrames = head;
                publishedRenderAnchor = new RenderAnchor(true, clock.videoEpoch,
                        clock.continuityEpoch, newSession, newRate, head, clock.videoMs,
                        haveTimestamp, haveTimestamp ? timestamp.framePosition : -1L);
                successfulSamples++;
''',
        "publish render/video tuple after successful controller sample",
    )

    rep(
        probe,
        '''        lastTraceVideoMs = Long.MIN_VALUE;

        writeBaselineVideoMs = -1L;
''',
        '''        lastTraceVideoMs = Long.MIN_VALUE;
        publishedRenderAnchor = INVALID_RENDER_ANCHOR;

        writeBaselineVideoMs = -1L;
''',
        "invalidate published render anchor on session/epoch baseline reset",
    )

    rep(
        probe,
        '''            out.append("audioVideoSyncAcceptedVsVideoMs=").append(writeAcceptedVsVideoMs).append('\\n');
            out.append("audioVideoSyncRecentAnchors=");
''',
        '''            out.append("audioVideoSyncAcceptedVsVideoMs=").append(writeAcceptedVsVideoMs).append('\\n');
            RenderAnchor admission = publishedRenderAnchor;
            out.append("audioVideoAdmissionAnchorValid=").append(admission.valid).append('\\n');
            out.append("audioVideoAdmissionAnchorVideoEpoch=").append(admission.videoEpoch).append('\\n');
            out.append("audioVideoAdmissionAnchorContinuityEpoch=").append(admission.continuityEpoch).append('\\n');
            out.append("audioVideoAdmissionAnchorSessionId=").append(admission.sessionId).append('\\n');
            out.append("audioVideoAdmissionAnchorSampleRateHz=").append(admission.sampleRateHz).append('\\n');
            out.append("audioVideoAdmissionAnchorHeadFrames=").append(admission.headFrames).append('\\n');
            out.append("audioVideoAdmissionAnchorVideoMs=").append(admission.videoMs).append('\\n');
            out.append("audioVideoAdmissionAnchorTimestampAvailable=").append(admission.timestampAvailable).append('\\n');
            out.append("audioVideoAdmissionAnchorTimestampFrame=").append(admission.timestampFrame).append('\\n');
            out.append("audioVideoSyncRecentAnchors=");
''',
        "diagnose controller-published admission anchor",
    )

    rep(
        sherpa,
        '''    private static volatile int absoluteSegmentCount;

    private final float[] inferenceInput;
''',
        '''    private static volatile int absoluteSegmentCount;

    // v2.33.28 render-clock admission. These counters are capture-local and reset per video/seek.
    private static volatile long captureRenderBaselineHeadFrames = -1L;
    private static volatile long captureRenderBaselineVideoMs = -1L;
    private static volatile int captureRenderSessionId = -1;
    private static volatile int captureRenderAnchorRateHz;
    private static volatile long captureRenderAllowedInputFrames;
    private static volatile long captureRenderAcceptedInputFrames;
    private static volatile long captureRenderGateAcceptedBuffers;
    private static volatile long captureRenderGateRejectedBuffers;
    private static volatile long captureRenderGateNoAnchor;
    private static volatile long captureRenderGateOwnerMismatch;
    private static volatile long captureFingerprintCalls;
    private static volatile long captureFingerprintSameConsecutive;
    private static volatile long captureFingerprintChanges;
    private static volatile long captureFingerprintLast;

    private final float[] inferenceInput;
''',
        "add render-credit and PCM fingerprint state",
    )

    rep(
        sherpa,
        '''            float[] inference = null;
            long epoch = -1L;
            synchronized (LOCK) {
''',
        '''            long fingerprint = 0xcbf29ce484222325L;
            int fingerprintBytes = Math.min(64, remaining);
            for (int i = 0; i < fingerprintBytes; i++) {
                int rel = fingerprintBytes <= 1 ? 0
                        : (int) (((long) i * (remaining - 1L)) / (fingerprintBytes - 1L));
                fingerprint ^= (long) (src.get(position + rel) & 0xff);
                fingerprint *= 0x100000001b3L;
            }
            fingerprint ^= remaining;
            fingerprint *= 0x100000001b3L;

            float[] inference = null;
            long epoch = -1L;
            synchronized (LOCK) {
''',
        "add bounded allocation-free PCM fingerprint",
    )

    old_gate = '''                // v2.33.19 containment only: every fourth eligible callback feeds capture.
                captureBuffers++;
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
    new_gate = '''                captureBuffers++;
                captureFingerprintCalls++;
                if (captureFingerprintCalls > 1L) {
                    if (fingerprint == captureFingerprintLast) captureFingerprintSameConsecutive++;
                    else captureFingerprintChanges++;
                }
                captureFingerprintLast = fingerprint;

                AudioVideoSyncProbe.RenderAnchor render = AudioVideoSyncProbe.latestRenderAnchor();
                if (render == null || !render.valid || render.sampleRateHz <= 0
                        || render.headFrames < 0L || render.videoMs < 0L) {
                    captureRenderGateNoAnchor++;
                    return;
                }

                // Establish the zero-credit point from a controller-sampled rendered-frame/video pair.
                // Do not consume PCM on this call; future rendered-head movement grants the budget.
                if (captureRenderBaselineHeadFrames < 0L) {
                    captureVideoEpoch = render.videoEpoch;
                    captureContinuityEpoch = render.continuityEpoch;
                    captureRenderSessionId = render.sessionId;
                    captureRenderAnchorRateHz = render.sampleRateHz;
                    captureRenderBaselineHeadFrames = render.headFrames;
                    captureRenderBaselineVideoMs = render.videoMs;
                    captureStartVideoMs = render.videoMs;
                    captureEndVideoMs = -1L;
                    captureRenderAllowedInputFrames = 0L;
                    captureRenderAcceptedInputFrames = 0L;
                    absoluteTimelineValid = false;
                    absoluteSegmentCount = 0;
                    absoluteTimelineSummary = "none";
                    absoluteTimelineScalePermille = 0;
                    return;
                }

                if (render.videoEpoch != captureVideoEpoch
                        || render.continuityEpoch != captureContinuityEpoch
                        || render.sessionId != captureRenderSessionId) {
                    captureRenderGateOwnerMismatch++;
                    return;
                }

                long renderedFrames = Math.max(0L, render.headFrames - captureRenderBaselineHeadFrames);
                long allowedInputFrames = (renderedFrames * (long) sourceRateHz)
                        / Math.max(1, render.sampleRateHz);
                captureRenderAllowedInputFrames = allowedInputFrames;
                if (captureRenderAcceptedInputFrames + frames > allowedInputFrames) {
                    captureRenderGateRejectedBuffers++;
                    return;
                }

                captureRenderGateAcceptedBuffers++;
                captureRenderAcceptedInputFrames += frames;
                captureInputFrames = captureRenderAcceptedInputFrames;

                if (captureSourceRateHz != sourceRateHz || captureChannels != channels) {
'''
    rep(sherpa, old_gate, new_gate, "replace stride4 with rendered-frame credit gate")

    rep(
        sherpa,
        '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {
                    VideoSessionClock.Snapshot clock = VideoSessionClock.snapshot();
                    captureEndVideoMs = clock.videoMs;
                    captureComplete = true;
''',
        '''                if (captureSamples >= CAPTURE_TARGET_SAMPLES) {
                    captureEndVideoMs = captureStartVideoMs +
                            (captureRenderAcceptedInputFrames * 1000L) / Math.max(1, sourceRateHz);
                    captureComplete = true;
''',
        "stamp capture end from accepted rendered-frame credit",
    )

    rep(
        sherpa,
        '''            reset = captureSamples > 0 && !inferenceStarted
                    && captureVideoEpoch == clock.videoEpoch
''',
        '''            reset = (captureSamples > 0 || captureRenderBaselineHeadFrames >= 0L)
                    && !inferenceStarted
                    && captureVideoEpoch == clock.videoEpoch
''',
        "invalidate a baseline-only partial capture across seek",
    )

    rep(
        sherpa,
        '''            absoluteTimelineSummary = "none";
            absoluteSegmentCount = 0;
''',
        '''            absoluteTimelineSummary = "none";
            absoluteSegmentCount = 0;
            captureRenderBaselineHeadFrames = -1L;
            captureRenderBaselineVideoMs = -1L;
            captureRenderSessionId = -1;
            captureRenderAnchorRateHz = 0;
            captureRenderAllowedInputFrames = 0L;
            captureRenderAcceptedInputFrames = 0L;
            captureRenderGateAcceptedBuffers = 0L;
            captureRenderGateRejectedBuffers = 0L;
            captureRenderGateNoAnchor = 0L;
            captureRenderGateOwnerMismatch = 0L;
            captureFingerprintCalls = 0L;
            captureFingerprintSameConsecutive = 0L;
            captureFingerprintChanges = 0L;
            captureFingerprintLast = 0L;
''',
        "reset render-credit/fingerprint state with video capture",
        count=1,
    )

    rep(
        sherpa,
        '''        return "sherpa-video-projection videoMs=" + videoMs
                + " capture=" + captureStartVideoMs + "-" + captureEndVideoMs
                + " scalePermille=" + absoluteTimelineScalePermille
                + " alignment=" + (absoluteTimelineValid ? "coarse-valid" : "unavailable");
''',
        '''        return "sherpa-render-credit-video-projection videoMs=" + videoMs
                + " capture=" + captureStartVideoMs + "-" + captureEndVideoMs
                + " scalePermille=" + absoluteTimelineScalePermille
                + " alignment=" + (absoluteTimelineValid ? "render-credit-valid" : "unavailable");
''',
        "identify render-credit neural badge alignment",
    )

    rep(
        sherpa,
        '        out.append("speakerNeuralGate=v2.33.26-neural-only+stride4+absolute-video-projection\\n");\n',
        '        out.append("speakerNeuralGate=v2.33.28-neural-only+render-credit+absolute-video-projection\\n");\n',
        "update neural gate diagnostic",
    )
    rep(
        sherpa,
        '        out.append("speakerNeuralPcmFeed=direct-pcm16-fullwindow-stride4-16k-20s\\n");\n',
        '        out.append("speakerNeuralPcmFeed=direct-pcm16-fullwindow-render-credit-gated-16k-20s\\n");\n',
        "identify render-credit PCM feed",
    )
    rep(
        sherpa,
        '        out.append("speakerNeuralAbsoluteTimelineMode=linear-projection-from-video-clock-capture-span-coarse\\n");\n',
        '        out.append("speakerNeuralAbsoluteTimelineMode=render-credit-projection-from-controller-render-video-anchor\\n");\n',
        "identify render-credit absolute timeline mode",
    )

    diag_anchor = '''        out.append("speakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary).append('\\n');
        out.append("speakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline\\n");
'''
    diag_insert = '''        out.append("speakerNeuralAbsoluteSummary=").append(absoluteTimelineSummary).append('\\n');
        out.append("speakerNeuralRenderBaselineHeadFrames=").append(captureRenderBaselineHeadFrames).append('\\n');
        out.append("speakerNeuralRenderBaselineVideoMs=").append(captureRenderBaselineVideoMs).append('\\n');
        out.append("speakerNeuralRenderSessionId=").append(captureRenderSessionId).append('\\n');
        out.append("speakerNeuralRenderAnchorRateHz=").append(captureRenderAnchorRateHz).append('\\n');
        out.append("speakerNeuralRenderAllowedInputFrames=").append(captureRenderAllowedInputFrames).append('\\n');
        out.append("speakerNeuralRenderAcceptedInputFrames=").append(captureRenderAcceptedInputFrames).append('\\n');
        long neuralAcceptedMs = captureSourceRateHz > 0
                ? (captureRenderAcceptedInputFrames * 1000L) / captureSourceRateHz : 0L;
        out.append("speakerNeuralRenderAcceptedAudioMs=").append(neuralAcceptedMs).append('\\n');
        out.append("speakerNeuralRenderGateAcceptedBuffers=").append(captureRenderGateAcceptedBuffers).append('\\n');
        out.append("speakerNeuralRenderGateRejectedBuffers=").append(captureRenderGateRejectedBuffers).append('\\n');
        out.append("speakerNeuralRenderGateNoAnchor=").append(captureRenderGateNoAnchor).append('\\n');
        out.append("speakerNeuralRenderGateOwnerMismatch=").append(captureRenderGateOwnerMismatch).append('\\n');
        out.append("speakerNeuralPcmFingerprintMode=fnv1a-64-over-64-evenly-spaced-bytes-no-copy\\n");
        out.append("speakerNeuralPcmFingerprintCalls=").append(captureFingerprintCalls).append('\\n');
        out.append("speakerNeuralPcmFingerprintSameConsecutive=").append(captureFingerprintSameConsecutive).append('\\n');
        out.append("speakerNeuralPcmFingerprintChanges=").append(captureFingerprintChanges).append('\\n');
        out.append("speakerNeuralPcmFingerprintLast=").append(captureFingerprintLast).append('\\n');
        out.append("speakerNeuralLiveBadgeAuthority=true-neural-projected-video-timeline\\n");
'''
    rep(sherpa, diag_anchor, diag_insert, "publish render-credit and fingerprint diagnostics")

    rep(
        controller,
        'report.append("Spanish Dub Study v2.33.27 accepted-write PCM clock diagnostics\\n");',
        'report.append("Spanish Dub Study v2.33.28 render-clock PCM admission diagnostics\\n");',
        "update v2.33.28 diagnostics header",
    )
    rep(
        controller,
        '        report.append("audioVideoBridge=render-clock+accepted-write-accounting-active;pcm-admission-still-stride4\\n");\n'
        '        report.append("pcmAdmission=unchanged-sherpa-stride4-v23327-diagnostic-only\\n");\n',
        '        report.append("audioVideoBridge=render-clock+accepted-write-accounting+neural-render-credit-active\\n");\n'
        '        report.append("pcmAdmission=sherpa-render-credit-gate-v23328-shadow-no-live-diarizer-yet\\n");\n',
        "declare v2.33.28 render-credit admission active",
    )

    hook_text = hook.read_text(encoding="utf-8")
    player_text = player.read_text(encoding="utf-8")
    required_hook = [
        "observeAudioTrackWriteRequestedForStudy(I)V",
        "observeAudioTrackWriteResultForStudy(I)V",
        "resultInstruction.opcode != Opcode.MOVE_RESULT",
    ]
    for needle in required_hook:
        if needle not in hook_text:
            raise RuntimeError(f"v2.33.28 requires live v2.33.27 patch hook: {needle}")
    for needle in (
        "observeAudioTrackWriteRequestedForStudy(int requestedBytes)",
        "observeAudioTrackWriteResultForStudy(int result)",
    ):
        if needle not in player_text:
            raise RuntimeError(f"v2.33.28 requires v2.33.27 runtime callback: {needle}")

    print("v2.33.28 render-clock admission patch complete")
    print("ACTIVE: controller-published immutable rendered-frame/video anchor")
    print("ACTIVE: Sherpa render-credit gate replaces stride4; bounded 64-byte PCM fingerprint")
    print("ACTIVE: v2.33.27 accepted-write hook retained and MUST ship with current patch classes")
    print("UNCHANGED: Sherpa model/inference worker, translation, TTS, subtitle timing, voice routing")
    print("DEFERRED: LS-EEND/live Reddit diarizer until this clock/alignment gate validates at runtime")


if __name__ == "__main__":
    main()
