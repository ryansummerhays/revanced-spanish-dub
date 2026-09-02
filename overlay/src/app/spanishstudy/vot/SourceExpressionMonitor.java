package app.spanishstudy.vot;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.pm.PackageManager;
import android.media.AudioTrack;
import android.media.audiofx.Visualizer;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;

import java.lang.ref.WeakReference;

import app.morphe.extension.shared.Logger;
import app.morphe.extension.shared.Utils;
import app.morphe.extension.youtube.patches.PlayerVolumePatch;

/**
 * Conservatively follows broad expressive movement in YouTube's ORIGINAL playback audio.
 *
 * This is intentionally not speaker recognition and not voice cloning. Android Visualizer gives us
 * a low-resolution waveform from the app's own YouTube AudioTrack session. We extract only a small,
 * confidence-gated relative pitch/energy signal and expose tightly bounded multipliers to the Edge
 * TTS MediaPlayer. If anything is uncertain, stale, silent, noisy, or unavailable, the getters return
 * neutral 1.0 values.
 *
 * Android requires RECORD_AUDIO permission for Visualizer even when it is attached to an existing
 * playback session. We do not open AudioRecord, do not record the microphone, and do not persist or
 * transmit waveform samples.
 */
public final class SourceExpressionMonitor {
    private static final Handler MAIN = new Handler(Looper.getMainLooper());
    private static final int PERMISSION_REQUEST_CODE = 0x5A31;
    private static final long ATTACH_RETRY_MS = 1_500L;
    private static final long SIGNAL_STALE_MS = 420L;

    private static final float BASELINE_ALPHA = 0.035f;
    private static final float ACTIVE_SMOOTH_ALPHA = 0.20f;
    private static final float NEUTRAL_SMOOTH_ALPHA = 0.28f;

    // A large sustained absolute-F0 jump is more likely a new speaker / tracking octave than an
    // expressive inflection. We reset the baseline instead of turning it into a dramatic TTS shift.
    private static final float IDENTITY_JUMP_LOW = 0.68f;
    private static final float IDENTITY_JUMP_HIGH = 1.47f;
    private static final int IDENTITY_CONFIRM_FRAMES = 4;

    private static volatile boolean requestedEnabled;
    private static volatile float pitchMultiplier = 1f;
    private static volatile float volumeMultiplier = 1f;
    private static volatile long lastGoodSignalElapsedMs;

    private static Visualizer visualizer;
    private static int attachedSessionId = -1;
    private static WeakReference<AudioTrack> latestTrackRef = new WeakReference<>(null);
    private static long lastAttachAttemptElapsedMs;

    // These fields are only mutated from Visualizer callback / main reset, and tiny races merely
    // make one frame more conservative. No waveform data is retained between callbacks.
    private static float baselinePitchHz;
    private static float baselineRms;
    private static int identityJumpFrames;
    private static float identityJumpCandidateHz;

    private SourceExpressionMonitor() {}

    /** Called from the patched YouTube AudioTrack wrapper whenever the playback track is replaced. */
    public static void onAudioTrack(AudioTrack track) {
        if (track == null) return;
        latestTrackRef = new WeakReference<>(track);
        MAIN.post(() -> {
            Context context = Utils.getContext();
            if (context == null) return;
            requestedEnabled = SpanishStudyPrefs.sourceExpressionEnabled(context);
            if (requestedEnabled && hasPermission(context)) attach(track);
        });
    }

