package app.spanishstudy.vot;

import android.media.AudioTimestamp;
import android.media.AudioTrack;

/**
 * Read-only bridge between YouTube's authoritative video clock and Android's rendered-audio
 * playback clock. Sampling is driven from the normal controller/video-time callback, never from
 * the AudioTrack.write hot path.
 */
public final class AudioVideoSyncProbe {
    private static final Object LOCK = new Object();
    private static final int RECENT = 8;
    private static final long[] recentVideoMs = new long[RECENT];
    private static final long[] recentHeadFrames = new long[RECENT];

    private static long videoEpoch = -1L;
    private static long continuityEpoch = -1L;
    private static int sessionId = -1;
    private static int sampleRateHz;
    private static long samples;
    private static long successfulSamples;
    private static long errors;
    private static long timestampAvailable;
    private static long timestampUnavailable;

    private static long wrapBase;
    private static long lastRawHead = -1L;
    private static long extendedHead = -1L;
    private static long lastVideoMs = -1L;
    private static long lastHeadFrames = -1L;
    private static long lastVideoDeltaMs;
    private static long lastAudioDeltaMs;
    private static long lastDeltaErrorMs;
    private static long maxAbsDeltaErrorMs;
    private static int lastRatePermille;

    private static long lastTimestampFrame = -1L;
    private static long lastTimestampNano = -1L;
    private static long lastTimestampVsHeadFrames;
    private static long lastTraceVideoMs = Long.MIN_VALUE;
    private static int recentCount;
    private static int recentWrite;

    private AudioVideoSyncProbe() {}

    public static void sample(VideoSessionClock.Snapshot clock, AudioTrack track, boolean trace) {
        if (clock == null || !clock.open || clock.videoMs < 0L) return;
        synchronized (LOCK) {
            samples++;
            if (track == null) return;
            try {
                final int newSession = track.getAudioSessionId();
                final int newRate = track.getSampleRate();
                if (newRate <= 0) return;

                if (clock.videoEpoch != videoEpoch || clock.continuityEpoch != continuityEpoch
                        || newSession != sessionId) {
                    resetBaselineLocked(clock.videoEpoch, clock.continuityEpoch, newSession, newRate);
                }
                sampleRateHz = newRate;

                final long raw = Integer.toUnsignedLong(track.getPlaybackHeadPosition());
                if (lastRawHead >= 0L && raw < lastRawHead
                        && (lastRawHead - raw) > 0x80000000L) {
                    wrapBase += (1L << 32);
                }
                final long head = wrapBase + raw;

                AudioTimestamp timestamp = new AudioTimestamp();
                boolean haveTimestamp = false;
                try {
                    haveTimestamp = track.getTimestamp(timestamp);
                } catch (Throwable ignored) {
                    haveTimestamp = false;
                }
                if (haveTimestamp) {
                    timestampAvailable++;
                    lastTimestampFrame = timestamp.framePosition;
                    lastTimestampNano = timestamp.nanoTime;
                    lastTimestampVsHeadFrames = timestamp.framePosition - head;
                } else {
                    timestampUnavailable++;
                    lastTimestampFrame = -1L;
                    lastTimestampNano = -1L;
                    lastTimestampVsHeadFrames = 0L;
                }

                if (lastVideoMs >= 0L && lastHeadFrames >= 0L) {
                    final long videoDelta = clock.videoMs - lastVideoMs;
                    final long frameDelta = head - lastHeadFrames;
                    if (videoDelta > 0L && frameDelta >= 0L) {
                        final long audioDelta = (frameDelta * 1000L) / newRate;
                        final long error = audioDelta - videoDelta;
                        lastVideoDeltaMs = videoDelta;
                        lastAudioDeltaMs = audioDelta;
                        lastDeltaErrorMs = error;
                        maxAbsDeltaErrorMs = Math.max(maxAbsDeltaErrorMs, Math.abs(error));
                        lastRatePermille = (int) Math.max(0L, Math.min(10_000L,
                                (audioDelta * 1000L) / Math.max(1L, videoDelta)));
                    }
                }

                lastRawHead = raw;
                extendedHead = head;
                lastVideoMs = clock.videoMs;
                lastHeadFrames = head;
                successfulSamples++;
                recentVideoMs[recentWrite] = clock.videoMs;
                recentHeadFrames[recentWrite] = head;
                recentWrite = (recentWrite + 1) % RECENT;
                recentCount = Math.min(RECENT, recentCount + 1);

                if (trace && (lastTraceVideoMs == Long.MIN_VALUE
                        || Math.abs(clock.videoMs - lastTraceVideoMs) >= 5_000L)) {
                    lastTraceVideoMs = clock.videoMs;
                    SpanishStudyDiagnostics.record(SpanishStudyDiagnostics.AUDIO,
                            "clockAnchor videoMs=" + clock.videoMs
                                    + " videoEpoch=" + clock.videoEpoch
                                    + " continuityEpoch=" + clock.continuityEpoch
                                    + " session=" + newSession
                                    + " headFrames=" + head
                                    + " sampleRate=" + newRate
                                    + " timestamp=" + haveTimestamp
                                    + " timestampFrame=" + lastTimestampFrame
                                    + " audioDeltaMs=" + lastAudioDeltaMs
                                    + " videoDeltaMs=" + lastVideoDeltaMs
                                    + " deltaErrorMs=" + lastDeltaErrorMs
                                    + " ratePermille=" + lastRatePermille);
                }
            } catch (Throwable t) {
                errors++;
                if (trace) {
                    SpanishStudyDiagnostics.error(SpanishStudyDiagnostics.AUDIO,
                            "audio/video clock anchor sample failed", t);
                }
            }
        }
    }