    /** Enable/disable from the Spanish-study sheet. Permission is requested only on opt-in. */
    public static void setEnabled(Activity activity, boolean enabled) {
        requestedEnabled = enabled;
        if (!enabled) {
            release();
            return;
        }
        resetDynamics();
        if (activity == null) return;
        if (!hasPermission(activity)) {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                activity.requestPermissions(
                        new String[]{Manifest.permission.RECORD_AUDIO}, PERMISSION_REQUEST_CODE);
                // We intentionally do not depend on a host-Activity permission callback hook. Video
                // time updates and these delayed checks attach as soon as Android grants permission.
                MAIN.postDelayed(() -> maybeEnsureAttached(activity), 900L);
                MAIN.postDelayed(() -> maybeEnsureAttached(activity), 2_500L);
                MAIN.postDelayed(() -> maybeEnsureAttached(activity), 5_000L);
            }
            return;
        }
        maybeEnsureAttached(activity);
    }

    /** Lightweight periodic retry, called from the existing video-time hook. */
    public static void maybeEnsureAttached(Activity activity) {
        if (activity == null) return;
        if (!requestedEnabled) requestedEnabled = SpanishStudyPrefs.sourceExpressionEnabled(activity);
        if (!requestedEnabled || !hasPermission(activity)) return;

        long now = SystemClock.elapsedRealtime();
        if (visualizer != null && visualizer.getEnabled()) return;
        if (now - lastAttachAttemptElapsedMs < ATTACH_RETRY_MS) return;
        lastAttachAttemptElapsedMs = now;

        AudioTrack track = latestTrackRef.get();
        if (track == null) track = PlayerVolumePatch.getAudioTrackForStudy();
        if (track != null) attach(track);
    }

    public static boolean isRequestedEnabled() {
        return requestedEnabled;
    }

    /** Pitch applied independently of playback speed; stale/uncertain audio always returns neutral. */
    public static float pitchMultiplier() {
        if (!requestedEnabled) return 1f;
        if (SystemClock.elapsedRealtime() - lastGoodSignalElapsedMs > SIGNAL_STALE_MS) return 1f;
        return pitchMultiplier;
    }

    /** Small relative loudness expression; stale/uncertain audio always returns neutral. */
    public static float volumeMultiplier() {
        if (!requestedEnabled) return 1f;
        if (SystemClock.elapsedRealtime() - lastGoodSignalElapsedMs > SIGNAL_STALE_MS) return 1f;
        return volumeMultiplier;
    }

    /** Keep the AudioTrack attachment but forget the old video's/speaker's baseline. */
    public static void resetDynamics() {
        baselinePitchHz = 0f;
        baselineRms = 0f;
        identityJumpFrames = 0;
        identityJumpCandidateHz = 0f;
        pitchMultiplier = 1f;
        volumeMultiplier = 1f;
        lastGoodSignalElapsedMs = 0L;
    }

    private static boolean hasPermission(Context context) {
        return Build.VERSION.SDK_INT < Build.VERSION_CODES.M
                || context.checkSelfPermission(Manifest.permission.RECORD_AUDIO)
                == PackageManager.PERMISSION_GRANTED;
    }

    private static void attach(AudioTrack track) {
        if (!requestedEnabled || track == null) return;
        int sessionId;
        try {
            sessionId = track.getAudioSessionId();
        } catch (Exception ex) {
            Logger.printDebug(() -> "Source expression: cannot read AudioTrack session", ex);
            return;
        }
        if (sessionId <= 0) return;
        if (visualizer != null && attachedSessionId == sessionId) {
            try {
                if (!visualizer.getEnabled()) visualizer.setEnabled(true);
                return;
            } catch (Exception ignored) {
                releaseVisualizer();
            }
        }

        releaseVisualizer();
        try {
            Visualizer next = new Visualizer(sessionId);
            int[] range = Visualizer.getCaptureSizeRange();
            int capture = range != null && range.length >= 2 ? range[1] : 1024;
            capture = Math.max(128, capture);
            next.setCaptureSize(capture);
            int rate = Math.min(Visualizer.getMaxCaptureRate(), 20_000); // milli-Hz ~= 20 callbacks/s
            if (rate <= 0) rate = 10_000;
            next.setDataCaptureListener(new Visualizer.OnDataCaptureListener() {
                @Override
                public void onWaveFormDataCapture(Visualizer v, byte[] waveform, int samplingRate) {
                    consumeWaveform(waveform, samplingRate);
                }

                @Override
                public void onFftDataCapture(Visualizer v, byte[] fft, int samplingRate) {
                    // Waveform autocorrelation is enough for our deliberately broad expression cue.
                }
            }, rate, true, false);
            next.setEnabled(true);
            visualizer = next;
            attachedSessionId = sessionId;
            resetDynamics();
            Logger.printDebug(() -> "Source expression attached to YouTube audio session: " + sessionId);
        } catch (Throwable ex) {
            // Device/ROM support varies. This feature must never break ordinary dubbing.
            releaseVisualizer();
            Logger.printDebug(() -> "Source expression unavailable; using neutral TTS expression", ex);
        }
    }

    private static void consumeWaveform(byte[] waveform, int samplingRateMilliHz) {
        SourceExpressionMath.Frame frame = SourceExpressionMath.analyze(waveform, samplingRateMilliHz);
        if (!frame.hasReliablePitch()) {
            pitchMultiplier = smooth(pitchMultiplier, 1f, NEUTRAL_SMOOTH_ALPHA);
            volumeMultiplier = smooth(volumeMultiplier, 1f, NEUTRAL_SMOOTH_ALPHA);
            identityJumpFrames = 0;
            return;
        }

        if (baselinePitchHz <= 0f || baselineRms <= 0f) {
            baselinePitchHz = frame.pitchHz;
            baselineRms = Math.max(0.001f, frame.rms);
            lastGoodSignalElapsedMs = SystemClock.elapsedRealtime();
            return;
        }

        float ratio = frame.pitchHz / baselinePitchHz;
        if (ratio < IDENTITY_JUMP_LOW || ratio > IDENTITY_JUMP_HIGH) {
            // Do not interpret a new voice / octave error as expression. Require several consistent
            // frames, then adopt it as the new neutral baseline while TTS remains unchanged.
            if (identityJumpCandidateHz <= 0f
                    || Math.abs(frame.pitchHz - identityJumpCandidateHz)
                    / Math.max(1f, identityJumpCandidateHz) > 0.12f) {
                identityJumpCandidateHz = frame.pitchHz;
                identityJumpFrames = 1;
            } else {
                identityJumpCandidateHz = smooth(identityJumpCandidateHz, frame.pitchHz, 0.35f);
                identityJumpFrames++;
            }
            pitchMultiplier = smooth(pitchMultiplier, 1f, NEUTRAL_SMOOTH_ALPHA);
            volumeMultiplier = smooth(volumeMultiplier, 1f, NEUTRAL_SMOOTH_ALPHA);
            if (identityJumpFrames >= IDENTITY_CONFIRM_FRAMES) {
                baselinePitchHz = identityJumpCandidateHz;
                baselineRms = frame.rms;
                identityJumpFrames = 0;
                identityJumpCandidateHz = 0f;
            }
            lastGoodSignalElapsedMs = SystemClock.elapsedRealtime();
            return;
        }

        identityJumpFrames = 0;
        identityJumpCandidateHz = 0f;

        float pitchTarget = SourceExpressionMath.pitchMultiplier(
                frame.pitchHz, baselinePitchHz, frame.confidence);
        float volumeTarget = SourceExpressionMath.volumeMultiplier(
                frame.rms, baselineRms, frame.confidence);
        pitchMultiplier = smooth(pitchMultiplier, pitchTarget, ACTIVE_SMOOTH_ALPHA);
        volumeMultiplier = smooth(volumeMultiplier, volumeTarget, ACTIVE_SMOOTH_ALPHA);

        // Slow adaptation means short inflections survive as expression, while a sustained change
        // (including a different speaker) becomes the new neutral instead of remaining distorted.
        baselinePitchHz = smooth(baselinePitchHz, frame.pitchHz, BASELINE_ALPHA);
        baselineRms = smooth(baselineRms, frame.rms, BASELINE_ALPHA);
        lastGoodSignalElapsedMs = SystemClock.elapsedRealtime();
    }

    private static float smooth(float current, float target, float alpha) {
        return current + (target - current) * alpha;
    }

    private static void release() {
        releaseVisualizer();
        resetDynamics();
    }

    private static void releaseVisualizer() {
        Visualizer old = visualizer;
        visualizer = null;
        attachedSessionId = -1;
        if (old != null) {
            try { old.setEnabled(false); } catch (Exception ignored) {}
            try { old.release(); } catch (Exception ignored) {}
        }
    }
}