    private static void resetBaselineLocked(long newVideoEpoch, long newContinuityEpoch,
                                            int newSessionId, int newRate) {
        videoEpoch = newVideoEpoch;
        continuityEpoch = newContinuityEpoch;
        sessionId = newSessionId;
        sampleRateHz = newRate;
        wrapBase = 0L;
        lastRawHead = -1L;
        extendedHead = -1L;
        lastVideoMs = -1L;
        lastHeadFrames = -1L;
        lastVideoDeltaMs = 0L;
        lastAudioDeltaMs = 0L;
        lastDeltaErrorMs = 0L;
        maxAbsDeltaErrorMs = 0L;
        lastRatePermille = 0;
        lastTimestampFrame = -1L;
        lastTimestampNano = -1L;
        lastTimestampVsHeadFrames = 0L;
        recentCount = 0;
        recentWrite = 0;
        lastTraceVideoMs = Long.MIN_VALUE;
    }

    public static String diagnostics() {
        synchronized (LOCK) {
            StringBuilder out = new StringBuilder();
            out.append("audioVideoSyncProbe=controller-sampled-audiotrack-render-clock\n");
            out.append("audioVideoSyncThread=controller-video-time-callback-not-audiotrack-write\n");
            out.append("audioVideoSyncVideoEpoch=").append(videoEpoch).append('\n');
            out.append("audioVideoSyncContinuityEpoch=").append(continuityEpoch).append('\n');
            out.append("audioVideoSyncSessionId=").append(sessionId).append('\n');
            out.append("audioVideoSyncSampleRateHz=").append(sampleRateHz).append('\n');
            out.append("audioVideoSyncSamples=").append(samples).append('\n');
            out.append("audioVideoSyncSuccessfulSamples=").append(successfulSamples).append('\n');
            out.append("audioVideoSyncErrors=").append(errors).append('\n');
            out.append("audioVideoSyncTimestampAvailable=").append(timestampAvailable).append('\n');
            out.append("audioVideoSyncTimestampUnavailable=").append(timestampUnavailable).append('\n');
            out.append("audioVideoSyncPlaybackHeadFrames=").append(extendedHead).append('\n');
            out.append("audioVideoSyncTimestampFrame=").append(lastTimestampFrame).append('\n');
            out.append("audioVideoSyncTimestampNano=").append(lastTimestampNano).append('\n');
            out.append("audioVideoSyncTimestampVsHeadFrames=").append(lastTimestampVsHeadFrames).append('\n');
            out.append("audioVideoSyncLastVideoDeltaMs=").append(lastVideoDeltaMs).append('\n');
            out.append("audioVideoSyncLastAudioDeltaMs=").append(lastAudioDeltaMs).append('\n');
            out.append("audioVideoSyncLastDeltaErrorMs=").append(lastDeltaErrorMs).append('\n');
            out.append("audioVideoSyncMaxAbsDeltaErrorMs=").append(maxAbsDeltaErrorMs).append('\n');
            out.append("audioVideoSyncRatePermille=").append(lastRatePermille).append('\n');
            out.append("audioVideoSyncRecentAnchors=");
            for (int i = 0; i < recentCount; i++) {
                int slot = (recentWrite - recentCount + i + RECENT) % RECENT;
                if (i > 0) out.append(',');
                out.append(recentVideoMs[slot]).append('@').append(recentHeadFrames[slot]);
            }
            out.append('\n');
            return out.toString();
        }
    }
}
